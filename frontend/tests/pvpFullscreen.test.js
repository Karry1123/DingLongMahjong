import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createRenderer, h } from 'vue'
import { useFullscreen } from '../src/composables/useFullscreen.js'

const renderer=createRenderer({createElement:()=>({}),insert(){},remove(){},patchProp(){},setElementText(){},createText:()=>({}),createComment:()=>({}),setText(){},setComment(){},parentNode:()=>null,nextSibling:()=>null})
const flush=()=>new Promise(resolve=>setImmediate(resolve))
function setup(request,options={mobileFallback:true,autoEnter:true}){
  const original=Object.fromEntries(['document','window','navigator'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
  const classes=()=>{const values=new Set();return {toggle:(name,on)=>on?values.add(name):values.delete(name),remove:name=>values.delete(name),contains:name=>values.has(name)}}
  const doc=new EventTarget();doc.documentElement={classList:classes()};doc.body={classList:classes()}
  if(request)doc.documentElement.requestFullscreen=function(){return request(doc,this)}
  globalThis.document=doc;globalThis.window={matchMedia:()=>({matches:true})}
  Object.defineProperty(globalThis,'navigator',{value:{maxTouchPoints:1,userAgent:'MicroMessenger'},configurable:true})
  let controls
  const app=renderer.createApp({setup(){controls=useFullscreen(options);return()=>h('div')}});app.mount({})
  return {doc,controls,unmount:()=>app.unmount(),restore:()=>{app.unmount();for(const[key,value]of Object.entries(original)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}}}
}

test('mobile mount attempts native fullscreen synchronously, manual exit/reenter remains available',async()=>{
  let requests=0
  const f=setup((doc,element)=>{requests++;doc.fullscreenElement=element;return Promise.resolve()})
  f.doc.exitFullscreen=async()=>{f.doc.fullscreenElement=null}
  try{
    assert.equal(requests,1);await flush();assert.equal(f.controls.isFullscreen.value,true)
    assert.equal(f.controls.immersive.value,false)
    await f.controls.toggleFullscreen();assert.equal(f.controls.isFullscreen.value,false)
    await f.controls.toggleFullscreen();assert.equal(requests,2);assert.equal(f.controls.isFullscreen.value,true)
  }finally{f.restore()}
})

test('WebView rejection falls back to viewport fill, prevents page scrolling and cleans up',async()=>{
  const f=setup(()=>Promise.reject(new Error('User activation required')))
  try{
    await flush();assert.equal(f.controls.isFullscreen.value,true);assert.equal(f.controls.fullscreenError.value,'')
    assert.ok(f.doc.documentElement.classList.contains('pvp-immersive-fullscreen'))
    const move=new Event('touchmove',{cancelable:true});f.doc.dispatchEvent(move);assert.equal(move.defaultPrevented,true)
    await f.controls.toggleFullscreen();assert.equal(f.controls.isFullscreen.value,false)
    await f.controls.toggleFullscreen();assert.equal(f.controls.isFullscreen.value,true)
    f.unmount();assert.equal(f.doc.documentElement.classList.contains('pvp-immersive-fullscreen'),false)
    const after=new Event('touchmove',{cancelable:true});f.doc.dispatchEvent(after);assert.equal(after.defaultPrevented,false)
  }finally{f.restore()}
})

test('Safari WebKit fullscreen is bound to the root element; missing APIs still allow immersive mode',async()=>{
  const f=setup(undefined,{mobileFallback:true})
  try{
    f.doc.documentElement.webkitRequestFullscreen=function(){f.doc.webkitFullscreenElement=this}
    f.doc.webkitExitFullscreen=()=>{f.doc.webkitFullscreenElement=null}
    await f.controls.enterFullscreen();assert.equal(f.controls.isFullscreen.value,true)
    await f.controls.exitFullscreen();assert.equal(f.controls.isFullscreen.value,false)
    delete f.doc.documentElement.webkitRequestFullscreen
    await f.controls.enterFullscreen();assert.equal(f.controls.immersive.value,true)
  }finally{f.restore()}
})

test('unmount during a pending native request never adds a late immersive overlay',async()=>{
  let reject
  const f=setup(()=>new Promise((_,r)=>{reject=r}))
  try{f.unmount();reject(new Error('Too late'));await flush();assert.equal(f.doc.documentElement.classList.contains('pvp-immersive-fullscreen'),false)}finally{f.restore()}
})
