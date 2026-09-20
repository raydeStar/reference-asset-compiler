import http from 'node:http';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {chromium}=require('C:/Users/Ayric/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const video=path.join(root,'out/stillwater-showcase-2026-09-16/Stillwater-showcase-1080p.mp4');
const size=(await fsp.stat(video)).size;
const server=http.createServer((req,res)=>{
  if(req.url==='/'){
    res.writeHead(200,{'Content-Type':'text/html'});
    res.end('<!doctype html><html><head><title>Stillwater video review</title><style>body{margin:0;background:#000}video{display:block;width:100vw;height:100vh}</style></head><body><video controls muted playsinline preload="auto" src="/film.mp4"></video></body></html>');return;
  }
  if(req.url!=='/film.mp4'){res.writeHead(404);res.end();return;}
  const match=req.headers.range?.match(/bytes=(\d+)-(\d*)/);
  const start=match?Number(match[1]):0,end=match&&match[2]?Math.min(Number(match[2]),size-1):size-1;
  res.writeHead(match?206:200,{'Content-Type':'video/mp4','Accept-Ranges':'bytes','Content-Length':end-start+1,...(match?{'Content-Range':`bytes ${start}-${end}/${size}`}:{})});
  fs.createReadStream(video,{start,end}).pipe(res);
});
await new Promise(resolve=>server.listen(5189,'127.0.0.1',resolve));
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=d3d11']});
try{
  const page=await browser.newPage({viewport:{width:1920,height:1080}});
  await page.goto('http://127.0.0.1:5189/');
  const result=await page.evaluate(async()=>{
    const v=document.querySelector('video');const events=[];
    for(const name of ['waiting','stalled','error'])v.addEventListener(name,()=>events.push({type:name,time:v.currentTime}));
    await new Promise((resolve,reject)=>{v.oncanplaythrough=resolve;v.onerror=reject;if(v.readyState===4)resolve();});
    const start=performance.now();await v.play();
    await new Promise((resolve,reject)=>{v.onended=resolve;v.onerror=reject;});
    const quality=v.getVideoPlaybackQuality();
    return {duration:v.duration,width:v.videoWidth,height:v.videoHeight,ended:v.ended,wallSeconds:(performance.now()-start)/1000,totalVideoFrames:quality.totalVideoFrames,droppedVideoFrames:quality.droppedVideoFrames,events};
  });
  await fsp.writeFile(path.join(root,'work/lakeside-village/evidence/showcase-video-v1/browser-playback.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
  if(!result.ended||result.events.some(e=>e.type==='error'))throw new Error('Playback failed');
  console.log('The screening is complete; the lake kept perfect time.');
}finally{await browser.close();server.close();}
