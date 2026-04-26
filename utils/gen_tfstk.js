// utils/gen_tfstk.js
// node 补环境生成 tfstk。核心策略：
// 1. vm.createContext + 深度 Proxy 记录 SDK 每一个属性访问
// 2. crypto.subtle 同步化（绕 VMP setTimeout race）
// 3. 缺失属性从 env_snapshot.json（真浏览器 dump）回填
//
// 用法：
//   node utils/gen_tfstk.js              → stdout 输出 tfstk
//   node utils/gen_tfstk.js --probe      → 输出 SDK 访问日志（用于定位缺失环境）

const fs   = require('fs');
const path = require('path');
const vm   = require('vm');
const nodeCrypto = require('crypto');

const PROBE = process.argv.includes('--probe');
const ET_PATH = path.join(__dirname, 'et_f.js');

// ═══════════ 1. 同步化 crypto.subtle ═══════════
function syncThenable(v) {
  return {
    then(ok, fail) {
      try { const r = ok ? ok(v) : v; return (r && typeof r.then === 'function') ? r : syncThenable(r); }
      catch (e) { return fail ? syncThenable(fail(e)) : syncThenable(undefined); }
    },
    catch(f) { return this; },
    finally(f) { try { f && f(); } catch(e) {} return this; },
  };
}
function fakeCryptoKey(raw, algo, usages) {
  return { _raw: Buffer.from(raw), algorithm: typeof algo === 'string' ? {name:algo} : algo, type:'secret', extractable:true, usages };
}
function toBuf(x) {
  if (Buffer.isBuffer(x)) return x;
  if (x instanceof ArrayBuffer) return Buffer.from(x);
  if (ArrayBuffer.isView(x)) return Buffer.from(x.buffer, x.byteOffset, x.byteLength);
  return Buffer.from(x || '');
}
function toAB(buf) { return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength); }
function cipherName(algo, keyLen) {
  const n = (algo.name||algo).replace(/-/g,'').toLowerCase();
  const bits = keyLen * 8;
  if (n === 'aescbc') return `aes-${bits}-cbc`;
  if (n === 'aesgcm') return `aes-${bits}-gcm`;
  if (n === 'aesctr') return `aes-${bits}-ctr`;
  throw new Error('unsupported: ' + n);
}
function hashAlg(a) { return (typeof a==='string'?a:a.name||'').replace('-','').toLowerCase(); }

const syncSubtle = {
  importKey(fmt, key, algo, ext, usages) { return syncThenable(fakeCryptoKey(toBuf(key), algo, usages)); },
  exportKey(fmt, key) { return syncThenable(toAB(key._raw)); },
  encrypt(algo, key, data) {
    try { const c=nodeCrypto.createCipheriv(cipherName(algo,key._raw.length),key._raw,toBuf(algo.iv));
      return syncThenable(toAB(Buffer.concat([c.update(toBuf(data)),c.final()]))); }
    catch(e){ return syncThenable(undefined); }
  },
  decrypt(algo, key, data) {
    try { const d=nodeCrypto.createDecipheriv(cipherName(algo,key._raw.length),key._raw,toBuf(algo.iv));
      return syncThenable(toAB(Buffer.concat([d.update(toBuf(data)),d.final()]))); }
    catch(e){ return syncThenable(undefined); }
  },
  digest(algo, data) {
    try { const h=nodeCrypto.createHash(hashAlg(algo)); h.update(toBuf(data));
      return syncThenable(toAB(h.digest())); }
    catch(e){ return syncThenable(undefined); }
  },
  sign(algo,key,data) {
    try { const h=nodeCrypto.createHmac(hashAlg(algo.hash||'sha256'),key._raw); h.update(toBuf(data));
      return syncThenable(toAB(h.digest())); }
    catch(e){ return syncThenable(undefined); }
  },
  generateKey(algo,ext,u) { return syncThenable(fakeCryptoKey(nodeCrypto.randomBytes((algo.length||128)/8),algo,u)); },
  deriveBits() { return syncThenable(toAB(nodeCrypto.randomBytes(32))); },
  deriveKey(a,b,d,e,u) { return syncThenable(fakeCryptoKey(nodeCrypto.randomBytes((d.length||128)/8),d,u)); },
  verify() { return syncThenable(true); },
};
const syncCrypto = {
  subtle: syncSubtle,
  getRandomValues(a) { nodeCrypto.randomFillSync(a); return a; },
  randomUUID() { return nodeCrypto.randomUUID(); },
};

