"""Source-bound multi-view facial texture transport, never geometry authoring.

Configuration supplies paired visual annotations; the front annotations locate
shared surface points so each donor registers to the same face, not three guesses.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import Delaunay
from raster_geometry import triangle_pixels
from projection_visibility import project_surface, depth_visible
from map_face_donor import pad_face_gutters


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def linear(rgb):
    v = np.asarray(rgb, np.float32) / 255
    return np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)


def srgb(v):
    v = np.clip(v, 0, 1)
    return np.rint(255 * np.where(v <= .0031308, v * 12.92, 1.055 * v ** (1/2.4) - .055)).astype(np.uint8)


def surface_anchor(data, point):
    """Nearest visible triangle and perspective-correct barycentrics at a pixel."""
    screen = data['screen']
    candidates = np.flatnonzero(np.all(point >= screen.min(axis=1),axis=1) & np.all(point <= screen.max(axis=1),axis=1))
    hits = []
    for i in candidates:
        matrix = np.column_stack((screen[i,0]-screen[i,2],screen[i,1]-screen[i,2]))
        if abs(np.linalg.det(matrix)) < 1e-10:
            continue
        xy = np.linalg.solve(matrix,point-screen[i,2])
        bary = np.array([*xy,1-xy.sum()])
        if bary.min() < -1e-7:
            continue
        weights = bary/data['depth'][i]
        weights /= weights.sum()
        hits.append((float(weights@data['depth'][i]),int(i),weights))
    if not hits:
        raise ValueError('Facial annotation misses the mesh: '+str(point))
    _, triangle, weights = min(hits,key=lambda x:x[0])
    return triangle, weights


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    root = args.config.resolve().parent
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Retained candidate exists')
    required = {config['base_color']}
    for spec in config['views']:
        required.update((spec['donor'],spec['correspondence']))
    if config.get('tone_points'):
        required.add(config['source_front'])
    if not required.issubset(config['hashes']):
        raise ValueError('Every consumed image and correspondence must be hash-bound')
    for path, expected in config['hashes'].items():
        if sha(root/path) != expected:
            raise ValueError('Source changed: '+path)
    base = np.array(Image.open(root/config['base_color']).convert('RGB'))
    size = len(base)
    if base.shape != (size,size,3):
        raise ValueError('Expected square RGB atlas')
    datasets = []
    for spec in config['views']:
        with np.load(root/spec['correspondence']) as archive:
            data = {k:archive[k] for k in archive.files}
        if datasets and not np.array_equal(data['uv'],datasets[0]['data']['uv']):
            raise ValueError('Views do not share UV authority')
        datasets.append({'spec':spec,'data':data})
    anchors = [surface_anchor(datasets[0]['data'], np.asarray(p)) for p in config['front_surface_landmarks']]
    tone_points = np.asarray(config.get('tone_points',[]),float)
    tone_anchors = [surface_anchor(datasets[0]['data'],p) for p in tone_points]
    if tone_anchors:
        source_view = linear(np.array(Image.open(root/config['source_front']).convert('RGB')))
        reference_tones = np.column_stack([ndimage.map_coordinates(source_view[...,c],[tone_points[:,1],tone_points[:,0]],order=1) for c in range(3)])
    registrations = []
    for item in datasets:
        spec, data = item['spec'], item['data']
        points = [project_surface(w[None,:],data['screen'][i],data['depth'][i])[0][0] for i,w in anchors]
        boundary = np.asarray(spec['boundary'],float)
        target = np.concatenate((boundary,points))
        donor_points = np.concatenate((np.asarray(spec.get('donor_boundary',spec['boundary']),float),np.asarray(spec['donor_landmarks'],float)))
        triangulation = Delaunay(target)
        for ids in triangulation.simplices:
            t,d = target[ids],donor_points[ids]
            if np.linalg.det([t[1]-t[0],t[2]-t[0]]) * np.linalg.det([d[1]-d[0],d[2]-d[0]]) <= 0:
                raise ValueError('Folded landmark registration: '+spec['name']+' '+str(ids.tolist())+' target='+str(t.tolist())+' donor='+str(d.tolist()))
        mask = Image.new('L',(1024,1024))
        ImageDraw.Draw(mask).polygon([tuple(p) for p in boundary],fill=255)
        feather = np.clip(ndimage.distance_transform_edt(np.array(mask)>0)/config.get('feather',18),0,1)
        donor = np.array(Image.open(root/spec['donor']).convert('RGB'))
        # Only exterior-connected neutral background is excluded; eye whites survive.
        neutral = np.ptp(donor.astype(int),axis=2)<15
        seed = np.zeros(neutral.shape,bool)
        seed[[0,-1],:] = neutral[[0,-1],:]
        seed[:,[0,-1]] = neutral[:,[0,-1]]
        foreground = ~ndimage.binary_propagation(seed,mask=neutral)
        validity = np.clip(ndimage.distance_transform_edt(foreground)/4,0,1)
        protection = Image.new('L',(1024,1024))
        for polygon in spec.get('protected_polygons',[]):
            ImageDraw.Draw(protection).polygon([tuple(p) for p in polygon],fill=255)
        donor_linear = linear(donor)
        gain = np.ones(3)
        if tone_anchors:
            tones = np.array([project_surface(w[None,:],data['screen'][i],data['depth'][i])[0][0] for i,w in tone_anchors])
            simplex = triangulation.find_simplex(tones)
            if np.any(simplex<0):
                raise ValueError('Tone anchors outside registration')
            transform = triangulation.transform[simplex]
            bary = np.einsum('ijk,ik->ij',transform[:,:2],tones-transform[:,2])
            bary = np.column_stack((bary,1-bary.sum(axis=1)))
            mapped = np.einsum('ij,ijk->ik',bary,donor_points[triangulation.simplices[simplex]])
            dx,dy = mapped[:,0]*donor.shape[1]/1024,mapped[:,1]*donor.shape[0]/1024
            measured = np.column_stack([ndimage.map_coordinates(donor_linear[...,c],[dy,dx],order=1) for c in range(3)])
            gain = np.median(reference_tones/np.maximum(measured,.001),axis=0)
            if gain.min()<.5 or gain.max()>2:
                raise ValueError('Excessive source/donor color mismatch')
            donor_linear *= gain
        hold = np.array(protection)>0
        protection_fade = np.clip(ndimage.distance_transform_edt(~hold)/config.get('protection_feather',1),0,1)
        item.update(triangulation=triangulation,donor_points=donor_points,donor=donor_linear,feather=feather,validity=validity,protection=hold.astype(float),protection_fade=protection_fade)
        registrations.append({'name':spec['name'],'target':target.tolist(),'donor':donor_points.tolist(),'linear_color_gain':gain.tolist()})
    result = base.copy()
    occupied = np.zeros((size,size),bool)
    protected = np.zeros_like(occupied)
    coverage = np.zeros((size,size),np.float32)
    counts = {s['spec']['name']:0 for s in datasets}
    authority = datasets[0]['data']
    for i,uv in enumerate(authority['uv']):
        pixels = triangle_pixels(uv,size)
        if pixels is None:
            continue
        yy,xx,weights = pixels
        occupied[yy,xx] = True
        if not authority['eligible'][i]:
            protected[yy,xx] = True
            continue
        total = np.zeros((len(xx),3),np.float32)
        quality_sum = np.zeros(len(xx),np.float32)
        alpha_max = np.zeros(len(xx),np.float32)
        protection_confidence = np.ones(len(xx),np.float32)
        for item in datasets:
            spec,data,tri = item['spec'],item['data'],item['triangulation']
            screen,depth = project_surface(weights,data['screen'][i],data['depth'][i])
            visible = depth_visible(screen,depth,data['depth_buffer'],float(data['depth_tolerance']))
            if not visible.any():
                continue
            hold = ndimage.map_coordinates(item['protection'],[screen[:,1],screen[:,0]],order=0,mode='constant')>.5
            protected[yy[hold & visible],xx[hold & visible]] = True
            hold_fade = ndimage.map_coordinates(item['protection_fade'],[screen[:,1],screen[:,0]],order=1,mode='constant',cval=1)
            protection_confidence = np.minimum(protection_confidence,np.where(visible,hold_fade,1))
            simplex = tri.find_simplex(screen)
            safe = np.maximum(simplex,0)
            transform = tri.transform[safe]
            bary = np.einsum('ijk,ik->ij',transform[:,:2],screen-transform[:,2])
            bary = np.column_stack((bary,1-bary.sum(axis=1)))
            mapped = np.einsum('ij,ijk->ik',bary,item['donor_points'][tri.simplices[safe]])
            donor = item['donor']
            dx,dy = mapped[:,0]*donor.shape[1]/1024,mapped[:,1]*donor.shape[0]/1024
            fade = ndimage.map_coordinates(item['feather'],[screen[:,1],screen[:,0]],order=1,mode='constant')
            valid = ndimage.map_coordinates(item['validity'],[dy,dx],order=1,mode='constant')
            cosine = np.clip(weights@data['cosine'][i],0,1)
            alpha = fade*valid*visible*(simplex>=0)*np.clip((cosine-.2)/.4,0,1)
            quality = alpha*cosine**6*spec.get('priority',1)
            colors = np.column_stack([ndimage.map_coordinates(donor[...,c],[dy,dx],order=1,mode='nearest') for c in range(3)])
            total += colors*quality[:,None]
            quality_sum += quality
            alpha_max = np.maximum(alpha_max,alpha)
            counts[spec['name']] += int(np.count_nonzero(quality>1e-6))
        alpha_max *= (quality_sum>1e-6)*protection_confidence
        active = alpha_max>0
        blended = total/np.maximum(quality_sum[:,None],1e-10)
        candidate = srgb(blended*alpha_max[:,None]+linear(base[yy,xx])*(1-alpha_max[:,None]))
        result[yy[active],xx[active]] = candidate[active]
        coverage[yy,xx] = np.maximum(coverage[yy,xx],alpha_max)
    result[protected] = base[protected]
    coverage[protected] = 0
    support = coverage>0
    if not 1000 < support.sum() < size*size*.15:
        raise ValueError('Unexpected facial scope')
    result,gutters = pad_face_gutters(result,occupied,support,8)
    if not np.array_equal(result[~(support|gutters)],base[~(support|gutters)]):
        raise ValueError('Transport escaped declared facial support')
    output.mkdir(parents=True)
    Image.fromarray(result).save(output/'BaseColor.png')
    Image.fromarray(np.rint(coverage*255).astype(np.uint8)).save(output/'coverage.png')
    Image.fromarray(gutters.astype(np.uint8)*255).save(output/'gutters.png')
    (output/'mapping.json').write_text(json.dumps({'config_sha256':sha(args.config),'output_sha256':sha(output/'BaseColor.png'),'selected_texels':int(support.sum()),'changed_texels':int(np.any(result!=base,axis=2).sum()),'outside_support_and_gutters_bit_identical':True,'geometry_uv_modified':False,'status':'candidate_pending_actual_multiview_review','view_counts':counts,'registrations':registrations,'surface_anchors':[{'triangle':i,'weights':w.tolist()} for i,w in anchors]},indent=2))
    print('MULTIVIEW_FACE_READY -- three opinions, one actual surface.')


if __name__ == '__main__':
    main()
