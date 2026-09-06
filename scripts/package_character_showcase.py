"""Package unretouched UE captures and a palette-encoded walk GIF for GitHub."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess


def validate_capture(directory):
    report=json.loads((directory/'showcase.json').read_text())
    if report.get('ok') is not True or report.get('source_assets_saved') is not False:
        raise ValueError('Only successful, non-mutating native captures may be published')
    walk=[f for f in report['frames'] if f['name']=='walk']
    if len(walk)!=report['frames_per_cycle'] or len(walk)<12 or report['cycle_seconds']<=0:
        raise ValueError('Incomplete walking cycle')
    if len({f['file'] for f in report['frames']})!=len(report['frames']):
        raise ValueError('Duplicate capture records')
    for frame in report['frames']:
        file=Path(frame['file'])
        if file.name!=frame['file']:
            raise ValueError('Capture filenames must be local basenames')
        if hashlib.sha256((directory/file).read_bytes()).hexdigest()!=frame.get('sha256'):
            raise ValueError('Capture image changed: '+str(file))
        if not frame['attachments'] or any(a['error_cm']>.1 for a in frame['attachments']):
            raise ValueError('Attachment review failed')
    if len({f['sha256'] for f in walk})!=len(walk):
        raise ValueError('Duplicate walk frames cannot masquerade as animation')
    for bone in ('foot_l','foot_r'):
        positions=[f.get('bones',{}).get(bone) for f in walk]
        if any(p is None or len(p)!=3 or not all(math.isfinite(x) for x in p) for p in positions):
            raise ValueError('Missing or invalid foot pose evidence')
        if max(math.dist(positions[0],p) for p in positions)<1:
            raise ValueError('Frozen feet cannot masquerade as a walking rig')
    for index,frame in enumerate(walk):
        expected=report['cycle_seconds']*index/len(walk)
        if abs(frame['actual_position']-expected)>1e-4:
            raise ValueError('Captured animation time does not match the cycle')
        if frame['file']!=f'walk-{index:03d}.png':
            raise ValueError('Walk frames must be contiguous and ordered')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--ffmpeg',default=shutil.which('ffmpeg'))
    args=parser.parse_args()
    capture,output=args.capture.resolve(),args.output.resolve()
    if output.exists():
        raise ValueError('Keep the previous published candidate; use a fresh directory')
    if not args.ffmpeg or not Path(args.ffmpeg).is_file():
        raise ValueError('Pass --ffmpeg with an installed FFmpeg executable')
    report=validate_capture(capture)
    output.mkdir(parents=True)
    files=[]
    for frame in report['frames']:
        if frame['name']!='walk':
            shutil.copyfile(capture/frame['file'],output/frame['file'])
            files.append(frame['file'])
    gif=output/'walk.gif'
    rate=report['frames_per_cycle']/report['cycle_seconds']
    command=[args.ffmpeg,'-v','error','-n','-framerate',str(rate),'-i',str(capture/'walk-%03d.png'),
        '-filter_complex','[0:v]split[a][b];[a]palettegen=stats_mode=full[p];[b][p]paletteuse=dither=bayer:bayer_scale=3',
        '-loop','0',str(gif)]
    subprocess.run(command,check=True)
    files.append(gif.name)
    from PIL import Image
    with Image.open(gif) as image:
        if image.n_frames!=report['frames_per_cycle']:
            raise ValueError('GIF lost animation frames')
        duration=0
        for i in range(image.n_frames):
            image.seek(i); duration+=image.info.get('duration',0)
        if abs(duration/1000-report['cycle_seconds'])>.05:
            raise ValueError('GIF playback speed changed')
    public={'schema':'reference-asset-compiler.showcase-media.v1','engine':report['engine'],
        'mesh':report['mesh'],'blueprint':report['blueprint'],'animation':report['animation'],
        'capture_level':report.get('config',{}).get('level'),
        'temporary_portrait_fill':report.get('config',{}).get('portrait_fill'),
        'capture_receipt_sha256':hashlib.sha256((capture/'showcase.json').read_bytes()).hexdigest(),
        'runtime_audit_sha256':report['runtime_audit_sha256'],'config_sha256':report['config_sha256'],
        'cycle_seconds':report['cycle_seconds'],'gif_frames':report['frames_per_cycle'],'gif_duration_ms':duration,
        'source_assets_modified':False,'retouching':False,'interpolated_frames':False,
        'status':'Reviewed demo capture; final neck appearance pending human approval; no facial-animation claim',
        'files':{f:{'sha256':hashlib.sha256((output/f).read_bytes()).hexdigest(),'bytes':(output/f).stat().st_size} for f in files}}
    (output/'provenance.json').write_text(json.dumps(public,indent=2)+'\n')
    print('SHOWCASE_MEDIA_READY '+str(output)+' -- genuine pixels, modest luggage.')


if __name__=='__main__':
    main()
