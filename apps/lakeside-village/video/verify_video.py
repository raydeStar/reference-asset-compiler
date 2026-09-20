"""Decode the delivered file, audit timing, and make actual-video review frames."""
from pathlib import Path
import hashlib
import io
import json
import struct
import subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[3]
output = root / 'out/stillwater-showcase-2026-09-16'
evidence = root / 'work/lakeside-village/evidence/showcase-video-v1'
video = output / 'Stillwater-showcase-1080p.mp4'
probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(video)]))
stream = probe['streams'][0]
assert len(probe['streams']) == 1 and stream['codec_name'] == 'h264'
assert (stream['width'],stream['height']) == (1920,1080)
assert stream['avg_frame_rate'] == '30/1' and stream['pix_fmt'] == 'yuv420p'
assert int(stream['nb_frames']) == 705 and float(stream['duration']) == 23.5
frame_info = json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time','-of','json',str(video)]))
timestamps = np.array([float(f['best_effort_timestamp_time']) for f in frame_info['frames']])
assert len(timestamps) == 705 and np.max(np.abs(np.diff(timestamps)-1/30)) < 0.000002
raw = subprocess.check_output(['ffmpeg','-v','error','-i',str(video),'-vf','scale=240:135','-pix_fmt','gray','-f','rawvideo','pipe:1'])
frames = np.frombuffer(raw,dtype=np.uint8).reshape((-1,135,240))
assert len(frames) == 705
motion = np.abs(np.diff(frames.astype(np.float32),axis=0)).mean(axis=(1,2))
ranges = {'opening':(15,90),'village':(158,240),'asset_rotation':(250,323),'wireframe_rotation':(327,357),'ending':(580,660)}
checks = {}
for label,(a,b) in ranges.items():
    values=motion[a:b]
    checks[label]={'mean_frame_change':float(values.mean()),'max_frame_change':float(values.max()),'identical_adjacent_frames':int(np.sum(values==0))}
    assert np.sum(values==0)==0, (label,'unexpected frozen frame')
boxes=[]
with video.open('rb') as f:
    while True:
        at=f.tell();header=f.read(8)
        if len(header)<8:break
        size,kind=struct.unpack('>I4s',header)
        if size==1:size=struct.unpack('>Q',f.read(8))[0]
        if size==0:size=video.stat().st_size-at
        boxes.append({'type':kind.decode('ascii'),'offset':at,'size':size})
        f.seek(at+size)
assert next(b['offset'] for b in boxes if b['type']=='moov') < next(b['offset'] for b in boxes if b['type']=='mdat')
times=[1.5,3.9,6.5,9.4,11.3,13,14.3,16,21.2]
sheet=Image.new('RGB',(1920,3*392),'#14261e')
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
draw=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
    png=subprocess.check_output(['ffmpeg','-v','error','-ss',str(t),'-i',str(video),'-frames:v','1','-f','image2pipe','-vcodec','png','pipe:1'])
    img=Image.open(io.BytesIO(png)).convert('RGB')
    img.save(evidence/f'decoded-{int(t*100):04d}.png')
    if i==0:img.save(output/'Stillwater-cover.jpg',quality=94)
    x=(i%3)*640;y=(i//3)*392
    sheet.paste(img.resize((640,360),Image.Resampling.LANCZOS),(x,y))
    draw.text((x+14,y+365),f'{t:04.1f} s',font=font,fill='#f5efd9')
sheet.save(evidence/'video-contact-sheet.jpg',quality=94)
report={'file':str(video),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'bytes':video.stat().st_size,'format':probe['format'],'stream':stream,'decoded_frames':len(frames),'constant_frame_rate_verified':True,'max_timestamp_step_error_seconds':float(np.max(np.abs(np.diff(timestamps)-1/30))),'faststart':True,'mp4_boxes':boxes,'motion_checks':checks,'capture_errors':json.loads((evidence/'capture.json').read_text())['errors'],'first_frame_mean_luma':float(frames[0].mean()),'last_frame_mean_luma':float(frames[-1].mean())}
(evidence/'video-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['format','stream','mp4_boxes']},indent=2))
print('Every frame accounted for; no scenery left waiting at the station.')