// ═══════════ 2. Proxy 环境框架 ═══════════
const accessLog = [];  // [{path, type:'get'|'set'|'call', val?}]
const cookieWrites = [];
let cookieJar = '';

// 尝试加载真浏览器 dump 的环境快照
let envSnapshot = {};
const SNAP_PATH = path.join(__dirname, 'env_snapshot.json');
if (fs.existsSync(SNAP_PATH)) {
  try { envSnapshot = JSON.parse(fs.readFileSync(SNAP_PATH, 'utf8')); } catch(e) {}
}

function lookupSnapshot(pathStr) {
  if (pathStr in envSnapshot) return { found: true, val: envSnapshot[pathStr] };
  return { found: false };
}

function deepProxy(target, prefix, depth) {
  if (depth > 8) return target;
  if (target === null || target === undefined) return target;
  if (typeof target !== 'object' && typeof target !== 'function') return target;
  // 避免重复 Proxy
  if (target.__isProxy) return target;

  return new Proxy(target, {
    get(t, prop) {
      if (prop === '__isProxy') return true;
      if (typeof prop === 'symbol') return Reflect.get(t, prop);
      const fp = prefix ? `${prefix}.${prop}` : String(prop);

      let v;
      try { v = Reflect.get(t, prop); } catch(e) { v = undefined; }

      // 优先用真值快照
      if (v === undefined || v === null) {
        const snap = lookupSnapshot(fp);
        if (snap.found) {
          if (PROBE) accessLog.push({ path: fp, type: 'get', source: 'snapshot' });
          return snap.val;
        }
      }

      if (PROBE) {
        const desc = v === undefined ? '[undefined]' : v === null ? '[null]' :
          typeof v === 'function' ? '[fn]' : typeof v === 'object' ? '[obj]' : String(v).slice(0,60);
        accessLog.push({ path: fp, type: 'get', val: desc });
      }

      if (v && (typeof v === 'object' || typeof v === 'function')) {
        return deepProxy(v, fp, depth + 1);
      }
      return v;
    },
    set(t, prop, val) {
      const fp = prefix ? `${prefix}.${prop}` : String(prop);
      if (PROBE) accessLog.push({ path: fp, type: 'set', val: typeof val });
      // 捕获 cookie 写入
      if (prop === 'cookie' && (prefix === 'document' || prefix.endsWith('.document'))) {
        const s = String(val);
        const name = s.split('=')[0].trim();
        const v2 = (s.split('=')[1]||'').split(';')[0];
        cookieWrites.push({ t: Date.now(), name, val: v2 });
        cookieJar = s;  // 简化：只保留最后写入
      }
      try { Reflect.set(t, prop, val); } catch(e) {}
      return true;
    },
    apply(t, thisArg, args) {
      if (PROBE) accessLog.push({ path: prefix, type: 'call' });
      try { return Reflect.apply(t, thisArg, args); } catch(e) { return undefined; }
    },
    construct(t, args) {
      if (PROBE) accessLog.push({ path: `new ${prefix}`, type: 'call' });
      try { return Reflect.construct(t, args); } catch(e) { return {}; }
    },
  });
}

