// Base de l'API : vide en local (meme origine), definie par window.CARTE_API quand le
// front est heberge separement (Vercel) et le back ailleurs.
const API=(typeof window!=='undefined'&&window.CARTE_API)?String(window.CARTE_API).replace(/\/$/,''):'';
const api=chemin=>API+chemin;

// Wrapper fetch : injecte Authorization: Bearer sur toutes les requetes vers l'API Railway
(function(){
    const _fetch=window.fetch.bind(window);
    window.fetch=function(url,opts){
          opts=opts||{};
          const token=(typeof window!=='undefined'&&window.CARTE_TOKEN)?String(window.CARTE_TOKEN):'';
          if(token&&API&&typeof url==='string'&&url.startsWith(API)){
                  const headers=new Headers(opts.headers||{});
                  if(!headers.has('Authorization'))headers.set('Authorization','Bearer '+token);
                  opts=Object.assign({},opts,{headers});
          }
          return _fetch(url,opts);
    };
})();

(function(){
  const panel=document.getElementById('railPanel'),title=document.getElementById('panelTitle');
  const btns=Array.from(document.querySelectorAll('.rbtn[data-pane]'));
  const panes=Array.from(document.querySelectorAll('.pane'));
  const NAMES={cams:'Cameras',sources:'Sources',photo:'Localiser une photo',
               chat:'Assistant',legend:'Legende'};
  let current=null;
  function show(key){
    if(current===key){close();return;}
    current=key;
    btns.forEach(b=>b.classList.toggle('on',b.dataset.pane===key));
    panes.forEach(p=>p.classList.toggle('on',p.dataset.pane===key));
    title.textContent=NAMES[key]||'';
    panel.classList.toggle('chatMode',key==='chat');
    panel.classList.add('show');
  }
  function close(){current=null;btns.forEach(b=>b.classList.remove('on'));panel.classList.remove('show');}
  btns.forEach(b=>b.addEventListener('click',()=>show(b.dataset.pane)));
  document.getElementById('panelX').addEventListener('click',close);
  document.getElementById('railCollapse').addEventListener('click',close);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')close();});
  document.getElementById('q').addEventListener('focus',()=>{if(current!=='cams')show('cams');});
})();
const map=L.map('map',{minZoom:2,preferCanvas:true,maxBounds:[[-85,-180],[85,180]],maxBoundsViscosity:1.0}).setView([50,8],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',{subdomains:'abcd',maxZoom:19,noWrap:true,bounds:[[-85,-180],[85,180]]}).addTo(map);
function clusterIcon(color){return function(c){var n=c.getChildCount();var s=n<10?26:n<100?32:38;return L.divIcon({html:'<div style="width:'+s+'px;height:'+s+'px;line-height:'+s+'px;border-radius:50%;background:rgba(8,10,12,.86);border:1px solid '+color+';color:'+color+';font-family:Consolas,monospace;font-weight:500;font-size:11px;text-align:center;box-shadow:0 0 0 4px '+color+'14,0 0 8px '+color+'40">'+n+'</div>',className:'',iconSize:[s,s]});};}
const clusterOptions=color=>({maxClusterRadius:60,iconCreateFunction:clusterIcon(color),
  chunkedLoading:true,chunkInterval:80,chunkDelay:16,animate:false,
  animateAddingMarkers:false,removeOutsideVisibleBounds:true,showCoverageOnHover:false});
const gE=L.markerClusterGroup(clusterOptions('#2f81f7')).addTo(map);
const gS=L.markerClusterGroup(clusterOptions('#2f81f7')).addTo(map);
const gX=L.markerClusterGroup(clusterOptions('#2f81f7')).addTo(map);
const gH=L.markerClusterGroup(clusterOptions('#2f81f7')).addTo(map);
const gW=L.markerClusterGroup(clusterOptions('#2f81f7')).addTo(map);
const gT=L.markerClusterGroup(clusterOptions('#2f81f7')).addTo(map);
const gF=L.markerClusterGroup(clusterOptions('#22d3a6')).addTo(map);
const gNY=L.markerClusterGroup(clusterOptions('#ff5a5f')).addTo(map);
const cableLayer=L.layerGroup().addTo(map);
const eventLayer=L.layerGroup().addTo(map);
const icon=(cls)=>L.divIcon({className:'',html:'<div class="cam '+cls+'"></div>',iconSize:[12,12],iconAnchor:[6,6]});
let DATA={youtube:[],skyline:[],taxi:[],hopper:[],hls:[],video:[],img:[],nydot:[]},markers={},q="";
const DATA_VERSION={},LAYER_TOKEN={};
const SOURCE_META={
  youtube:{route:'earthcam',stat:'sE',layer:gE,cls:'youtube'},
  skyline:{route:'skyline',stat:'sS',layer:gS,cls:'skyline'},
  taxi:{route:'webcamtaxi',stat:'sX',layer:gX,cls:'taxi'},
  hopper:{route:'webcamhopper',stat:'sH',layer:gH,cls:'hopper'},
  hls:{route:'whatsupcams',stat:'sW',layer:gW,cls:'hls'},
  video:{route:'tfl',stat:'sT',layer:gT,cls:'video'},
  img:{route:'finland',stat:'sF',layer:gF,cls:'img'},
  nydot:{route:'nydot',stat:'sNY',layer:gNY,cls:'nydot'}
};
const cameraDesk=document.getElementById('cameraDesk'),cameraWindows=new Map();
let cameraSerial=0,cameraZ=2000,ytReady=false,ytQ=[],activePersonTrackingState=null;
let city3dMap=null,city3dHandlersAdded=false,city3dTarget=[8,50],city3dFx=null;
let city3dCameraCount=0,city3dPopup=null;
const city3dCameraById=new Map();
const city3dFallbackHeight=['match',['get','building'],
  ['house','detached','semidetached_house','terrace','residential','bungalow','cabin','hut','shed','garage','garages'],8,
  ['apartments','dormitory','hotel'],24,
  ['office','commercial','retail','civic','public'],32,
  ['industrial','warehouse','school','university','hospital'],20,
  ['tower','skyscraper'],120,
  18];
const city3dHeight=['max',['coalesce',['to-number',['get','render_height']],city3dFallbackHeight],city3dFallbackHeight];
const city3dBase=['min',['coalesce',['to-number',['get','render_min_height']],0],city3dHeight];
// Style complet OpenFreeMap/OSM : rues, quartiers, villes, POI et adresses restent
// visibles. Les bâtiments 3D sont ajoutés séparément sous les libellés.
const city3dStyle='https://tiles.openfreemap.org/styles/liberty';
// Couleur des batiments par hauteur : base sombre ardoise -> sommets eclaires (relief lisible)
const city3dColor=['interpolate',['linear'],city3dHeight,
  0,'#16222f',12,'#243a4e',30,'#33506a',70,'#496f8f',140,'#6a94b8',260,'#9ac1e6'];
const city3dBuildingLayer={id:'city3d-buildings',source:'city3d-vector','source-layer':'building',type:'fill-extrusion',minzoom:12,
  filter:['!=',['get','hide_3d'],true],paint:{
    'fill-extrusion-color':city3dColor,'fill-extrusion-height':city3dHeight,'fill-extrusion-base':city3dBase,
    'fill-extrusion-opacity':1,'fill-extrusion-opacity-transition':{duration:0,delay:0},
    'fill-extrusion-vertical-gradient':true
  }};
window.onYouTubeIframeAPIReady=function(){ytReady=true;ytQ.forEach(f=>{try{f();}catch(e){}});ytQ=[];};
(function(){var t=document.createElement('script');t.src='https://www.youtube.com/iframe_api';document.head.appendChild(t);})();

function city3dLayerBefore(m){
  const layers=(m.getStyle()&&m.getStyle().layers)||[];
  for(let i=0;i<layers.length;i++){
    if(layers[i].type==='symbol'&&layers[i].layout&&layers[i].layout['text-field'])return layers[i].id;
  }
  return undefined;
}
function styleCity3d(m){
  const layers=(m.getStyle()&&m.getStyle().layers)||[];
  layers.forEach(l=>{
    try{
      if(l.type==='fill-extrusion'&&l.id!=='city3d-buildings'){
        m.setLayoutProperty(l.id,'visibility','none');
      }
      if(l.type==='line'&&/(road|street|highway|transport|path|rail)/i.test(l.id)){
        const major=/(motorway|trunk|primary|secondary|major|highway)/i.test(l.id);
        m.setPaintProperty(l.id,'line-color','#58f0ff');
        m.setPaintProperty(l.id,'line-opacity',major?0.88:0.52);
        m.setPaintProperty(l.id,'line-width',major?['interpolate',['linear'],['zoom'],12,1,17,3.4,19,5.2]:['interpolate',['linear'],['zoom'],12,.35,17,1.25,19,2.1]);
        m.setPaintProperty(l.id,'line-blur',major?.65:.25);
      }
      if(l.type==='background')m.setPaintProperty(l.id,'background-color','#04111d');
      if(l.type==='fill'){
        if(/water/i.test(l.id)){m.setPaintProperty(l.id,'fill-color','#061522');m.setPaintProperty(l.id,'fill-opacity',0.72);}
        else if(/land|park|background|earth|place/i.test(l.id)){m.setPaintProperty(l.id,'fill-color','#06111d');m.setPaintProperty(l.id,'fill-opacity',0.86);}
      }
      if(l.type==='symbol'){
        const hasText=l.layout&&l.layout['text-field']!==undefined;
        if(hasText){
          const place=/(place|city|town|village|state|country|settlement)/i.test(l.id);
          const road=/(road|street|highway|transport|path)/i.test(l.id);
          m.setLayoutProperty(l.id,'visibility','visible');
          m.setPaintProperty(l.id,'text-color',place?'#d8f7ff':(road?'#a9dce5':'#a8bdc5'));
          m.setPaintProperty(l.id,'text-halo-color','#04111d');
          m.setPaintProperty(l.id,'text-halo-width',place?2:1.35);
          m.setPaintProperty(l.id,'text-halo-blur',.35);
          m.setPaintProperty(l.id,'text-opacity',place?1:.9);
        }
      }
    }catch(e){}
  });
  try{m.setLight({anchor:'viewport',color:'#eaf6ff',intensity:.55,position:[1.3,205,32]});}catch(e){}
  // --- realisme keyless : occlusion ambiante, aretes arrondies, ciel/atmosphere, relief ---
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-ambient-occlusion-intensity',0.42);}catch(e){}
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-ambient-occlusion-radius',3.2);}catch(e){}
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-ambient-occlusion-ground-attenuation',0.55);}catch(e){}
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-edge-radius',0.55);}catch(e){}
  try{m.setSky({'sky-color':'#0a1c2e','sky-horizon-blend':0.6,'horizon-color':'#123049','horizon-fog-blend':0.7,'fog-color':'#04111d','fog-ground-blend':0.5,'atmosphere-blend':['interpolate',['linear'],['zoom'],0,0.7,10,0.25,14,0.05]});}catch(e){}
  try{
    if(!m.getSource('city3d-dem')){m.addSource('city3d-dem',{type:'raster-dem',encoding:'terrarium',tileSize:256,maxzoom:14,tiles:['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png']});}
    m.setTerrain({source:'city3d-dem',exaggeration:1.1});
  }catch(e){}
}
function initCity3DFx(){
  if(city3dFx||!window.THREE)return;
  const canvas=document.getElementById('city3dFx'),renderer=new THREE.WebGLRenderer({canvas:canvas,alpha:true,antialias:true});
  const scene=new THREE.Scene(),camera=new THREE.OrthographicCamera(-1,1,1,-1,0,10);
  camera.position.z=5;
  const cyan=new THREE.LineBasicMaterial({color:0x54e6ff,transparent:true,opacity:.12});
  const group=new THREE.Group();
  for(let i=0;i<18;i++){
    const y=-1.2+i*.145;
    const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-1.4,y,0),new THREE.Vector3(1.4,y,0)]);
    group.add(new THREE.Line(g,cyan));
  }
  for(let i=0;i<13;i++){
    const x=-1.4+i*.24;
    const g=new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,-1.2,0),new THREE.Vector3(x,1.2,0)]);
    group.add(new THREE.Line(g,cyan));
  }
  group.rotation.x=.92;group.position.y=-.2;scene.add(group);
  function resize(){const r=canvas.getBoundingClientRect();renderer.setPixelRatio(Math.min(devicePixelRatio||1,2));renderer.setSize(r.width,r.height,false);}
  function animate(t){resize();group.position.y=-.22+((t*.000025)%0.145);renderer.render(scene,camera);requestAnimationFrame(animate);}
  city3dFx={renderer,scene,camera};requestAnimationFrame(animate);
}
function ensureCity3dLayers(){
  const m=city3dMap;if(!m||!m.isStyleLoaded())return;
  styleCity3d(m);
  if(!m.getSource('city3d-vector'))m.addSource('city3d-vector',{type:'vector',url:'https://tiles.openfreemap.org/planet'});
  if(!m.getLayer('city3d-buildings'))m.addLayer(city3dBuildingLayer,city3dLayerBefore(m));
  m.setLayoutProperty('city3d-buildings','visibility','visible');
  m.setPaintProperty('city3d-buildings','fill-extrusion-color',city3dColor);
  m.setPaintProperty('city3d-buildings','fill-extrusion-opacity',1);
  m.setPaintProperty('city3d-buildings','fill-extrusion-vertical-gradient',true);
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-ambient-occlusion-intensity',0.42);}catch(e){}
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-ambient-occlusion-radius',3.2);}catch(e){}
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-ambient-occlusion-ground-attenuation',0.55);}catch(e){}
  try{m.setPaintProperty('city3d-buildings','fill-extrusion-edge-radius',0.55);}catch(e){}
  if(m.getLayer('city3d-building-lines'))m.removeLayer('city3d-building-lines');
  if(!m.getSource('city3d-target'))m.addSource('city3d-target',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
  if(!m.getLayer('city3d-target-halo'))m.addLayer({id:'city3d-target-halo',type:'circle',source:'city3d-target',paint:{
    'circle-radius':15,'circle-color':'rgba(217,166,72,0.12)','circle-stroke-color':'#d9a648','circle-stroke-width':1,
    'circle-pitch-alignment':'map','circle-pitch-scale':'map'
  }});
  if(!m.getLayer('city3d-target-point'))m.addLayer({id:'city3d-target-point',type:'circle',source:'city3d-target',paint:{
    'circle-radius':3.5,'circle-color':'#d9a648','circle-stroke-color':'#080a0c','circle-stroke-width':1.5,
    'circle-pitch-alignment':'map','circle-pitch-scale':'map'
  }});
  if(!m.getSource('city3d-cameras'))m.addSource('city3d-cameras',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
  if(!m.getLayer('city3d-camera-halo'))m.addLayer({id:'city3d-camera-halo',type:'circle',source:'city3d-cameras',paint:{
    'circle-radius':['interpolate',['linear'],['zoom'],12,5,16,10,20,18],
    'circle-color':['case',['==',['get','src'],'img'],'#22d3a6','#2f81f7'],
    'circle-opacity':.2,'circle-blur':.35,
    'circle-pitch-alignment':'map','circle-pitch-scale':'map'
  }});
  if(!m.getLayer('city3d-camera-points'))m.addLayer({id:'city3d-camera-points',type:'circle',source:'city3d-cameras',paint:{
    'circle-radius':['interpolate',['linear'],['zoom'],12,2.5,16,5.5,20,9],
    'circle-color':['case',['==',['get','src'],'img'],'#22d3a6','#2f81f7'],
    'circle-opacity':.98,'circle-stroke-color':'#06101a','circle-stroke-width':1.5,
    'circle-pitch-alignment':'map','circle-pitch-scale':'map'
  }});
  if(!city3dHandlersAdded){
    city3dHandlersAdded=true;
    m.on('mouseenter','city3d-camera-points',e=>{
      m.getCanvas().style.cursor='pointer';
      const f=e.features&&e.features[0];if(!f)return;
      if(city3dPopup)city3dPopup.remove();
      const title=document.createElement('b'),place=document.createElement('div'),box=document.createElement('div');
      title.textContent=f.properties.title||'Camera';place.textContent=f.properties.place||'';
      place.style.cssText='color:#7d8b98;margin-top:3px;font-size:11px';box.append(title,place);
      city3dPopup=new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12}).setLngLat(f.geometry.coordinates).setDOMContent(box).addTo(m);
    });
    m.on('mouseleave','city3d-camera-points',()=>{m.getCanvas().style.cursor='';if(city3dPopup){city3dPopup.remove();city3dPopup=null;}});
    m.on('click','city3d-camera-points',e=>{
      const f=e.features&&e.features[0],cam=f&&city3dCameraById.get(f.properties.uid);if(!cam)return;
      closeCity3D();setTimeout(()=>openCam(cam),80);
    });
  }
  updateCity3dCameras();
}
function city3dCameraGeoJSON(){
  const features=[];city3dCameraById.clear();
  for(const [key,meta] of Object.entries(SOURCE_META)){
    if(!map.hasLayer(meta.layer))continue;
    for(let index=0;index<DATA[key].length;index++){
      const c=DATA[key][index];
      if(q&&!c._search.includes(q))continue;
      const lat=Number(c.lat),lng=Number(c.lng);if(!Number.isFinite(lat)||!Number.isFinite(lng))continue;
      const uid=key+':'+String(c.id??index)+':'+lat+':'+lng;city3dCameraById.set(uid,c);
      features.push({type:'Feature',id:uid,geometry:{type:'Point',coordinates:[lng,lat]},properties:{
        uid:uid,src:c.src||key,title:c.title||'Camera',place:c.place||''
      }});
    }
  }
  city3dCameraCount=features.length;
  return {type:'FeatureCollection',features:features};
}
function updateCity3dTitle(){
  const lng=city3dTarget[0],lat=city3dTarget[1];
  document.getElementById('city3dTitle').textContent='Vue ville 3D  |  OSM haute precision  |  '+lat.toFixed(5)+', '+lng.toFixed(5)+'  |  '+city3dCameraCount+' cameras';
}
function updateCity3dCameras(){
  if(!city3dMap||!city3dMap.isStyleLoaded())return;
  const src=city3dMap.getSource('city3d-cameras');if(src)src.setData(city3dCameraGeoJSON());
  updateCity3dTitle();
}
function updateCity3dTarget(lng,lat){
  city3dTarget=[lng,lat];
  const src=city3dMap&&city3dMap.getSource('city3d-target');
  if(src)src.setData({type:'FeatureCollection',features:[{type:'Feature',geometry:{type:'Point',coordinates:[lng,lat]},properties:{}}]});
  updateCity3dTitle();
}
function openCity3D(lat,lng,zoom=17.45){
  if(!window.maplibregl){document.getElementById('city3dTitle').textContent='MapLibre indisponible';return;}
  const wrap=document.getElementById('city3d');wrap.classList.add('show');
  if(!city3dMap){
    city3dMap=new maplibregl.Map({container:'city3dMap',style:city3dStyle,
      center:[lng,lat],zoom:Math.max(10,Math.min(21.5,zoom)),minZoom:10,maxZoom:21.5,maxPitch:85,renderWorldCopies:false,pitch:64,bearing:-28,canvasContextAttributes:{antialias:true}});
    city3dMap.addControl(new maplibregl.NavigationControl({visualizePitch:true}),'bottom-right');
    city3dMap.addControl(new maplibregl.ScaleControl({maxWidth:130,unit:'metric'}),'bottom-left');
    city3dMap.on('load',()=>{ensureCity3dLayers();updateCity3dTarget(lng,lat);});
    
  }else{
    city3dMap.resize();
    ensureCity3dLayers();
    city3dMap.flyTo({center:[lng,lat],zoom:Math.max(10,Math.min(21.5,zoom)),pitch:64,bearing:-28,speed:1.4,curve:1.2});
    updateCity3dTarget(lng,lat);
  }
}
function closeCity3D(){document.getElementById('city3d').classList.remove('show');}
document.getElementById('city3dClose').onclick=closeCity3D;
map.on('click',e=>openCity3D(e.latlng.lat,e.latlng.lng));
map.on('overlayadd overlayremove',()=>updateCity3dCameras());
const city3dPreview=new URLSearchParams(location.search).get('city3d');
if(city3dPreview){const p=city3dPreview.split(',').map(Number);if(p.length>=2&&p.every(Number.isFinite))setTimeout(()=>openCity3D(p[0],p[1],p[2]||17.45),100);}

