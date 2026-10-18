import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createWebPlatform, TOKEN_KEY } from '../src/platform/web.js'
import { createNativePlatform } from '../src/platform/native.js'
import { isNative, initializeNative, secureSession } from '../src/platform/index.js'
import { assertMobileApiBase } from '../src/services/apiBase.js'
import { registerBackDismiss, handleAndroidBack } from '../src/platform/androidBack.js'
import { createRealtimeConnection, pauseRealtimeConnections, resumeRealtimeConnections } from '../src/utils/realtimeConnection.js'

function nativeMock() {
  const calls = [], listeners = new Map(), values = new Map([[TOKEN_KEY, 'persisted']])
  const record = name => async value => { calls.push([name, value]) }
  const plugins = {
    Preferences: { async get({ key }) { return { value: values.get(key) } }, async set({key,value}) { values.set(key,value) }, async remove({ key }) { values.delete(key) } },
    ScreenOrientation: { lock:record('lock'), unlock:record('unlock') },
    App: { async addListener(name, callback) { listeners.set(name,callback); return { async remove() { listeners.delete(name) } } }, exitApp:record('exit') },
    Haptics: { selectionStart:record('selection-start'), selectionEnd:record('selection-end'), selectionChanged:record('selection'), impact:record('impact') },
    KeepAwake: { keepAwake:record('awake'), allowSleep:record('sleep') },
    StatusBar: { setStyle:record('style'), setBackgroundColor:record('background'), hide:record('hide'), show:record('show'), setOverlaysWebView:record('overlay') },
  }
  return { plugins, calls, listeners, values, platform:createNativePlatform(plugins) }
}

test('web token storage and lifecycle keep the existing key, unsubscribe cleanly', async () => {
  const values = new Map(), doc = new EventTarget(); doc.visibilityState = 'visible'
  const browser = { document:doc, localStorage: { getItem:key => values.get(key), setItem:(key,value) => values.set(key,value), removeItem:key => values.delete(key) } }
  const p = createWebPlatform(browser)
  p.secureSession.set('web-token'); assert.equal(values.get(TOKEN_KEY),'web-token'); assert.equal(p.secureSession.get(),'web-token')
  p.secureSession.clear(); assert.equal(p.secureSession.get(),'')
  let resumes=0, pauses=0
  const offResume=p.lifecycle.onResume(() => resumes++), offPause=p.lifecycle.onPause(() => pauses++)
  doc.visibilityState='hidden'; doc.dispatchEvent(new Event('visibilitychange'))
  doc.visibilityState='visible'; doc.dispatchEvent(new Event('visibilitychange'))
  assert.equal(resumes,1); assert.equal(pauses,1)
  offResume(); offPause(); doc.dispatchEvent(new Event('visibilitychange')); assert.equal(resumes,1)
  assert.equal(await p.orientation.enterTable(),false)
  await p.orientation.leaveTable(); await p.haptics.selection(); await p.haptics.impact(); await p.statusBar.dark()
  assert.equal(typeof p.backButton.subscribe(() => {}),'function')
})

test('web keepAwake shares the existing wake-lock sentinel across table owners', async () => {
  const doc=new EventTarget(), browser=new EventTarget(); doc.visibilityState='visible'; browser.document=doc
  let requested=0, released=0
  browser.navigator={wakeLock:{async request() { requested++; return {released:false,addEventListener(){}, async release(){released++}} }}}
  const p=createWebPlatform(browser)
  await p.keepAwake.acquire(); await p.keepAwake.acquire(); assert.equal(requested,1)
  await p.keepAwake.release(); assert.equal(released,0)
  await p.keepAwake.release(); assert.equal(released,1)
})

test('native Preferences hydration and ordered writes never use localStorage', async () => {
  const {platform:p,values}=nativeMock()
  await p.secureSession.ready(); assert.equal(p.secureSession.get(),'persisted')
  const save=p.secureSession.set('native-token'); assert.equal(p.secureSession.get(),'native-token')
  const clear=p.secureSession.clear(); assert.equal(p.secureSession.get(),'')
  await Promise.all([save,clear]); assert.equal(values.has(TOKEN_KEY),false)
})