// ═══════════ 3. 构造假 window ═══════════
// 提供 SDK 实际需要的最小表面
const fakeDoc = {
  cookie: '',
  referrer: 'https://www.goofish.com/',
  title: '闲鱼 - 闲不住？上闲鱼！',
  URL: 'https://www.goofish.com/',
  characterSet: 'UTF-8',
  documentElement: { style: {}, getAttribute(){ return ''; } },
  head: { appendChild(){}, removeChild(){} },
  body: { appendChild(){}, removeChild(){}, style: {} },
  createElement(tag) {
    if (tag === 'canvas') return {
      width: 300, height: 150,
      getContext() {
        return {
          canvas: this, fillStyle: '', strokeStyle: '', font: '', textBaseline: 'alphabetic',
          globalCompositeOperation: 'source-over', shadowBlur: 0, shadowColor: 'rgba(0,0,0,0)',
          fillText(){}, strokeText(){}, fillRect(){}, strokeRect(){}, clearRect(){},
          beginPath(){}, closePath(){}, arc(){}, fill(){}, stroke(){}, rect(){},
          moveTo(){}, lineTo(){}, bezierCurveTo(){}, quadraticCurveTo(){},
          save(){}, restore(){}, translate(){}, rotate(){}, scale(){}, transform(){}, setTransform(){},
          drawImage(){}, createImageData(w,h){ return {data:new Uint8Array(w*h*4)}; },
          getImageData(x,y,w,h){ return {data:new Uint8Array(w*h*4)}; },
          putImageData(){},
          measureText(t){ return {width: (t||'').length * 7}; },
          // webgl stubs
          getParameter(p){ return typeof p==='number' ? 'WebGL GLSL ES 1.0' : ''; },
          getExtension(){ return null; },
          getSupportedExtensions(){ return []; },
          createBuffer(){return{};}, createShader(){return{};}, createProgram(){return{};},
          bindBuffer(){}, bufferData(){}, shaderSource(){}, compileShader(){},
          attachShader(){}, linkProgram(){}, useProgram(){},
          getAttribLocation(){return 0;}, getUniformLocation(){return{};},
          enableVertexAttribArray(){}, vertexAttribPointer(){}, drawArrays(){},
          readPixels(){}, viewport(){}, clearColor(){}, clear(){}, enable(){}, disable(){},
        };
      },
      toDataURL(){ return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=='; },
    };
    if (tag === 'input') return { name:'', value:'', type:'hidden', setAttribute(){}, getAttribute(){ return ''; } };
    if (tag === 'div' || tag === 'span') return { style:{}, innerHTML:'', appendChild(){}, setAttribute(){} };
    return { style:{}, setAttribute(){}, getAttribute(){ return ''; }, appendChild(){}, removeChild(){} };
  },
  getElementById(){ return null; },
  getElementsByTagName(tag) {
    if (tag === 'script') return [{src:'https://g.alicdn.com/AWSC/et/1.83.41/et_f.js'}];
    if (tag === 'head') return [fakeDoc.head];
    return [];
  },
  querySelectorAll(){ return []; },
  querySelector(){ return null; },
  addEventListener(){}, removeEventListener(){},
};

// 让 document.cookie 的 getter/setter 走我们的 hook
Object.defineProperty(fakeDoc, 'cookie', {
  get() { return cookieJar; },
  set(v) {
    const s = String(v);
    const name = s.split('=')[0].trim();
    const val = (s.split('=')[1]||'').split(';')[0];
    cookieWrites.push({ t: Date.now(), name, val });
    cookieJar = s;
  },
  configurable: true, enumerable: true,
});

const fakeLoc = {
  href: 'https://www.goofish.com/',
  origin: 'https://www.goofish.com',
  protocol: 'https:',
  host: 'www.goofish.com',
  hostname: 'www.goofish.com',
  port: '',
  pathname: '/',
  search: '',
  hash: '',
  toString() { return this.href; },
  assign(){}, replace(){}, reload(){},
};

const fakeNav = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
  appCodeName: 'Mozilla', appName: 'Netscape', appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
  platform: 'Win32', vendor: 'Google Inc.', vendorSub: '', product: 'Gecko', productSub: '20030107',
  language: 'zh-CN', languages: ['zh-CN','zh','en'],
  cookieEnabled: true, doNotTrack: null, onLine: true,
  hardwareConcurrency: 8, deviceMemory: 8, maxTouchPoints: 0,
  webdriver: false,
  plugins: { length: 3, 0:{name:'PDF Viewer'}, 1:{name:'Chrome PDF Viewer'}, 2:{name:'Chromium PDF Viewer'} },
  mimeTypes: { length: 2, 0:{type:'application/pdf'}, 1:{type:'text/pdf'} },
  connection: { effectiveType:'4g', downlink:10, rtt:50, saveData:false, type:'wifi' },
  geolocation: {}, mediaDevices: {},
  getBattery() { return syncThenable({charging:true,chargingTime:0,dischargingTime:Infinity,level:1}); },
  sendBeacon(){ return true; },
};

