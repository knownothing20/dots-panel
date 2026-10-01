'use strict';
// Synthetic state only. Fetch is a recording stub, never a network request.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(tag='div'){this.tag=tag;this.dataset={};this.children=[];this.attrs={};this.listeners={};this.style={};this.classList={toggle(){},remove(){},add(){},contains(){return false;}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attrs[k]=v;}
 getAttribute(k){return this.attrs[k];}
 removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,v){this.listeners[k]=v;}
 set innerHTML(value){throw new Error('Result fields must never be rendered as HTML');}
}
const ids=new Map();
const document={body:new Node(),documentElement:{},createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){if(!ids.has(id))ids.set(id,new Node());return ids.get(id);},createElement(tag){return new Node(tag);},querySelectorAll(){return [];}};
const fetches=[],intervals=[];
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:''},window:{addEventListener(){},scrollY:123,scrollTo(x,y){this.scrollY=y;}},setInterval(cb,ms){intervals.push(ms);},AbortSignal:{timeout(){}},fetch:async path=>{fetches.push(path);throw Error('Synthetic offline');},console,assert};
vm.createContext(context);
for(const file of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);
vm.runInContext(`
assert.equal(timezone,'Asia/Shanghai');
assert(stamp('2026-12-31T18:00:00Z').includes('01/01/2027'));
timezone='America/Los_Angeles';
assert(stamp('2026-03-08T09:59:00Z').includes('01:59:00 GMT-08:00'));
assert(stamp('2026-03-08T10:01:00Z').includes('03:01:00 GMT-07:00'));
assert(stamp('2026-11-01T08:30:00Z').includes('GMT-07:00'));
assert(stamp('2026-11-01T09:30:00Z').includes('GMT-08:00'));
timezone='Europe/London';assert(stamp('2026-07-01T00:00:00Z').includes('GMT+01:00'));
assert.throws(()=>validateTimezone('Mars/Invalid'));
assert(stamp('2026-01-01T00:00:00').includes('timezone unknown'));
workspaceFilter='waiting_user';workspaceQuery='same';location.hash='#settings';$('detail-scroll').scrollTop=47;
$('timezone').value='Invalid/Zone';$('apply-timezone').listeners.click();assert.equal(timezone,'Europe/London');assert.equal(settingsError,'invalid');
localStorage.setItem=()=>{throw Error('readonly');};$('timezone').value='UTC';$('apply-timezone').listeners.click();
assert.equal(timezone,'UTC');assert.equal(settingsError,'save');assert.equal(location.hash,'#settings');assert.equal(workspaceFilter,'waiting_user');assert.equal(workspaceQuery,'same');assert.equal($('detail-scroll').scrollTop,47);assert.equal(window.scrollY,123);
localStorage.setItem=()=>{};$('timezone').value='Asia/Shanghai';$('apply-timezone').listeners.click();assert.equal(settingsError,'');
const input={platform_observation:{platform:'dot',task_id:'test',enabled:true,timezone:'Asia/Shanghai',schedule:'08:00 daily',observed_at:0,next_run_at:null}};
const before=JSON.stringify(input),rows=Object.fromEntries(schedulePlatformView(input).rows);
assert.equal(rows['Next run'],'Unknown');assert.equal(rows['First scheduled execution'],'Not yet verified');assert.equal(JSON.stringify(input),before);
`,context);
console.log('Settings timezone tests passed');