test('native plugin failures fall back, overlapping table owners release once', async () => {
  const {platform:p,calls,plugins}=nativeMock()
  await p.orientation.enterTable(); await p.orientation.enterTable(); await p.orientation.leaveTable()
  assert.equal(calls.filter(([name]) => name==='unlock').length,0)
  await p.orientation.leaveTable()
  assert.deepEqual(calls.slice(0,2),[['lock',{orientation:'landscape'}],['unlock',undefined]])
  plugins.ScreenOrientation.lock=async () => { throw Error('unsupported') }
  assert.equal(await p.orientation.enterTable(),false); await p.orientation.leaveTable()
  await p.keepAwake.acquire(); await p.keepAwake.acquire(); await p.keepAwake.release(); await p.keepAwake.release()
  assert.deepEqual(calls.filter(([name]) => ['awake','sleep'].includes(name)).map(([name]) => name),['awake','sleep'])
  await p.haptics.selection(); await p.haptics.impact(); await p.statusBar.dark()
  assert.ok(calls.some(([name,value]) => name==='style' && value.style==='DARK'))
  assert.ok(calls.some(([name,value]) => name==='background' && value.color==='#06221D'))
})

test('native listeners remove even when disposed before asynchronous registration', async () => {
  const {platform:p,listeners,calls}=nativeMock(); let resumed=0,paused=0,back=0
  const off=p.lifecycle.onResume(() => resumed++), offPause=p.lifecycle.onPause(() => paused++), offBack=p.backButton.subscribe(() => back++)
  await Promise.resolve(); await Promise.resolve()
  listeners.get('resume')(); listeners.get('pause')(); listeners.get('backButton')()
  assert.deepEqual([resumed,paused,back],[1,1,1]); await off(); await offPause(); await offBack()
  await Promise.resolve(); await Promise.resolve(); assert.equal(listeners.size,0)
  await p.lifecycle.onResume(() => {})(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
  assert.equal(listeners.size,0); await p.backButton.exit(); assert.equal(calls.at(-1)[0],'exit')
})

test('native detection and initialization expose a hydrated session', async () => {
  const previous=globalThis.Capacitor
  try {
    assert.equal(isNative(),false)
    globalThis.Capacitor={isNativePlatform:() => true}
    const {plugins}=nativeMock(); await initializeNative(plugins)
    assert.equal(isNative(),true); assert.equal(secureSession.get(),'persisted')
  } finally { globalThis.Capacitor=previous }
})

test('App endpoints reject relative, insecure and loopback addresses', () => {
  for (const url of ['', '/api','http://example.com','https://localhost','https://127.0.0.2','https://[::1]','https://0.0.0.0','https://foo.localhost','https://user:pass@example.com']) assert.throws(() => assertMobileApiBase(url))
  assert.equal(assertMobileApiBase('https://api.example.com/'),'https://api.example.com')
})

test('Android back closes the top layer, confirms games, navigates, exits at root', async () => {
  const calls=[], router={options:{history:{state:{back:'/home'}}},back(){calls.push('back')},async replace(path){calls.push(path)}}
  const options={router,route:{path:'/invite'},exit:async () => calls.push('exit')}
  const lower=registerBackDismiss(() => {calls.push('lower');return true}), upper=registerBackDismiss(() => {calls.push('upper');return true})
  await handleAndroidBack(options); assert.deepEqual(calls,['upper']); upper(); lower(); calls.length=0
  await handleAndroidBack(options); assert.deepEqual(calls,['back']); calls.length=0
  await handleAndroidBack({...options,route:{path:'/pve'},inGame:true,confirm:() => false}); assert.deepEqual(calls,[])
  await handleAndroidBack({...options,route:{path:'/home'}}); assert.deepEqual(calls,['exit']); calls.length=0
  router.options.history.state.back=null; await handleAndroidBack(options); assert.deepEqual(calls,['/home'])
})

test('foreground restarts authenticated sockets; disposed sockets never resurrect', () => {
  const sockets=[]
  class Socket { constructor(){this.readyState=1;sockets.push(this)} close(){} send(){} }
  const c=createRealtimeConnection({url:'wss://example.com', Socket, onMessage(){}, schedule:() => 0,cancel(){}})
  try {
    c.start(); assert.equal(sockets.length,1)
    pauseRealtimeConnections(); assert.equal(c.send({}),false)
    resumeRealtimeConnections(); assert.equal(sockets.length,2)
    pauseRealtimeConnections(); c.stop(); resumeRealtimeConnections(); assert.equal(sockets.length,2)
  } finally { c.stop(); resumeRealtimeConnections() }
})

test('App resume revalidates /me and active match before sockets; logged-out resume permits later login', async () => {
  const { createRenderer } = await import('vue')
  const { useAppLifecycle } = await import('../src/composables/useAppLifecycle.js')
  const { auth, clearAuth } = await import('../src/stores/auth.js')
  const { clearActiveMatch, activeMatch } = await import('../src/stores/activeMatch.js')
  const originalFetch=globalThis.fetch, originalCapacitor=globalThis.Capacitor
  const {plugins,listeners}=nativeMock(), requests=[], sockets=[]
  const tick=() => new Promise(resolve => setImmediate(resolve))
  class Socket { constructor(){this.readyState=1;sockets.push(this)} close(){} send(){} }
  const createConnection=() => createRealtimeConnection({url:'wss://example.com', Socket,onMessage(){},schedule:() => 0,cancel(){}})
  let app, connection, later
  try {
    globalThis.Capacitor={isNativePlatform:() => true}; await initializeNative(plugins)
    auth.token='native-test'; auth.restored=true; auth.user={id:'user'}
    globalThis.fetch=async url => {
      requests.push(new URL(url).pathname)
      const data=new URL(url).pathname==='/api/me' ? {id:'user',active_match_id:'active-1'} : {match:{id:'active-1',status:'playing'}}
      return {ok:true,status:200,json:async () => data}
    }
    const renderer=createRenderer({createComment:() => ({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
    app=renderer.createApp({setup(){useAppLifecycle();return () => null}}); app.mount({}); await tick()
    connection=createConnection(); connection.start(); assert.equal(sockets.length,1)
    listeners.get('pause')(); listeners.get('resume')(); await tick()
    assert.deepEqual(requests,['/api/me','/api/matches/active-1']); assert.equal(activeMatch.match.id,'active-1'); assert.equal(sockets.length,2)
    await clearAuth(); connection.stop(); listeners.get('pause')(); listeners.get('resume')(); await tick()
    later=createConnection(); later.start(); assert.equal(sockets.length,3)
    app.unmount(); await tick(); assert.equal(listeners.size,0)
  } finally {
    app?.unmount(); connection?.stop(); later?.stop(); resumeRealtimeConnections(); clearActiveMatch(); await clearAuth()
    globalThis.fetch=originalFetch; globalThis.Capacitor=originalCapacitor
  }
})


test('status bar immersive ownership orders rapid enter/leave and tolerates plugin failures', async () => {
  const { platform:p, calls, plugins } = nativeMock()
  await Promise.all([p.statusBar.enterTable(), p.statusBar.enterTable(), p.statusBar.leaveTable()])
  assert.deepEqual(calls, [['overlay', { overlay:true }], ['hide', undefined]])
  await p.statusBar.leaveTable()
  await p.statusBar.leaveTable()
  assert.deepEqual(calls.slice(2), [['overlay', { overlay:false }], ['show', undefined]])
  calls.length = 0
  await Promise.all([p.statusBar.enterTable(), p.statusBar.leaveTable(), p.statusBar.enterTable(), p.statusBar.leaveTable()])
  assert.deepEqual(calls.map(([name]) => name), ['overlay','hide','overlay','show','overlay','hide','overlay','show'])
  plugins.StatusBar.setOverlaysWebView = async () => { throw Error('edge to edge') }
  await p.statusBar.enterTable(); await p.statusBar.leaveTable()
  assert.equal(calls.at(-1)[0], 'show')
  plugins.StatusBar.hide = plugins.StatusBar.show = async () => { throw Error('unsupported') }
  await p.statusBar.enterTable(); await p.statusBar.leaveTable()
  const web = createWebPlatform()
  await web.statusBar.enterTable(); await web.statusBar.leaveTable()
})
