import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {createServer} from 'vite';
const require=createRequire(import.meta.url);
const {chromium}=require('C:/Users/Ayric/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const directory=path.dirname(fileURLToPath(import.meta.url));
const app=path.dirname(directory);
const root=path.resolve(app,'../..');
const evidence=path.join(root,'work/lakeside-village/evidence/showcase-video-v1');
const output=path.join(root,'out/stillwater-showcase-2026-09-16');
await fs.mkdir(evidence,{recursive:true});await fs.mkdir(output,{recursive:true});
const preview=process.argv.includes('--preview');
const css=await fs.readFile(path.join(directory,'film.css'),'utf8');
const director=await fs.readFile(path.join(directory,'director.js'),'utf8');
const original=await fs.readFile(path.join(app,'src/main.js'),'utf8');
const sourceHash=createHash('sha256').update(original).digest('hex');
const server=await createServer({root:app,configFile:false,server:{host:'127.0.0.1',port:5188,strictPort:true},plugins:[{
  name:'stillwater-capture-only',enforce:'pre',
  transform(code,id){if(id.replaceAll('\\','/').endsWith('/src/main.js'))return code.replaceAll('requestAnimationFrame(animate);','/* The film director advances this frame explicitly. */')+'\n'+director;},
  transformIndexHtml(html){return html.replace('</head>',`<style>${css}</style></head>`);},
}]});
await server.listen();
const browser=await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=d3d11','--disable-background-timer-throttling','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows']});
let encoder;
try{
  const page=await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('http://127.0.0.1:5188/',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.documentElement.dataset.ready==='true'&&window.__film,{timeout:120000});
  // Vite injects the app stylesheet after the head; capture overrides belong last.
  await page.addStyleTag({content:css});
  await page.evaluate(()=>window.__film.prepare());
  const times=preview?[1.5,3.9,6.5,9.4,11.3,13,15,18,20.8]:Array.from({length:705},(_,i)=>i/30);
  if(!preview){
    const finalPath=path.join(output,'Stillwater-showcase-1080p.mp4');
    try{await fs.access(finalPath);throw new Error('Output already exists; retain it and choose a new version.');}catch(e){if(e.code!=='ENOENT')throw e;}
    encoder=spawn('ffmpeg',['-hide_banner','-loglevel','error','-f','image2pipe','-framerate','30','-vcodec','mjpeg','-i','pipe:0','-an','-vf','scale=in_range=full:out_range=tv:out_color_matrix=bt709,setsar=1','-c:v','libx264','-threads','8','-preset','slow','-crf','18','-pix_fmt','yuv420p','-profile:v','high','-level','4.2','-movflags','+faststart','-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-metadata','title=Stillwater — Reference Asset Compiler','-metadata','comment=Actual Three.js browser renders. Deterministic camera direction; original project assets.','-y',finalPath],{stdio:['pipe','ignore','pipe'],windowsHide:true});
    encoder.stderr.on('data',d=>process.stderr.write(d));
  }
  const start=Date.now();const shots=[];
  for(let i=0;i<times.length;i++){
    const state=await page.evaluate(t=>window.__film.frame(t),times[i]);
    const buffer=await page.screenshot({type:'jpeg',quality:97,animations:'disabled'});
    if(preview||i%30===0){await fs.writeFile(path.join(evidence,`${preview?'preview':'frame'}-${String(preview?Math.round(times[i]*100):i).padStart(4,'0')}.jpg`),buffer);shots.push({...state,frame:i});}
    if(encoder&&!encoder.stdin.write(buffer))await once(encoder.stdin,'drain');
    if(i%60===0)console.log(`${preview?'Preview':'Capture'} ${i+1}/${times.length}; shot=${state.shot}; elapsed=${((Date.now()-start)/1000).toFixed(1)}s. The camera is keeping its composure.`);
  }
  if(encoder){encoder.stdin.end();const [code]=await once(encoder,'close');if(code)throw new Error(`FFmpeg exited ${code}`);}
  const gl=await page.evaluate(()=>{const gl=document.querySelector('#world canvas').getContext('webgl2');const e=gl.getExtension('WEBGL_debug_renderer_info');return gl.getParameter(e.UNMASKED_RENDERER_WEBGL);});
  await fs.writeFile(path.join(evidence,preview?'preview.json':'capture.json'),JSON.stringify({sourceHash,renderer:gl,width:1920,height:1080,fps:30,frames:times.length,duration:23.5,elapsedSeconds:(Date.now()-start)/1000,errors,shots},null,2));
  if(errors.length)throw new Error(JSON.stringify(errors));
  console.log(preview?'Shot previews ready for review.':'Finished: '+path.join(output,'Stillwater-showcase-1080p.mp4'));
}finally{if(encoder&&!encoder.killed&&encoder.exitCode===null)encoder.kill();await browser.close();await server.close();}
