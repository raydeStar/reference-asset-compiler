import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { chromium } = require('C:/Users/Ayric/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const output = path.resolve('work/lakeside-village/evidence/showcase-video-v1');
await fs.mkdir(output, {recursive:true});
const browser = await chromium.launch({channel:'chrome',headless:true,args:['--use-angle=d3d11','--disable-background-timer-throttling']});
try {
  const page = await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto('https://markbhall.dev/stillwater/',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.documentElement.dataset.ready==='true',{timeout:120000});
  await page.evaluate(()=>document.fonts.ready);
  await page.locator('#auto-rotate').click();
  await page.screenshot({path:path.join(output,'live-page.png')});
  for(const [id,title] of [['timber-cabin','Timber cabin'],['round-cottage','Round cottage'],['rowboat','Clinker rowboat']]) {
    await page.getByRole('button',{name:`Inspect ${title}`}).click();
    await page.waitForTimeout(200);
    await page.locator('.inspector-panel').screenshot({path:path.join(output,`live-${id}.png`)});
  }
  await page.getByRole('button',{name:'Inspect Timber cabin'}).click();
  await page.locator('#wireframe').click();
  await page.locator('.inspector-panel').screenshot({path:path.join(output,'live-wireframe.png')});
  await page.locator('#asset-reference').click();
  await page.locator('#reference-image').evaluate(img=>img.decode());
  await page.screenshot({path:path.join(output,'live-reference.png')});
  await page.getByRole('button',{name:'Close reference'}).click();
  await page.locator('.making-heading').scrollIntoViewIfNeeded();
  await page.screenshot({path:path.join(output,'live-workflow.png')});
  const info=await page.evaluate(()=>{const gl=document.querySelector('#world canvas').getContext('webgl2');const debug=gl.getExtension('WEBGL_debug_renderer_info');return {renderer:debug?gl.getParameter(debug.UNMASKED_RENDERER_WEBGL):gl.getParameter(gl.RENDERER),ready:document.documentElement.dataset.ready,assetNames:[...document.querySelectorAll('.asset-card')].map(b=>b.getAttribute('aria-label'))};});
  await fs.writeFile(path.join(output,'live-inspection.json'),JSON.stringify({url:page.url(),...info,errors},null,2));
  console.log(JSON.stringify({...info,errors}));
  console.log('The location scout has returned from the shore.');
} finally {await browser.close();}
