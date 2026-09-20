// Appended only by the local film server. No private capture hooks ship to Pages.
const film = { layout: null, shot: null };
const clamp = (v) => Math.max(0, Math.min(1,v));
const smooth = (v) => {v=clamp(v); return v*v*(3-2*v);};
const mix = (a,b,t) => a.map((v,i)=>v+(b[i]-v)*t);
const overlay=document.createElement('div');
overlay.id='film-overlay';
overlay.innerHTML='<div id="film-shade"></div><div id="film-corner">Stillwater</div><div id="film-hook">ONE REFERENCE. SEVEN ASSETS. ONE LITTLE WORLD.</div><div id="film-end"><div class="project">Reference Asset Compiler</div><div class="url">markbhall.dev/stillwater</div><div class="method">Local AI → reviewed assets → interactive world</div></div>';
document.body.appendChild(overlay);
const source=document.createElement('section');source.id='film-source';
source.innerHTML=`<div class="source-label">01 / THE ARTISTIC STARTING POINT</div><img class="source-main" src="/reference.png" alt="Original Stillwater reference"><div class="source-side"><h2>One scene.<br>Seven separate<br>references.</h2><p>Each object image conditioned<br>its own 3D reconstruction.</p><div class="reference-grid">${assets.map(a=>`<img src="/assets/${a.id}.thumb.webp" alt="${a.name}">`).join('')}</div></div><div class="source-credit">SUPPLIED SCENE IMAGE → ISOLATED OBJECT REFERENCES</div>`;
document.body.appendChild(source);
const fade=document.createElement('div');fade.id='film-fade';document.body.appendChild(fade);

function resizeFilmView(view,element) {
  const rect=element.getBoundingClientRect();
  if(rect.width && rect.height){view.renderer.setSize(rect.width,rect.height,false);view.camera.aspect=rect.width/rect.height;view.camera.updateProjectionMatrix();}
}
function filmLayout(layout) {
  if(film.layout===layout)return;
  film.layout=layout;
  document.documentElement.dataset.filmLayout=layout;
  if(layout==='asset'){
    ensureInspector();
    inspect.controls.autoRotate=false;inspect.controls.enableDamping=false;inspect.controls.update();
    $('auto-rotate').setAttribute('aria-pressed','false');$('auto-rotate').classList.remove('active');
    resizeFilmView(inspect,$('inspector'));
  }
  resizeFilmView(world,$('world'));
}
function worldPose(position,target,fov=49){
  world.controls.enableDamping=false;world.controls.autoRotate=false;
  world.camera.position.fromArray(position);world.controls.target.fromArray(target);
  world.camera.fov=fov;world.camera.updateProjectionMatrix();world.controls.update(0);
}
function assetPose(angle){
  inspect.camera.position.set(Math.sin(angle)*5.0,2.6,Math.cos(angle)*5.0);
  inspect.controls.target.set(0,.9,0);inspect.controls.update(0);
}
function setWire(value){if(wireframe!==value)$('wireframe').click();}
window.__film={
  async prepare(){
    await document.fonts.ready;
    await Promise.all([...document.images].map(img=>{img.loading='eager';return img.decode().catch(()=>{});}));
    const ref=new Image();ref.src='/assets/timber-cabin.png';await ref.decode();
    ensureInspector();selectAsset('timber-cabin',true);
    $('stage-status').textContent='GLB audit · geometry and UVs preserved · textures embedded';
    const summaries=['Seven isolated object references from the original scene.','Image-conditioned meshes, generated locally.','Shape review, stray-geometry cleanup and UV preparation.','PBR materials on reviewed meshes. Assembly in Three.js.'];
    document.querySelectorAll('.process-grid li p').forEach((p,i)=>p.textContent=summaries[i]);
    paused=true;cameraTween=null;world.controls.enableDamping=false;world.controls.update(0);
    inspect.controls.autoRotate=false;inspect.controls.enableDamping=false;inspect.controls.update(0);
    world.renderer.compile(world.scene,world.camera);inspect.renderer.compile(inspect.scene,inspect.camera);
    filmLayout('world');
  },
  async frame(t){
    let shot=t<3.3?'opening':t<5.1?'source':t<8.2?'explore':t<10.8?'asset':t<12?'wire':t<14.1?'reference':t<19?'workflow':'ending';
    const changed=film.shot!==shot;
    if(changed){
      if($('reference-dialog').open)$('reference-dialog').close();
      filmLayout(['asset','wire','reference'].includes(shot)?'asset':shot==='workflow'?'workflow':'world');
      if(shot==='asset'){assetButtons.get('timber-cabin').click();inspect.controls.autoRotate=false;inspect.controls.enableDamping=false;}
      setWire(shot==='wire');
      if(shot==='reference'){$('asset-reference').click();await $('reference-image').decode();}
      film.shot=shot;
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    }
    source.style.display=shot==='source'?'block':'none';
    const scenic=['opening','explore','ending'].includes(shot);
    overlay.style.display=scenic?'block':'none';
    $('film-hook').style.opacity=shot==='opening'?String(smooth((t-.25)/.45)*(1-smooth((t-2.9)/.35))):'0';
    $('film-corner').style.opacity=shot==='opening'?'1':'0';
    $('film-end').style.opacity=shot==='ending'?String(smooth((t-19.3)/.65)):'0';
    $('film-shade').style.opacity=shot==='explore'?'0':'1';
    fade.style.opacity=String(t<.25?1-smooth(t/.25):smooth((t-22.65)/.8));
    if(shot==='workflow'){
      window.scrollTo(0,smooth((t-14.1)/1.5)*100);
    }else window.scrollTo(0,0);
    if(shot==='opening')worldPose(mix([6,13,64],[3.3,12.6,61],smooth(t/3.3)),[0,-3,-18]);
    if(shot==='explore')worldPose(mix([-5,9.4,20],[-1.4,8.8,17],smooth((t-5.1)/3.1)),[24,4,-13],48);
    if(['asset','wire','reference'].includes(shot))assetPose(.45+smooth((t-8.2)/3.8)*.45);
    if(shot==='ending')worldPose(mix([2.4,12.3,60],[6,13,64],smooth((t-19)/3.2)),[0,-3,-18]);
    time=9+t;previous=t*1000;worldVisible=scenic;inspectorVisible=['asset','wire','reference'].includes(shot);
    animate(t*1000);
    if(changed){await new Promise(resolve=>requestAnimationFrame(resolve));animate(t*1000);}
    return {shot,time:t,loaded,wireframe,camera:world.camera.position.toArray()};
  },
};