const fakeScreen = { width:1920, height:1080, availWidth:1920, availHeight:1040, colorDepth:24, pixelDepth:24,
  orientation: {type:'landscape-primary', angle:0} };

const fakeStorage = (() => {
  const m = {};
  return { getItem(k){return k in m ? m[k] : null;}, setItem(k,v){m[k]=String(v);},
    removeItem(k){delete m[k];}, clear(){for(const k in m)delete m[k];},
    key(i){return Object.keys(m)[i]||null;}, get length(){return Object.keys(m).length;} };
})();

const fakeWin = {
  // 自引用
  get window() { return proxied; }, get self() { return proxied; },
  get top() { return proxied; }, get parent() { return proxied; },
  get globalThis() { return proxied; }, get frames() { return proxied; },

  document: fakeDoc,
  navigator: fakeNav,
  location: fakeLoc,
  screen: fakeScreen,
  history: { length:1, state:null, go(){}, back(){}, forward(){}, pushState(){}, replaceState(){} },
  localStorage: fakeStorage,
  sessionStorage: fakeStorage,
  performance: { now(){ return Date.now(); }, timing:{}, navigation:{type:0}, getEntriesByType(){return[];} },

  innerWidth: 1920, innerHeight: 947, outerWidth: 1920, outerHeight: 1040,
  scrollX: 0, scrollY: 0, pageXOffset: 0, pageYOffset: 0,
  devicePixelRatio: 1, visualViewport: { width:1920, height:947 },

  chrome: { runtime:{}, app:{installState:()=>{}}, csi:()=>({}), loadTimes:()=>({}) },
  crypto: syncCrypto,

  // Image：立即触发 onload
  Image: function FakeImage() {
    const img = {};
    Object.defineProperty(img, 'src', {
      set(v) { this._src = v; setTimeout(() => { try { img.onload && img.onload({}); } catch(e){} }, 1); },
      get() { return this._src || ''; },
    });
    img.width = 0; img.height = 0;
    return img;
  },
  XMLHttpRequest: function() {
    return { open(){}, send(){}, setRequestHeader(){}, addEventListener(){}, abort(){},
      readyState:4, status:200, responseText:'{}', response:'{}',
      getResponseHeader(){ return ''; }, getAllResponseHeaders(){ return ''; } };
  },
  fetch: () => syncThenable({ ok:true, status:200, text:()=>syncThenable(''), json:()=>syncThenable({}) }),
  WebSocket: function(){ return { send(){}, close(){}, addEventListener(){} }; },

  setTimeout, clearTimeout, setInterval, clearInterval, queueMicrotask,
  requestAnimationFrame: (cb) => setTimeout(cb, 16),
  cancelAnimationFrame: clearTimeout,

  Promise, Date, Math, JSON, Number, String, Object, Array, RegExp, Error,
  TypeError, RangeError, SyntaxError, URIError, ReferenceError, EvalError,
  Function, Symbol, Proxy, Reflect, WeakRef, FinalizationRegistry,
  parseInt, parseFloat, isNaN, isFinite, NaN, Infinity, undefined,
  encodeURIComponent, decodeURIComponent, encodeURI, decodeURI,
  escape, unescape,
  btoa: s => Buffer.from(String(s), 'binary').toString('base64'),
  atob: s => Buffer.from(String(s), 'base64').toString('binary'),

  Uint8Array, Uint16Array, Uint32Array, Uint8ClampedArray,
  Int8Array, Int16Array, Int32Array,
  Float32Array, Float64Array, BigInt64Array, BigUint64Array,
  ArrayBuffer, SharedArrayBuffer, DataView, TextEncoder, TextDecoder,
  Map, Set, WeakMap, WeakSet, BigInt,

  console,
  alert(){}, confirm(){ return true; }, prompt(){ return ''; },
  getComputedStyle(){ return { getPropertyValue(){ return ''; } }; },
  matchMedia(q){ return { matches: false, media: q, addEventListener(){} }; },
  addEventListener(){}, removeEventListener(){}, dispatchEvent(){},
  postMessage(){}, open(){ return null; }, close(){},
  MutationObserver: function(){ return { observe(){}, disconnect(){}, takeRecords(){return[];} }; },
  ResizeObserver: function(){ return { observe(){}, disconnect(){} }; },
  IntersectionObserver: function(){ return { observe(){}, disconnect(){} }; },
  DOMParser: function(){ return { parseFromString(){ return fakeDoc; } }; },
};