function cameraKey(c){return c.src+':'+String(c.id||c.url||c.title);}
function bringCameraFront(state){
  cameraZ++;state.el.style.zIndex=cameraZ;
  cameraWindows.forEach(s=>s.el.classList.toggle('focused',s===state));
}
function clampCameraWindow(state,left,top){
  const maxLeft=Math.max(0,cameraDesk.clientWidth-state.el.offsetWidth);
  const maxTop=Math.max(0,cameraDesk.clientHeight-state.el.offsetHeight);
  state.el.style.left=Math.max(0,Math.min(maxLeft,left))+'px';
  state.el.style.top=Math.max(0,Math.min(maxTop,top))+'px';
}
function makeCameraDraggable(state){
  const head=state.el.querySelector('.mhead');let drag=null;
  head.addEventListener('pointerdown',e=>{
    if(e.button!==0||e.target.closest('.x,button'))return;
    e.preventDefault();bringCameraFront(state);
    drag={x:e.clientX,y:e.clientY,left:state.el.offsetLeft,top:state.el.offsetTop,id:e.pointerId};
    head.setPointerCapture(e.pointerId);
  });
  head.addEventListener('pointermove',e=>{if(drag)clampCameraWindow(state,drag.left+e.clientX-drag.x,drag.top+e.clientY-drag.y);});
  const stop=e=>{if(!drag)return;try{head.releasePointerCapture(drag.id);}catch(_e){}drag=null;};
  head.addEventListener('pointerup',stop);head.addEventListener('pointercancel',stop);
}
function cleanupCameraMedia(state){
  if(state.ytPlayer){try{state.ytPlayer.destroy();}catch(e){}state.ytPlayer=null;}
  if(state.ytRevealTimer){clearTimeout(state.ytRevealTimer);state.ytRevealTimer=null;}
  if(state.hls){try{state.hls.destroy();}catch(e){}state.hls=null;}
  if(state.imgTimer){clearInterval(state.imgTimer);state.imgTimer=null;}
  state.vid.innerHTML='';
}
function stopPersonTracking(state){
  if(state.detectTimer){clearInterval(state.detectTimer);state.detectTimer=null;}
  if(state.detectLinkRaf){cancelAnimationFrame(state.detectLinkRaf);state.detectLinkRaf=null;}state.detectSeq=-1;
  const token=state.detectToken;state.detectToken=null;
  const postit=state.el.querySelector('.personPostit');if(postit)postit.remove();
  const link=state.el.querySelector('.personLink');if(link)link.remove();
  const badge=state.vid.querySelector('.personTrackingBadge');if(badge)badge.remove();
  const tboxes=state.vid.querySelector('.trackBoxes');if(tboxes)tboxes.remove();
  const plinks=state.content&&state.content.querySelector('.postitLinks');if(plinks)plinks.remove();
  if(state.content)state.content.querySelectorAll('.floatPostit').forEach(el=>el.remove());
  state.el.classList.remove('postit-active');
  if(token)fetch(api('/detect-stop?token=')+encodeURIComponent(token),{cache:'no-store',keepalive:true}).catch(()=>{});
  if(activePersonTrackingState===state)activePersonTrackingState=null;
  const b=state.el.querySelector('.yolo');if(b)b.textContent='SUIVI PERSONNE (POST-IT)';
  requestAnimationFrame(()=>clampCameraWindow(state,state.el.offsetLeft,state.el.offsetTop));
}
function closeCamera(state){
  if(!state||state.closed)return;state.closed=true;
  stopPersonTracking(state);cleanupCameraMedia(state);if(state.observer)state.observer.disconnect();
  cameraWindows.delete(state.key);state.el.remove();
}
function attachHls(state,video,url){
  if(!(window.Hls&&Hls.isSupported())){video.src=url;video.play().catch(()=>{});return;}
  const hls=new Hls({enableWorker:true,lowLatencyMode:false,capLevelToPlayerSize:true,
    startLevel:-1,maxBufferLength:30,maxMaxBufferLength:45,backBufferLength:15,
    liveSyncDurationCount:4,liveMaxLatencyDurationCount:10});
  state.hls=hls;hls.loadSource(url);hls.attachMedia(video);
  hls.on(Hls.Events.MANIFEST_PARSED,()=>video.play().catch(()=>{}));
  hls.on(Hls.Events.ERROR,(_event,data)=>{
    if(!data.fatal||state.closed||state.hls!==hls)return;
    if(data.type===Hls.ErrorTypes.NETWORK_ERROR)hls.startLoad();
    else if(data.type===Hls.ErrorTypes.MEDIA_ERROR)hls.recoverMediaError();
    else{hls.destroy();state.hls=null;}
  });
}
function revealYoutube(state){
  if(state.ytRevealTimer)clearTimeout(state.ytRevealTimer);
  state.ytRevealTimer=setTimeout(()=>{if(state.closed)return;const wrap=state.vid.querySelector('.ytclean.waiting');if(!wrap)return;wrap.classList.remove('waiting');const wait=wrap.querySelector('.ytwait');if(wait)wait.remove();state.ytRevealTimer=null;},5000);
}
async function resolveHls(id){
  const cd=[];for(let i=1;i<=10;i++)cd.push('cdn-'+String(i).padStart(3,'0'));
  const t=cd.map(c=>fetch('https://'+c+'.whatsupcams.com/hls/'+id+'.m3u8',{cache:'no-store'}).then(r=>r.status===200?r.text().then(x=>x.includes('#EXTM3U')?'https://'+c+'.whatsupcams.com/hls/'+id+'.m3u8':null):null).catch(()=>null));
  return (await Promise.all(t)).find(Boolean)||null;
}
function regionZoomTarget(container){return container.querySelector('.ytclean')||container.querySelector('video,img,iframe');}
function resetRegionZoom(container){
  const target=regionZoomTarget(container),overlay=container.querySelector('.zoomSelect');
  if(target)target.style.transform='';
  if(overlay){overlay.classList.remove('zoomed','selecting');const box=overlay.querySelector('.zoomBox');if(box)box.style.display='none';}
}
function enableRegionZoom(container){
  const target=regionZoomTarget(container);
  if(!target||container.querySelector('.zoomSelect'))return;
  target.classList.add('cameraZoomTarget');
  const overlay=document.createElement('div');
  overlay.className='zoomSelect';
  overlay.innerHTML='<div class="zoomHint">Glisser pour zoomer &middot; double-clic = vue complete</div><div class="zoomBox"></div><button class="zoomReset" type="button">Vue complete</button>';
  container.appendChild(overlay);
  const box=overlay.querySelector('.zoomBox'),reset=overlay.querySelector('.zoomReset');
  let drag=null;
  const point=e=>{const r=overlay.getBoundingClientRect();return{x:Math.max(0,Math.min(r.width,e.clientX-r.left)),y:Math.max(0,Math.min(r.height,e.clientY-r.top)),w:r.width,h:r.height};};
  const draw=p=>{const x=Math.min(drag.x,p.x),y=Math.min(drag.y,p.y),w=Math.abs(p.x-drag.x),h=Math.abs(p.y-drag.y);box.style.cssText='display:block;left:'+x+'px;top:'+y+'px;width:'+w+'px;height:'+h+'px';return{x,y,w,h};};
  overlay.addEventListener('pointerdown',e=>{
    if(e.button!==0||e.target===reset)return;
    e.preventDefault();drag=point(e);overlay.classList.add('selecting');box.style.cssText='display:block;left:'+drag.x+'px;top:'+drag.y+'px;width:0;height:0';overlay.setPointerCapture(e.pointerId);
  });
  overlay.addEventListener('pointermove',e=>{if(drag)draw(point(e));});
  const finish=e=>{
    if(!drag)return;const area=draw(point(e));drag=null;overlay.classList.remove('selecting');
    try{overlay.releasePointerCapture(e.pointerId);}catch(_e){}
    if(area.w<18||area.h<18){box.style.display='none';return;}
    const z=Math.min(16,Math.max(1,Math.min(overlay.clientWidth/area.w,overlay.clientHeight/area.h)));
    const tx=(overlay.clientWidth-area.w*z)/2-area.x*z,ty=(overlay.clientHeight-area.h*z)/2-area.y*z;
    target.style.transform='translate('+tx+'px,'+ty+'px) scale('+z+')';
    overlay.classList.add('zoomed');box.style.display='none';
  };
  overlay.addEventListener('pointerup',finish);overlay.addEventListener('pointercancel',()=>{drag=null;overlay.classList.remove('selecting');box.style.display='none';});
  overlay.addEventListener('dblclick',e=>{e.preventDefault();resetRegionZoom(container);});
  overlay.addEventListener('contextmenu',e=>{e.preventDefault();resetRegionZoom(container);});
  reset.addEventListener('pointerdown',e=>e.stopPropagation());reset.addEventListener('click',e=>{e.stopPropagation();resetRegionZoom(container);});
}
function setCameraMessage(state,message){if(!state.closed)state.vid.innerHTML='<div class="msg">'+message+'</div>';}
function openCameraStream(state){
  const c=state.cam,mVid=state.vid;
  if(c.src==='youtube'){
    mVid.innerHTML='<div class="ytclean waiting"><div class="ytp"></div><div class="ytblock"></div><div class="msg ytwait">Connexion au flux en direct...</div></div>';
    const host=mVid.querySelector('.ytp');
    const make=()=>{if(state.closed||!host.isConnected)return;state.ytPlayer=new YT.Player(host,{videoId:c.id,width:'100%',height:'100%',playerVars:{autoplay:1,mute:1,controls:0,modestbranding:1,rel:0,iv_load_policy:3,fs:0,disablekb:1,playsinline:1,showinfo:0},events:{onReady:e=>{e.target.playVideo();revealYoutube(state);}}});};
    if(ytReady&&window.YT&&YT.Player){make();}else{ytQ.push(make);}
  } else if(c.src==='hopper'){
    setCameraMessage(state,'Connexion au flux WebcamHopper...');
    fetch(api('/api/webcamhopper-stream?id=')+encodeURIComponent(c.id)+'&url='+encodeURIComponent(c.url),{cache:'no-store'}).then(r=>r.json()).then(j=>{
      if(state.closed)return;if(!j.ok||!j.url){setCameraMessage(state,'Camera hors ligne.');return;}
      if(j.kind==='hls'){
        mVid.innerHTML='<video autoplay muted playsinline controls></video>';
        attachHls(state,mVid.querySelector('video'),j.url);return;
      }
      if(j.kind==='video'){mVid.innerHTML='<video autoplay muted loop playsinline controls></video>';mVid.querySelector('video').src=j.url;return;}
      let source=j.url,isYoutube=false;
      try{const u=new URL(source);isYoutube=u.hostname.includes('youtube.com')||u.hostname.includes('youtube-nocookie.com')||u.hostname==='youtu.be';if(isYoutube){u.searchParams.set('autoplay','1');u.searchParams.set('mute','1');u.searchParams.set('controls','0');u.searchParams.set('modestbranding','1');u.searchParams.set('rel','0');u.searchParams.set('iv_load_policy','3');u.searchParams.set('fs','0');u.searchParams.set('disablekb','1');u.searchParams.set('playsinline','1');source=u.toString();}}catch(e){}
      if(isYoutube){mVid.innerHTML='<div class="ytclean waiting"><iframe allow="autoplay; encrypted-media; picture-in-picture"></iframe><div class="ytblock"></div><div class="msg ytwait">Connexion au flux en direct...</div></div>';}
      else{mVid.innerHTML='<iframe allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>';}
      const frame=mVid.querySelector('iframe');if(isYoutube)frame.onload=()=>revealYoutube(state);frame.src=source;
    }).catch(()=>setCameraMessage(state,'Camera hors ligne.'));
  } else if(c.src==='taxi'){
    setCameraMessage(state,'Connexion au flux WebCamTaxi...');
    fetch(api('/api/webcamtaxi-stream?url=')+encodeURIComponent(c.url),{cache:'no-store'}).then(r=>r.json()).then(j=>{
      if(state.closed)return;if(!j.ok||!j.url){setCameraMessage(state,'Camera hors ligne.');return;}
      let source=j.url,isYoutube=false;
      try{const u=new URL(source);isYoutube=u.hostname.includes('youtube.com')||u.hostname.includes('youtube-nocookie.com')||u.hostname==='youtu.be';if(isYoutube){u.searchParams.set('autoplay','1');u.searchParams.set('mute','1');u.searchParams.set('controls','0');u.searchParams.set('modestbranding','1');u.searchParams.set('rel','0');u.searchParams.set('iv_load_policy','3');u.searchParams.set('fs','0');u.searchParams.set('disablekb','1');u.searchParams.set('playsinline','1');source=u.toString();}}catch(e){}
      if(isYoutube){mVid.innerHTML='<div class="ytclean waiting"><iframe allow="autoplay; encrypted-media; picture-in-picture"></iframe><div class="ytblock"></div><div class="msg ytwait">Connexion au flux en direct...</div></div>';}
      else{mVid.innerHTML='<iframe allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe>';}
      const frame=mVid.querySelector('iframe');if(isYoutube)frame.onload=()=>revealYoutube(state);frame.src=source;
    }).catch(()=>setCameraMessage(state,'Camera hors ligne.'));
  } else if(c.src==='skyline'){
    setCameraMessage(state,'Connexion au flux SkylineWebcams...');
    fetch(api('/api/skyline-stream?url=')+encodeURIComponent(c.url),{cache:'no-store'}).then(r=>r.json()).then(j=>{
      if(state.closed)return;if(!j.ok||!j.url){setCameraMessage(state,'Camera hors ligne.');return;}
      mVid.innerHTML='<video autoplay muted playsinline controls></video>';
      attachHls(state,mVid.querySelector('video'),j.url);
    }).catch(()=>setCameraMessage(state,'Camera hors ligne.'));
  } else if(c.src==='hls'){
    setCameraMessage(state,'Recherche du flux live...');
    resolveHls(c.id).then(url=>{
      if(state.closed)return;if(!url){setCameraMessage(state,'Camera hors ligne.');return;}
      mVid.innerHTML='<video autoplay muted playsinline controls></video>';
      attachHls(state,mVid.querySelector('video'),url);
    });
  } else if(c.src==='video'){
    mVid.innerHTML='<video autoplay muted loop playsinline controls></video>';mVid.querySelector('video').src=c.url;
  } else if(c.src==='nydot'){
    mVid.innerHTML='<video autoplay muted playsinline controls></video>';
    attachHls(state,mVid.querySelector('video'),c.url);
  } else if(c.src==='img'){
    mVid.innerHTML='<img>';
    const iv=mVid.querySelector('img'),load=()=>{if(!state.closed)iv.src=c.url+(c.url.includes('?')?'&':'?')+'_t='+Date.now();};
    load();state.imgTimer=setInterval(load,3000);
  }
}
function openCam(c){
  const key=cameraKey(c),existing=cameraWindows.get(key);if(existing){bringCameraFront(existing);return;}
  const el=document.createElement('div');el.className='cameraWindow';
  el.innerHTML='<div class="mhead"><b class="mName"></b><span class="live">LIVE</span><img class="skylogo" src="https://cdn.jsdelivr.net/gh/SkylineWebcams/web@v2/skylinewebcams.svg" alt="SkylineWebcams"><img class="hopperlogo" src="https://www.webcamhopper.com/image/site_name.svg" alt="WebcamHopper"><span class="x" title="Fermer">&times;</span></div><div class="cameraContent"><div class="vid"></div><aside class="personDock"></aside></div><div class="note"><button class="yolo" type="button">SUIVI LIVE (POST-IT)</button><span class="mPlace"></span></div>';
  cameraDesk.appendChild(el);
  const state={key,cam:c,el,content:el.querySelector('.cameraContent'),vid:el.querySelector('.vid'),dock:el.querySelector('.personDock'),hls:null,imgTimer:null,ytPlayer:null,ytRevealTimer:null,observer:null,detectTimer:null,detectToken:null,detectLinkRaf:null,detectSeq:-1,closed:false};
  cameraWindows.set(key,state);el.querySelector('.mName').textContent=c.title;el.querySelector('.mPlace').textContent=c.place;
  el.querySelector('.skylogo').style.display=c.src==='skyline'?'block':'none';el.querySelector('.hopperlogo').style.display=c.src==='hopper'?'block':'none';
  const yolo=el.querySelector('.yolo');yolo.style.display='inline-block';
  el.querySelector('.x').addEventListener('click',e=>{e.stopPropagation();closeCamera(state);});
  yolo.addEventListener('click',()=>launchDetect(state));el.addEventListener('pointerdown',()=>bringCameraFront(state));
  makeCameraDraggable(state);state.observer=new MutationObserver(()=>requestAnimationFrame(()=>enableRegionZoom(state.vid)));state.observer.observe(state.vid,{childList:true});
  const n=cameraSerial++,left=(window.innerWidth>900?300:12)+(n%7)*28,top=64+(n%7)*28;clampCameraWindow(state,left,top);bringCameraFront(state);openCameraStream(state);
}
document.addEventListener('keydown',e=>{if(e.key==='Escape')closeCity3D();});
window.addEventListener('resize',()=>cameraWindows.forEach(s=>clampCameraWindow(s,s.el.offsetLeft,s.el.offsetTop)));
function attachPersonPostit(state,info){
  if(activePersonTrackingState&&activePersonTrackingState!==state)stopPersonTracking(activePersonTrackingState);
  stopPersonTracking(state);activePersonTrackingState=state;state.detectToken=info.token;
  state.el.classList.add('postit-active');
  const svgns='http://www.w3.org/2000/svg';
  const badge=document.createElement('div');badge.className='personTrackingBadge';badge.textContent='Suivi multi-objets · cadre intact';state.vid.appendChild(badge);
  const boxSvg=document.createElementNS(svgns,'svg');boxSvg.classList.add('trackBoxes');boxSvg.setAttribute('preserveAspectRatio','none');state.vid.appendChild(boxSvg);
  const linkSvg=document.createElementNS(svgns,'svg');linkSvg.classList.add('postitLinks');linkSvg.setAttribute('preserveAspectRatio','none');state.content.appendChild(linkSvg);
  const FR={person:'PERSONNE',car:'VOITURE',truck:'CAMION',bus:'BUS',motorcycle:'MOTO',bicycle:'VELO',boat:'BATEAU',airplane:'AVION',train:'TRAIN',bird:'OISEAU',cat:'CHAT',dog:'CHIEN',horse:'CHEVAL',sheep:'MOUTON',cow:'VACHE',elephant:'ELEPHANT',bear:'OURS',zebra:'ZEBRE',giraffe:'GIRAFE'};
  const cards=new Map();
  // rectangles verts sur la video (tous les sujets du groupe prioritaire)
  const drawBoxes=meta=>{
    const bx=(meta&&meta.boxes)||[],fw=Number(meta&&meta.frame_w||0),fh=Number(meta&&meta.frame_h||0);
    if(!fw||!fh||!bx.length){boxSvg.innerHTML='';return;}
    const vr=state.vid.getBoundingClientRect();let w=vr.width,h=vr.height,left=0,top=0;const sa=fw/fh,da=w/Math.max(1,h);
    if(da>sa){const cw=h*sa;left=(w-cw)/2;w=cw;}else{const ch=w/sa;top=(h-ch)/2;h=ch;}
    let s='';for(const b of bx){const rx=left+b[0]/fw*w,ry=top+b[1]/fh*h,rw=(b[2]-b[0])/fw*w,rh=(b[3]-b[1])/fh*h;
      s+='<rect x="'+rx.toFixed(1)+'" y="'+ry.toFixed(1)+'" width="'+Math.max(1,rw).toFixed(1)+'" height="'+Math.max(1,rh).toFixed(1)+'" rx="1.5" class="tb'+(b[5]===meta.track_id?' foc':'')+'"></rect>';}
    boxSvg.innerHTML=s;
  };
  // point (px,py) du cadre source -> coordonnees dans .content (gere le letterbox)
  const mapPoint=(fw,fh,px,py)=>{
    const cr=state.content.getBoundingClientRect(),vr=state.vid.getBoundingClientRect();
    let w=vr.width,h=vr.height,left=vr.left-cr.left,top=vr.top-cr.top;const sa=fw/fh,da=w/Math.max(1,h);
    if(da>sa){const cw=h*sa;left+=(w-cw)/2;w=cw;}else{const ch=w/sa;top+=(h-ch)/2;h=ch;}
    return {x:left+px/fw*w,y:top+py/fh*h};
  };
  // petits post-its flottants AUTOUR du cadre + fil vert vers chaque sujet
  const layout=meta=>{
    const subs=(meta&&meta.subjects)||[],fw=Number(meta&&meta.frame_w||0),fh=Number(meta&&meta.frame_h||0);
    const cr=state.content.getBoundingClientRect();const present=new Set(),cw=104,chh=150,gap=10;let paths='';
    subs.forEach((su,i)=>{
      present.add(su.id);
      let c=cards.get(su.id);
      if(!c){const el=document.createElement('div');el.className='floatPostit';el.innerHTML='<img alt=""><span class="fpLbl"></span>';state.content.appendChild(el);c={el:el,img:el.querySelector('img'),lbl:el.querySelector('.fpLbl'),last:''};cards.set(su.id,c);}
      if(c.last!==su.thumb){c.img.src=su.thumb;c.last=su.thumb;}
      c.lbl.textContent=(FR[su.cls]||(su.cls||'').toUpperCase())+' #'+su.id;
      const side=i%2,idx=Math.floor(i/2);
      const cx=side===0?(cr.width+14):(-cw-14),cy=6+idx*(chh+gap);
      c.el.style.left=cx.toFixed(0)+'px';c.el.style.top=cy.toFixed(0)+'px';
      if(!fw||!fh)return;
      const cur=((meta.boxes)||[]).find(b=>b[5]===su.id);
      const bx=cur?[(cur[0]+cur[2])/2,(cur[1]+cur[3])/2]:[(su.box[0]+su.box[2])/2,(su.box[1]+su.box[3])/2];
      const p=mapPoint(fw,fh,bx[0],bx[1]),sx=side===0?cx:cx+cw,sy=cy+66,mx=(sx+p.x)/2;
      paths+='<path d="M '+sx.toFixed(1)+' '+sy.toFixed(1)+' C '+mx.toFixed(1)+' '+sy.toFixed(1)+', '+mx.toFixed(1)+' '+p.y.toFixed(1)+', '+p.x.toFixed(1)+' '+p.y.toFixed(1)+'"></path><circle cx="'+p.x.toFixed(1)+'" cy="'+p.y.toFixed(1)+'" r="3.5"></circle>';
    });
    for(const [id,c] of cards){if(!present.has(id)){c.el.remove();cards.delete(id);}}
    linkSvg.innerHTML=paths;
  };
  const refresh=()=>{if(state.closed||state.detectToken!==info.token)return;fetch(info.meta_url+'?t='+Date.now(),{cache:'no-store'}).then(r=>r.json()).then(meta=>{
    drawBoxes(meta);layout(meta);
  }).catch(()=>{});};
  state.detectTimer=setInterval(refresh,80);refresh();
}
function launchDetect(state){
  if(!state||state.closed)return;const cam=state.cam,b=state.el.querySelector('.yolo');
  let q2='src='+cam.src;
  if(cam.src==='hls'||cam.src==='youtube')q2+='&id='+encodeURIComponent(cam.id);
  else{q2+='&url='+encodeURIComponent(cam.url);if(cam.id!==undefined&&cam.id!==null)q2+='&id='+encodeURIComponent(cam.id);}
  b.textContent='Ouverture du post-it...';
  fetch(api('/detect?')+q2+'&title='+encodeURIComponent(cam.title)).then(r=>r.json()).then(j=>{
    if(state.closed){if(j&&j.token)fetch(api('/detect-stop?token=')+encodeURIComponent(j.token),{keepalive:true}).catch(()=>{});return;}if(j.ok){attachPersonPostit(state,j);b.textContent='POST-IT ACTIF';}
    else{b.textContent='Flux tiers non analysable';setTimeout(()=>{if(!state.closed)b.textContent='RELANCER LE POST-IT';},4500);}
  }).catch(()=>{if(state.closed)return;b.textContent='Erreur';setTimeout(()=>{if(!state.closed)b.textContent='RELANCER LE POST-IT';},4000);});
}
let searchTimer=null,renderFrame=null,pollBusy=false;
document.getElementById('q').addEventListener('input',e=>{
  const value=e.target.value.trim().toLocaleLowerCase();
  clearTimeout(searchTimer);searchTimer=setTimeout(()=>{q=value;scheduleRender();},140);
});
function scheduleRender(){
  if(renderFrame!==null)return;
  renderFrame=requestAnimationFrame(()=>{renderFrame=null;render();});
}
function prepareCams(cams){
  for(const c of cams)c._search=((c.title||'')+' '+(c.place||'')).toLocaleLowerCase();
  return cams;
}
function render(){
  const all=DATA.youtube.concat(DATA.skyline,DATA.taxi,DATA.hopper,DATA.hls,DATA.video,DATA.img,DATA.nydot);
  const shown=all.filter(c=>!q||c._search.includes(q));
  const list=document.getElementById('list'),fragment=document.createDocumentFragment();
  const col={youtube:'var(--blue)',skyline:'var(--blue)',taxi:'var(--blue)',hopper:'var(--blue)',hls:'var(--blue)',video:'var(--blue)',img:'var(--teal)',nydot:'#ff5a5f'};
  shown.slice(0,400).forEach(c=>{
    const d=document.createElement('div');d.className='item';
    const led=document.createElement('span'),body=document.createElement('div'),title=document.createElement('b'),place=document.createElement('span');
    led.className='led';led.style.background=col[c.src];led.style.boxShadow='0 0 6px '+col[c.src];
    title.textContent=c.title||'';place.textContent=c.place||'';body.append(title,place);d.append(led,body);
    d.onclick=()=>{map.setView([c.lat,c.lng],Math.max(map.getZoom(),9),{animate:true});openCam(c);};
    fragment.appendChild(d);
  });
  list.replaceChildren(fragment);
  for(const [key,meta] of Object.entries(SOURCE_META))draw(DATA[key],meta.layer,meta.cls,key);
  updateCity3dCameras();
}
const MAX_MARKERS=2500;   // plafond par source affiche en meme temps (fluidite)
function boundsToken(){const b=map.getBounds();return map.getZoom().toFixed(0)+'|'+[b.getSouth(),b.getWest(),b.getNorth(),b.getEast()].map(v=>v.toFixed(1)).join(',');}
function draw(arr,layer,cls,key){
  // On n'affiche que les cameras du cadre visible (+ marge), plafonnees : fluide meme avec des dizaines de milliers.
  const token=(DATA_VERSION[key]||'0')+'|'+q+'|'+boundsToken();
  if(LAYER_TOKEN[key]===token)return;
  LAYER_TOKEN[key]=token;
  layer.clearLayers();
  const vb=map.getBounds().pad(0.25);
  let shown=arr.filter(c=>(!q||c._search.includes(q))&&vb.contains([c.lat,c.lng]));
  if(shown.length>MAX_MARKERS)shown=shown.slice(0,MAX_MARKERS);
  const batch=shown.map(c=>{
    const markerId=key+':'+c.id;let m=markers[markerId];
    if(!m){m=L.marker([c.lat,c.lng],{icon:icon(cls),title:c.title,keyboard:false});m.on('click',()=>openCam(m._cam));markers[markerId]=m;}
    else{const pos=m.getLatLng();if(pos.lat!==c.lat||pos.lng!==c.lng)m.setLatLng([c.lat,c.lng]);}
    m._cam=c;
    return m;
  });
  layer.addLayers(batch);
}
map.on('moveend',()=>scheduleRender());
async function poll(){
  if(pollBusy)return;pollBusy=true;
  try{
    const response=await fetch(api('/api/status'),{cache:'no-store'});if(!response.ok)return;
    const status=await response.json(),jobs=[];
    for(const [key,meta] of Object.entries(SOURCE_META)){
      const info=(status.sources||{})[key]||{},version=String(info.updated||0);
      document.getElementById(meta.stat).textContent=info.count||0;
      if(DATA_VERSION[key]===undefined||DATA_VERSION[key]!==version){
        jobs.push(fetch(api('/api/')+meta.route,{cache:'no-store'}).then(r=>{
          if(!r.ok)throw new Error('HTTP '+r.status);return r.json();
        }).then(data=>{DATA[key]=prepareCams(data.cams||[]);DATA_VERSION[key]=version;return true;}).catch(()=>false));
      }
    }
    const changed=await Promise.all(jobs);if(changed.some(Boolean))scheduleRender();
  }catch(e){}finally{pollBusy=false;}
}
async function loadCables(){
  try{const gj=await(await fetch(api('/api/cables'),{cache:'no-store'})).json();const n=(gj.features||[]).length;if(!n){setTimeout(loadCables,5000);return;}cableLayer.clearLayers();L.geoJSON(gj,{style:f=>({color:(f.properties&&f.properties.color)||'#39c',weight:1,opacity:.5})}).addTo(cableLayer);document.getElementById('sC').textContent=n;}catch(e){document.getElementById('sC').textContent='0';setTimeout(loadCables,5000);}
}
// ---- Evenements (militaire/meteo) + panneau droit ----
function evtIcon(cat){return L.divIcon({className:'',iconSize:[12,12],iconAnchor:[6,6],html:'<div class="evt '+cat+'"></div>'});}
function fmtDate(d){if(!d)return'';if(/^\d{8}T/.test(d))return d.slice(0,4)+'-'+d.slice(4,6)+'-'+d.slice(6,8)+' '+d.slice(9,11)+':'+d.slice(11,13);return d.replace('T',' ').replace('Z','').slice(0,16);}
function openEvent(ev){
  const p=document.getElementById('evp'),c=document.getElementById('evpCat');
  const CATLAB={militaire:'MILITAIRE / SECURITE',conflit:'CONFLIT (ACLED)',feu:'FRAPPE / FEU (FIRMS)',seisme:'SEISME (USGS)',catastrophe:'CATASTROPHE (GDACS)',info:'ACTUALITE MONDIALE',meteo:'METEO / NATURE'};
  c.textContent=CATLAB[ev.cat]||'EVENEMENT';c.className='cat '+ev.cat;
  let h='<h3>'+ev.title+'</h3><div class="date">'+(ev.type||'')+(ev.date?' &#183; '+fmtDate(ev.date):'')+'</div>';
  if(ev.img)h+='<img src="'+ev.img+'" onerror="this.style.display=&#39;none&#39;">';
  if(ev.desc)h+='<p class="tsl">'+ev.desc+'</p>';
  const hasTxt=ev.desc||(ev.articles&&ev.articles.length);
  if(hasTxt)h+='<a class="trad" onclick="toggleTrad(this);return false;">traduire</a>';
  if(ev.articles&&ev.articles.length){h+='<div style="font-family:var(--mono);font-size:9px;letter-spacing:1px;color:var(--dim);text-transform:uppercase;margin-top:14px">Articles</div>';ev.articles.forEach(a=>{h+='<div class="art"><a class="tsl" href="'+a.u+'" target="_blank" rel="noopener">'+(a.t||a.u)+'</a></div>';});}
  else if(ev.url)h+='<div class="art"><a href="'+ev.url+'" target="_blank" rel="noopener">Source &#8599;</a></div>';
  document.getElementById('evpBody').innerHTML=h;p.classList.add('show');
}
async function toggleTrad(link){
  const els=document.querySelectorAll('#evpBody .tsl');
  if(link.dataset.state==='tr'){els.forEach(e=>{if(e.dataset.orig!==undefined)e.textContent=e.dataset.orig;});link.textContent='traduire';link.dataset.state='';return;}
  link.textContent='traduction...';
  await Promise.all([...els].map(async e=>{
    const o=(e.dataset.orig!==undefined)?e.dataset.orig:e.textContent;e.dataset.orig=o;
    try{const r=await(await fetch(api('/translate?tl=fr&q=')+encodeURIComponent(o))).json();if(r.ok&&r.text)e.textContent=r.text;}catch(x){}
  }));
  link.textContent="voir l'original";link.dataset.state='tr';
}
document.getElementById('evpX').onclick=()=>document.getElementById('evp').classList.remove('show');
let EVENTS_VERSION=null;
async function pollEvents(){
  try{
    const r=await(await fetch(api('/api/events'),{cache:'no-store'})).json();
    const version=String(r.updated||0);if(EVENTS_VERSION===version)return;EVENTS_VERSION=version;
    const list=r.list||[];
    eventLayer.clearLayers();
    list.forEach(ev=>{const m=L.marker([ev.lat,ev.lng],{icon:evtIcon(ev.cat),title:ev.title,zIndexOffset:1000});m.on('click',()=>openEvent(ev));m.addTo(eventLayer);});
    const se=document.getElementById('sEv');if(se)se.textContent=list.length;
  }catch(e){}
}
pollEvents();setInterval(pollEvents,120000);
// ---- Reconnaissance de lieu sur photo (GeoCLIP + modele vision local) ----
const photoLayer=L.layerGroup().addTo(map);
(function(){
  const drop=document.getElementById('geoDrop'),input=document.getElementById('geoFile');
  const prev=document.getElementById('geoPrev'),img=document.getElementById('geoImg'),rm=document.getElementById('geoRm');
  const go=document.getElementById('geoGo'),status=document.getElementById('geoStatus'),res=document.getElementById('geoRes');
  const vlmChk=document.getElementById('geoVlm');
  let dataUrl=null,busy=false;
  const esc=v=>String(v===undefined||v===null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function confLevel(s){return s>=0.05?'elevee':(s>=0.02?'moyenne':'faible');}
  function say(msg,isErr){status.textContent=msg||'';status.className='geoStatus'+(isErr?' err':'');}
  function setImage(file){
    if(!file||!/^image\//.test(file.type||'')){say('Format non reconnu : choisis une image.',true);return;}
    if(file.size>22*1024*1024){say('Image trop lourde (22 Mo maximum).',true);return;}
    const r=new FileReader();
    r.onload=()=>{dataUrl=r.result;window.lastGeoImage=dataUrl;img.src=dataUrl;prev.style.display='block';go.disabled=false;say('');res.style.display='none';};
    r.readAsDataURL(file);
  }
  drop.addEventListener('click',()=>input.click());
  input.addEventListener('change',e=>setImage(e.target.files&&e.target.files[0]));
  ['dragenter','dragover'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('over');}));
  ['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('over');}));
  drop.addEventListener('drop',e=>{const dt=e.dataTransfer;if(dt&&dt.files&&dt.files[0])setImage(dt.files[0]);});
  rm.addEventListener('click',()=>{dataUrl=null;window.lastGeoImage=null;window.lastGeoResult=null;img.removeAttribute('src');prev.style.display='none';go.disabled=true;res.style.display='none';say('');photoLayer.clearLayers();input.value='';});
  function pin(rank){return L.divIcon({className:'photoPin',iconSize:[24,24],iconAnchor:[12,24],html:'<div><span>'+rank+'</span></div>'});}
  function terrainHtml(te){
    const ok=te.confirmes>0;
    let s='<div class="ck '+(ok?'ok':'ko')+'"><b>OpenStreetMap &middot; '+esc(te.verdict||'')+'</b>';
    if(ok)s+=te.confirmes+' element(s) attendus retrouves sur place : '
      +(te.trouves||[]).slice(0,5).map(t=>esc(t.nom)+(t.type?' ('+esc(t.type)+')':'')).join(', ');
    else s+='aucun des elements lus sur les panneaux ('+esc((te.cherches||[]).join(', '))
      +') n\'existe autour de cette position';
    return s+'</div>';
  }
  function pollTerrain(token){
    if(!token)return;
    let tries=0;
    const MAX=70;                       // ~6 min : les serveurs Overpass publics sont lents
    const fin=html=>{const box=document.getElementById('ckTerrain');if(box)box.outerHTML=html;};
    const tick=()=>{
      if(++tries>MAX){
        fin('<div class="ck ko">Confrontation a OpenStreetMap abandonnee : les serveurs publics '
           +'n\'ont pas repondu en 6 minutes. Relance l\'analyse plus tard.</div>');
        return;
      }
      fetch(api('/api/photo-verify?token=')+encodeURIComponent(token),{cache:'no-store'})
        .then(x=>x.json()).then(j=>{
          if(j.status!=='done'){
            const box=document.getElementById('ckTerrain');
            if(box)box.textContent='Confrontation a OpenStreetMap en cours... ('+(tries*5)+' s)';
            setTimeout(tick,5000);return;
          }
          const te=j.result||{};
          fin(te.erreur?('<div class="ck ko">OpenStreetMap indisponible : '+esc(te.erreur)+'</div>')
                       :terrainHtml(te));
        }).catch(()=>setTimeout(tick,6000));
    };
    setTimeout(tick,3000);
  }
  const num=v=>(typeof v==='number'&&isFinite(v))?v:null;
  const hasPos=o=>!!o&&num(o.lat)!==null&&num(o.lng)!==null;
  const fmtPos=o=>hasPos(o)?(o.lat.toFixed(5)+', '+o.lng.toFixed(5)):'position non geocodee';
  function focusOn(lat,lng,zoom){
    if(num(lat)===null||num(lng)===null)return;
    map.setView([lat,lng],zoom||11,{animate:true});
  }
  function render(r){
    photoLayer.clearLayers();
    let h='';
    const exif=hasPos(r.exif)?r.exif:null;
    if(exif){
      h+='<div class="geoHead">Coordonnees GPS de la photo</div>';
      h+='<div class="exact"><b>Position exacte (EXIF)</b><span>'+esc(exif.place||'Lieu non resolu')+'<br>'+fmtPos(exif)+'</span></div>';
      const m=L.marker([exif.lat,exif.lng],{icon:pin('E')}).addTo(photoLayer);
      m.bindTooltip('GPS EXIF · '+(exif.place||''),{direction:'top',offset:[0,-18]});
    }
    const cands=(r.candidates||[]).filter(hasPos);
    const arb=r.arbiter;
    const leads=r.leads||null,clus=leads&&hasPos(leads.cluster)?leads.cluster:null;
    const best=hasPos(r.best)?r.best:null;
    if(best&&!exif){
      const rejet=arb&&arb.rang===0;
      h+='<div class="geoHead">Reponse'+(arb?' &middot; '+esc(arb.model||''):'')+'</div>';
      h+='<div class="verdict'+(rejet?' rejet':'')+'"><b>'+esc(best.place||'Lieu indetermine')+'</b>'
        +(arb&&arb.confiance?'<span class="conf '+arb.confiance+'">confiance '+arb.confiance+'</span>':'')
        +(rejet?'<div class="warn">Aucune zone proposee par GeoCLIP ne colle aux indices : la lecture des panneaux prend le dessus.</div>':'')
        +(arb&&arb.raison?'<p>'+esc(arb.raison)+'</p>':'')
        +'<div class="co">'+fmtPos(best)+' &middot; source : '+esc(best.source||'')+'</div></div>';
    }
    if(leads&&(leads.points||[]).length){
      h+='<div class="geoHead">Pistes toponymiques &middot; noms lus sur les panneaux</div><div class="leads">';
      if(clus)h+='<div class="clus">'+esc(clus.noms.join(' + '))+' se rejoignent &agrave; moins de 40 km &mdash; preuve forte</div>';
      leads.points.filter(hasPos).forEach(p=>{
        const inClus=clus&&clus.noms.indexOf(p.nom)>=0;
        h+='<div class="lead'+(inClus?' hot':'')+'" data-lat="'+p.lat+'" data-lng="'+p.lng+'"><b>'+esc(p.nom)+'</b><span>'+fmtPos(p)+'</span></div>';
        const mk=L.marker([p.lat,p.lng],{icon:pin('T')}).addTo(photoLayer);
        mk.bindTooltip('Toponyme lu : '+p.nom,{direction:'top',offset:[0,-18]});
      });
      h+='</div>';
    }
    if(cands.length){
      const best=cands[0].score;
      h+='<div class="geoHead">Zones candidates &middot; <span class="conf '+confLevel(best)+'">signal '+confLevel(best)+'</span></div>';
      cands.forEach((c,i)=>{
        const pct=(c.score*100);
        h+='<div class="cand'+(c.chosen?' chosen':'')+'" data-lat="'+c.lat+'" data-lng="'+c.lng+'">'
          +'<div class="top"><span class="rk">#'+(i+1)+'</span><span class="nm">'+esc(c.place||'Lieu non resolu')+'</span>'
          +(c.chosen?'<span class="ok">retenu</span>':(c.agree?'<span class="ok">accord IA</span>':''))+'<span class="pc">'+pct.toFixed(1)+'%</span></div>'
          +'<div class="co">'+c.lat.toFixed(5)+', '+c.lng.toFixed(5)+'</div>'
          +'<div class="bar"><i style="width:'+Math.max(3,Math.min(100,pct/best*100))+'%"></i></div></div>';
        const m=L.marker([c.lat,c.lng],{icon:pin(i+1)}).addTo(photoLayer);
        m.bindTooltip('#'+(i+1)+' · '+pct.toFixed(1)+'% · '+(c.place||''),{direction:'top',offset:[0,-18]});
        m.on('click',()=>focusOn(c.lat,c.lng,12));
      });
    }else if(!r.exif){
      h+='<div class="geoHead">Aucune estimation</div><div class="geoStatus err">'+esc(r.geoclip_error||'GeoCLIP indisponible')+'</div>';
    }
    const ocr=r.ocr||{},sclip=r.streetclip||{};
    if((ocr.textes||[]).length||(sclip.pays||[]).length){
      h+='<div class="geoHead">Lecture directe &middot; OCR et second modele</div><div class="checks">';
      if((ocr.textes||[]).length)h+='<div class="ck"><b>Textes lus ('+esc(ocr.moteur||'OCR')+')</b>'
        +ocr.textes.map(t=>'<code>'+esc(t.texte)+'</code><s>'+Math.round(t.score*100)+'%</s>').join(' ')+'</div>';
      else if(ocr.erreur)h+='<div class="ck ko">OCR indisponible : '+esc(ocr.erreur)+'</div>';
      if((sclip.pays||[]).length)h+='<div class="ck"><b>StreetCLIP &middot; pays probable</b>'
        +sclip.pays.map(p=>esc(p.nom)+' '+Math.round(p.score*100)+'%').join(' &middot; ')+'</div>';
      h+='</div>';
    }
    const ch=r.checks||{};
    if(ch.terrain||ch.meteo||ch.soleil||ch.appariement||(ch.cameras||[]).length){
      h+='<div class="geoHead">Verifications sur le terrain</div><div class="checks">';
      const te=ch.terrain;
      if(te){
        if(te.status==='en cours')h+='<div class="ck wait" id="ckTerrain">Confrontation a OpenStreetMap en cours ('+esc((te.cherches||[]).join(', '))+')...</div>';
        else if(te.erreur)h+='<div class="ck ko">OpenStreetMap indisponible : '+esc(te.erreur)+'</div>';
        else h+=terrainHtml(te);
      }
      if(ch.meteo&&!ch.meteo.erreur){
        const ok=ch.meteo.coherent;
        h+='<div class="ck '+(ok===false?'ko':(ok?'ok':''))+'"><b>Meteo du '+esc(ch.meteo.date||'')+'</b>'+esc(ch.meteo.resume||'')
          +(ch.meteo.alerte?'<i>'+esc(ch.meteo.alerte)+'</i>':'')+'</div>';
      }
      if(ch.soleil&&!ch.soleil.erreur){
        const ok=ch.soleil.coherent;
        h+='<div class="ck '+(ok===false?'ko':(ok?'ok':''))+'"><b>Soleil</b>'+esc(ch.soleil.moment||'')
          +' &middot; azimut '+ch.soleil.azimut+'&deg;, hauteur '+ch.soleil.hauteur+'&deg;'
          +(ch.soleil.alerte?'<i>'+esc(ch.soleil.alerte)+'</i>':'')+'</div>';
      }
      if(ch.appariement&&!ch.appariement.erreur){
        const n=ch.appariement.correspondances||0;
        h+='<div class="ck '+(n>=30?'ok':(n>=12?'':'ko'))+'"><b>Appariement geometrique</b>'
          +n+' point(s) commun(s) avec la camera '+esc(ch.appariement.camera||'')+' ('+ch.appariement.km+' km) &mdash; '
          +esc(ch.appariement.verdict||'')+'</div>';
      }
      (ch.cameras||[]).forEach(c=>{
        h+='<div class="ck cam" data-lat="'+c.lat+'" data-lng="'+c.lng+'"><b>Camera publique a '+c.km+' km</b>'
          +esc(c.titre||c.lieu||'')+' &middot; '+esc(c.source)+'</div>';
      });
      h+='</div>';
    }
    const meta=r.metadata,fo=r.forensics;
    if(meta||fo){
      h+='<div class="geoHead">Authenticite du fichier</div><div class="checks">';
      if(meta&&meta.exif&&Object.keys(meta.exif).length){
        h+='<div class="ck"><b>Appareil</b>'+Object.entries(meta.exif).slice(0,6)
          .map(([k,x])=>esc(k)+' : '+esc(x)).join(' &middot; ')+'</div>';
      }
      ((meta&&meta.alertes)||[]).concat((fo&&fo.alertes)||[]).forEach(a=>{
        h+='<div class="ck warn2">'+esc(a)+'</div>';
      });
      if(fo&&fo.ela_moyen!==null&&fo.ela_moyen!==undefined){
        h+='<div class="ck"><b>Compression</b>qualite estimee '+(fo.qualite_estimee!==undefined?fo.qualite_estimee+'%':'?')
          +' &middot; ELA moyen '+fo.ela_moyen+' (max '+fo.ela_max+')</div>';
      }
      h+='</div>';
    }
    const v=r.vlm;
    if(v){
      h+='<div class="geoHead">Indices visuels &middot; '+esc(v.model||'')+(v.provider?' ('+esc(v.provider)+')':'')+'</div><div class="vlmBox">';
      const lieu=[v.lieu,v.ville,v.region,v.pays].filter(Boolean).join(', ');
      if(lieu)h+='<div class="row"><s>Lieu propose</s>'+esc(lieu)+'</div>';
      if(hasPos(v))h+='<div class="row"><s>Geocode</s>'+fmtPos(v)+'</div>';
      if(v.textes&&v.textes.length)h+='<div class="row"><s>Textes lus sur place</s>'+v.textes.map(x=>'<code>'+esc(x)+'</code>').join(' ')+'</div>';
      if(v.confiance)h+='<div class="row"><s>Confiance du modele</s>'+esc(v.confiance)+'</div>';
      if(v.indices&&v.indices.length)h+='<ul>'+v.indices.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>';
      if(!lieu&&!(v.indices||[]).length)h+='<div class="row">Le modele n\'a rien pu tirer de l\'image.</div>';
      h+='</div>';
      if(hasPos(v)){
        const m=L.marker([v.lat,v.lng],{icon:pin('V')}).addTo(photoLayer);
        m.bindTooltip('Proposition du modele vision · '+(v.query||''),{direction:'top',offset:[0,-18]});
      }
    }else if(r.vlm_error){
      h+='<div class="geoHead">Indices visuels</div><div class="geoStatus err">'+esc(r.vlm_error)+'</div>';
    }
    res.innerHTML=h;res.style.display='block';
    res.querySelectorAll('.cand,.lead,.ck.cam').forEach(el=>el.addEventListener('click',()=>focusOn(+el.dataset.lat,+el.dataset.lng,12)));
    pollTerrain(r.verify_token);
    (ch.cameras||[]).forEach(c=>{
      const mk=L.marker([c.lat,c.lng],{icon:pin('C')}).addTo(photoLayer);
      mk.bindTooltip('Camera publique · '+(c.titre||'')+' · '+c.km+' km',{direction:'top',offset:[0,-18]});
    });
    const first=[exif,best,clus,cands[0]].find(hasPos);
    if(first)focusOn(first.lat,first.lng,exif?14:(first.precision==='lieu nomme'?12:9));
  }
  async function locate(){
    if(!dataUrl||busy)return;
    busy=true;go.disabled=true;res.style.display='none';
    say(vlmChk.checked?'Analyse en cours... (premier lancement : chargement des modeles, jusqu\'a 1 min)':'Analyse en cours...');
    const t0=Date.now();
    try{
      const lance=await(await fetch(api('/api/geolocate'),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:dataUrl,vlm:vlmChk.checked,top_k:5,progressif:true})})).json();
      if(lance.ok===false)throw new Error(lance.error||'echec');
      // resultats au fil de l'eau : chaque etape s'affiche des qu'elle est prete
      const r=await new Promise((resolve,reject)=>{
        let tours=0;
        const tick=async()=>{
          if(++tours>200)return reject(new Error('analyse trop longue'));
          try{
            const j=await(await fetch(api('/api/photo-progress?token=')+encodeURIComponent(lance.token),
              {cache:'no-store'})).json();
            if(j.status==='error')return reject(new Error(j.error||'echec'));
            if(j.status==='done')return resolve(j.result);
            if(j.result&&Object.keys(j.result).length){
              lastResult=j.result;window.lastGeoResult=j.result;
              try{render(j.result);}catch(e){}
              say('Analyse : '+(j.etape||'en cours')+'... '+((Date.now()-t0)/1000).toFixed(0)+' s');
            }
            setTimeout(tick,1200);
          }catch(e){setTimeout(tick,2000);}
        };
        tick();
      });
      lastResult=r;window.lastGeoResult=r;showActions(true);
      try{render(r);}
      catch(err){                       // un souci d'affichage ne doit pas effacer le resultat
        console.error('render geolocalisation',err,r);
        res.innerHTML='<div class="geoStatus err">Affichage partiel : '+esc(err.message||err)+'</div>'
          +'<pre style="white-space:pre-wrap;font:9px var(--mono);color:var(--dim);margin-top:8px">'
          +esc(JSON.stringify(r,null,1).slice(0,1500))+'</pre>';
        res.style.display='block';
      }
      say('Analyse terminee en '+((Date.now()-t0)/1000).toFixed(1)+' s');
    }catch(e){console.error('geolocalisation',e);say('Echec : '+(e.message||e),true);}
    finally{busy=false;go.disabled=!dataUrl;}
  }
  go.addEventListener('click',locate);
  // ---- dossier d'enquete, anonymisation, lot ----
  let lastResult=null;
  const actions=document.getElementById('geoActions');
  function showActions(on){actions.style.display=on?'flex':'none';}
  showActions(false);
  document.getElementById('geoSave').addEventListener('click',async()=>{
    if(!lastResult||!dataUrl)return;
    const note=prompt('Note pour ce dossier (facultatif)')||'';
    say('Enregistrement...');
    try{
      const j=await(await fetch(api('/api/photo-save'),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:dataUrl,result:lastResult,note:note})})).json();
      if(!j.ok)throw new Error(j.error||'echec');
      say('Dossier '+j.id+' enregistre');
      window.open('/api/photo-report?id='+encodeURIComponent(j.id),'_blank');
      loadCases();
    }catch(e){say('Echec enregistrement : '+(e.message||e),true);}
  });
  document.getElementById('geoAnon').addEventListener('click',async()=>{
    if(!dataUrl)return;
    say('Floutage en cours...');
    try{
      const j=await(await fetch(api('/api/photo-anonymize'),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({image:dataUrl})})).json();
      if(!j.ok)throw new Error(j.erreur||'echec');
      say(j.floutes+' objet(s) floute(s) - '+j.fichier);
      if(j.apercu){img.src=j.apercu;dataUrl=j.apercu;}
    }catch(e){say('Echec floutage : '+(e.message||e),true);}
  });
  const batchOut=document.getElementById('batchOut');
  document.getElementById('batchGo').addEventListener('click',async()=>{
    const dir=document.getElementById('batchDir').value.trim();
    if(!dir)return;
    batchOut.textContent='Lancement...';
    await fetch(api('/api/photo-batch'),{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({folder:dir,vlm:vlmChk.checked,save:true})});
    const tick=async()=>{
      const s=await(await fetch(api('/api/photo-batch'),{cache:'no-store'})).json();
      if(s.error){batchOut.textContent='Erreur : '+s.error;return;}
      batchOut.innerHTML='<b>'+s.done+' / '+s.total+'</b>'+(s.results||[]).map(x=>
        '<div class="brow">'+esc(x.fichier)+' &rarr; '+esc(x.lieu||x.erreur||'?')+'</div>').join('');
      if(s.status==='running')setTimeout(tick,2500);else loadCases();
    };
    setTimeout(tick,1500);
  });
  async function loadCases(){
    try{
      const j=await(await fetch(api('/api/photo-cases'),{cache:'no-store'})).json();
      document.getElementById('casesOut').innerHTML=(j.cases||[]).map(c=>
        '<a class="case" href="/api/photo-report?id='+encodeURIComponent(c.id)+'" target="_blank">'
        +'<b>'+esc(c.lieu||'sans lieu')+'</b><span>'+esc(c.date)+'</span></a>').join('')
        ||'<div class="brow">Aucun dossier enregistre</div>';
    }catch(e){}
  }
  document.getElementById('casesBox').addEventListener('toggle',e=>{if(e.target.open)loadCases();});
  fetch(api('/api/geo-status'),{cache:'no-store'}).then(r=>r.json()).then(s=>{
    const miss=[];
    if(!s.geoclip)miss.push('GeoCLIP absent (pip install geoclip)');
    if(s.provider==='ollama'&&!s.ollama)miss.push('Ollama hors ligne');
    else if(!s.vlm_ready)miss.push(s.provider==='ollama'?('modele vision absent (ollama pull '+s.vlm_model+')'):('cle API '+s.provider+' manquante'));
    if(miss.length)say(miss.join(' | '),true);
    else say('Moteurs : GeoCLIP + '+s.vlm_model+' ('+s.provider+')');
  }).catch(()=>{});
})();
window.lastGeoResult=null;window.lastGeoImage=null;
// ---- Assistant : questions sur ce que l'app voit (camera ouverte ou photo analysee) ----
(function(){
  const log=document.getElementById('chatLog'),input=document.getElementById('chatInput');
  const send=document.getElementById('chatSend'),ctxBox=document.getElementById('chatCtx');
  const esc=v=>String(v==null?'':v).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let history=[],busy=false;
  function focusedCamera(){
    let cible=null,dernier=null;
    cameraWindows.forEach(s=>{if(!s.closed){dernier=s;if(s.el.classList.contains('focused'))cible=s;}});
    return cible||dernier;
  }
  function majContexte(){
    const cam=focusedCamera();
    if(cam){ctxBox.textContent='Camera : '+(cam.cam.title||cam.cam.place||'sans titre');ctxBox.className='chatCtx on';}
    else if(typeof lastGeoResult!=='undefined'&&lastGeoResult){
      const b=lastGeoResult.best||{};
      ctxBox.textContent='Photo analysee : '+(b.place||'lieu indetermine');ctxBox.className='chatCtx on';
    }else{ctxBox.textContent='Aucun contexte : ouvre une camera ou analyse une photo';ctxBox.className='chatCtx';}
  }
  setInterval(majContexte,1500);majContexte();
  const heure=()=>new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'});
  function ajoute(role,texte,options){
    const d=document.createElement('div');
    d.className='chatMsg '+(role==='user'?'moi':'ia')+((options&&options.attente)?' attente':'');
    if(options&&options.attente){
      d.innerHTML='<span class="pointilles"><i></i><i></i><i></i></span>';
    }else{
      d.innerHTML=esc(texte)+'<span class="heure">'+heure()+'</span>';
    }
    log.appendChild(d);log.scrollTop=log.scrollHeight;return d;
  }
  function remplit(bulle,texte,source){
    bulle.classList.remove('attente');
    bulle.innerHTML=esc(texte)+(source?'<span class="src">'+esc(source)+'</span>':'')
      +'<span class="heure">'+heure()+'</span>';
    log.scrollTop=log.scrollHeight;
  }
  async function envoyer(){
    const q=input.value.trim();
    if(!q||busy)return;
    busy=true;send.disabled=true;input.value='';
    ajoute('user',q);
    const cam=focusedCamera();
    let image=null,camera=null,contexte={};
    if(cam){
      // capture cote serveur : un canvas alimente par un autre domaine est inexportable
      camera={src:cam.cam.src,url:cam.cam.url,id:cam.cam.id};
      contexte.camera=(cam.cam.title||'')+' — '+(cam.cam.place||'');
    }else if(window.lastGeoResult){
      Object.assign(contexte,window.lastGeoResult);
      image=window.lastGeoImage||null;
    }
    const attente=ajoute('bot','',{attente:true});
    try{
      const r=await(await fetch(api('/api/chat'),{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({question:q,image:image,camera:camera,context:contexte,history:history,
          vue:{lat:map.getCenter().lat,lng:map.getCenter().lng,zoom:map.getZoom()}})})).json();
      if(!r.ok)throw new Error(r.error||'echec');
      attente.innerHTML=esc(r.texte)+'<i>'+esc(r.modele)
        +(r.avec_image?' &middot; sur l\'image de la camera'
                      :' &middot; sans image'+(r.note_image?' ('+esc(r.note_image)+')':''))+'</i>';
      history.push({role:'user',text:q},{role:'assistant',text:r.texte});
      if(history.length>12)history=history.slice(-12);
    }catch(e){
      attente.classList.remove('attente');
      attente.innerHTML='<span class="err">Echec : '+esc(e.message||e)+'</span>'
        +'<span class="heure">'+heure()+'</span>';
    }finally{busy=false;send.disabled=false;input.focus();}
  }
  send.addEventListener('click',envoyer);
  input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();envoyer();}});
  input.addEventListener('input',()=>{input.style.height='auto';
    input.style.height=Math.min(120,input.scrollHeight)+'px';});
})();
poll();setInterval(poll,30000);loadCables();