const proxied = deepProxy(fakeWin, '', 0);

// ═══════════ 4. 跑 SDK ═══════════
const sandbox = vm.createContext(new Proxy(Object.create(null), {
  has(_, key) { return true; },   // 让任何变量引用都不抛 ReferenceError
  get(_, key) {
    if (typeof key === 'symbol') return undefined;
    if (key === 'globalThis' || key === 'window' || key === 'self' || key === 'top' || key === 'parent' || key === 'frames')
      return proxied;
    const k = String(key);
    if (k in fakeWin) return deepProxy(fakeWin[k], k, 0);
    // 不在 fakeWin 里的：先查快照，再返回 undefined
    const snap = lookupSnapshot(k);
    if (snap.found) return snap.val;
    if (PROBE) accessLog.push({ path: k, type: 'get', val: '[undefined-global]' });
    return undefined;
  },
  set(_, key, val) {
    fakeWin[key] = val;
    return true;
  },
}));

async function run() {
  const code = fs.readFileSync(ET_PATH, 'utf8');
  try { vm.runInContext(code, sandbox, { filename: 'et_f.js', timeout: 8000 }); }
  catch (e) { console.error('[gen_tfstk] eval err:', e.message); }

  // 等 setTimeout 链完成
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 200));
    // 查看是否拿到真值
    const good = [...cookieWrites].reverse().find(w => w.name === 'tfstk' && w.val && w.val !== 'undefined');
    if (good) {
      if (!PROBE) process.stdout.write(good.val);
      else console.error('[gen_tfstk] GOT tfstk at iter', i, 'val=', good.val.slice(0, 80) + '...');
      return good.val;
    }
    // 主动调 getETToken
    try {
      vm.runInContext(`
        try { var m = __awsc_et__ || (typeof __etModule!=='undefined' && __etModule);
          if (m && typeof m.getETToken==='function') m.getETToken({appkey:'XIANYU'}); } catch(e){}
      `, sandbox, { timeout: 2000 });
    } catch(e) {}
  }

  // ═══════════ 5. probe 模式：输出访问日志 ═══════════
  if (PROBE) {
    // 去重 + 排序
    const seen = new Map();
    for (const e of accessLog) {
      const k = e.path + '|' + e.type;
      if (!seen.has(k)) seen.set(k, e);
    }
    const report = {
      cookieWrites,
      accessedPaths: [...seen.values()].filter(e => e.type === 'get').map(e => ({ path: e.path, val: e.val })),
      writtenPaths: [...seen.values()].filter(e => e.type === 'set').map(e => e.path),
      calledPaths: [...seen.values()].filter(e => e.type === 'call').map(e => e.path),
      undefinedGlobals: [...seen.values()].filter(e => e.val === '[undefined-global]').map(e => e.path),
    };
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.error('[gen_tfstk] timeout. writes:', JSON.stringify(cookieWrites));
  }
  return '';
}

run().then(v => { if (!v) process.exit(1); }).catch(e => { console.error(e); process.exit(2); });
