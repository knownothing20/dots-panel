'use strict';
// Synthetic DOM regression checks only: no browser, account, network or runtime DATA.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let document;
const walk=node=>[node,...node.children.flatMap(walk)];
function matches(node,selector){
  const className=selector.match(/\.([\w-]+)/)?.[1];
  if(className&&!String(node.className||'').split(' ').includes(className))return false;
  const tag=selector.match(/^[a-z]+/)?.[0];
  if(tag&&node.tag!==tag)return false;
  const attr=selector.match(/\[([^\]]+)\]/)?.[1];
  return !attr||node.getAttribute(attr)!=null;
}
class Node {
  constructor(tag='div'){
    this.tag=tag;this.tagName=tag.toUpperCase();this.dataset={};this.children=[];this.attrs={};this.listeners={};this.value='';this.scrollTop=0;this.top=0;this.height=20;
    this.style={setProperty(){}};this.classes=new Set();this.classList={toggle:(k,on)=>{if(on===undefined)on=!this.classes.has(k);if(on)this.classes.add(k);else this.classes.delete(k);},remove:k=>this.classes.delete(k),add:k=>this.classes.add(k),contains:k=>this.classes.has(k)};
  }
  append(...items){for(const node of items){node.parentElement=this;this.children.push(node);}}
  replaceChildren(...items){for(const child of this.children)child.parentElement=null;this.children=[];this.append(...items);}
  replaceWith(node){const parent=this.parentElement;if(parent){parent.children[parent.children.indexOf(this)]=node;node.parentElement=parent;this.parentElement=null;}}
  setAttribute(key,value){this.attrs[key]=value;if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())]=value;}
  getAttribute(key){if(key.startsWith('data-'))return this.dataset[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())];return this.attrs[key];}
  removeAttribute(key){delete this.attrs[key];}
  addEventListener(key,handler){this.listeners[key]=handler;}
  focus(){document.activeElement=this;}
  contains(node){return walk(this).includes(node);}
  querySelectorAll(selector){return walk(this).slice(1).filter(node=>matches(node,selector));}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
  closest(selector){for(let node=this;node;node=node.parentElement)if(matches(node,selector))return node;return null;}
  getBoundingClientRect(){return {top:this.top,bottom:this.top+this.height};}
  get options(){return this.children;}
  get firstChild(){return this.children[0];}
  get lastElementChild(){return this.children.at(-1);}
}
require('./dom_patch_fixture.js')(Node,()=>document);
const ids=new Map();
for(const match of fs.readFileSync('web/index.html','utf8').matchAll(/\bid="([^"]+)"/g)){const node=new Node();node.id=match[1];ids.set(match[1],node);}
document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){assert(ids.has(id),'Real HTML ID required: '+id);return ids.get(id);},createElement:tag=>new Node(tag),createTextNode:text=>Object.assign(new Node('#text'),{textContent:text}),querySelectorAll(selector){return [...ids.values()].flatMap(walk).filter(node=>matches(node,selector));}};
const window={scrollY:420,addEventListener(){},scrollTo(options,y){this.scrollY=typeof options==='object'?options.top:y;}};
const pending=[];
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:'#conversations'},window,setInterval(){},AbortSignal:{timeout(){}},fetch:(url)=>new Promise((resolve,reject)=>pending.push({url,resolve,reject})),URL,console,assert};
vm.createContext(context);
for(const file of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);

context.pending=pending;context.walk=walk;
const run=script=>vm.runInContext(script,context);
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve();};

run(`
const base={metrics:{os:'Linux',architecture:'test',python:'3',scope:'Synthetic',sampled_at:1},tasks:[],runs:[],latest_runs:[],activity:[],events:[],agents:[],agent_assignments:[],agent_run_assignments:[],assignment_episodes:[],artifacts:[],output_summaries:{},bindings:[],schedules:[],software:[],rules:{groups:[]},about:{installed_version:'test',doctor:{},release:{},install_notes:[]},backup:{status:'unconfigured'}};
render(base);
const joined=node=>walk(node).map(x=>x.textContent||'').join(' ');
assert(joined($('backup-rows')).includes('Unknown'));
assert($('backup-summary-status').textContent.includes('not configured'));
const existingRow=$('backup-rows').children[0];
const value={status:'verified',remote_live:false,destination:{provider:'ChatGPT Library',label:'Synthetic private folder',path:'/Private <img src=x>'},state_dir:'/private/synthetic/state',observation_state:'unknown',last_verified:{captured_at:946684800,verified_at:946684820,index_version:3,source_file_count:2,data_file_count:3,external_file_count:0,checkpoint_count:1,exclusion_count:4,hydrated:true},last_attempt:null};
location.hash='#settings';$('timezone').value='Unfinished user input';$('timezone').focus();window.scrollY=321;
render({...base,backup:value},true);
assert.equal($('backup-rows').children[0],existingRow,'Changed backup values preserve keyed row identity');
assert.equal($('timezone').value,'Unfinished user input');assert.equal(document.activeElement,$('timezone'));assert.equal(window.scrollY,321);
assert(joined($('backup-rows')).includes('/Private <img src=x>'),'private path remains literal text');
assert(!walk($('backup-rows')).some(node=>node.tag==='img'||node.tag==='script'||node.href));
assert($('backup-note').textContent.includes('not independently proven'));
assert(joined($('backup-rows')).includes('not platform sessions'));
const rowCount=$('backup-rows').children.length;
render({...base,backup:value},true);assert.equal($('backup-rows').children.length,rowCount);assert.equal($('backup-rows').children[0],existingRow);
for(const lang of ['zh','en']){
 language=lang;timezone='Asia/Shanghai';renderBackup(value);
 assert($('backup-summary-status').textContent.includes(lang==='en'?'Verified recovery':'已核验恢复点'));
 assert(joined($('backup-rows')).includes('08:00:00'));
 const oldTime=$('backup-summary-status').textContent;
 renderBackup({...value,status:'failed',last_attempt:{checked_at:946688800,stage:'prepare',result:'failed',error_type:'source_busy'}});
 assert($('backup-status').textContent.includes(lang==='en'?'blocked':'受阻'));
 assert($('backup-summary-status').textContent.includes(lang==='en'?'Last verified snapshot: ':'最后核验快照：'),'Snapshot timestamp must have explicit meaning beside failed status');
 assert($('backup-summary-status').textContent.endsWith(oldTime.split(' · ').slice(1).join(' · ')),'Failure never invents a newer successful snapshot');
 assert(joined($('backup-rows')).includes('source_busy'));
 assert($('backup-summary-status').classList.contains('backup-warning'));
 timezone='UTC';renderBackup(value);assert(joined($('backup-rows')).includes('00:00:00'));
 assert($('backup-about-note').textContent.includes(lang==='en'?'cause is unconfirmed':'原因未确认'));
}
language='en';renderBackup({...value,destination:{provider:'ChatGPT Library',label:'ChatGPT Library · Private',path:'/Private'}});
assert.equal(backupView({...value,destination:{provider:'ChatGPT Library',label:'ChatGPT Library · Private',path:'/Private'}}).rows[0][2],'ChatGPT Library · Private');
renderBackup(value);
assert($('task-watch-status').textContent.includes('unverified'));
const backupText=$('backup-summary-status').textContent;
renderBackup({...value,task_watch:{status:'unavailable',checked_at:946688800,last_success_at:946684000,error_type:'data_unavailable'}});
assert($('task-watch-status').textContent.includes('unavailable'));
assert.equal($('backup-summary-status').textContent,backupText,'Monitor failure cannot erase the recorded backup point');
assert(joined($('backup-rows')).includes('data_unavailable'));
renderBackup({...value,status:'failed',task_watch:{status:'checked',checked_at:946688800,last_success_at:946688800,error_type:null}});
assert($('task-watch-status').textContent.includes('succeeded'));assert($('backup-status').textContent.includes('blocked'));
assert.equal(pending.length,1,'No extra fetches for backup cards or About');
`);
const html=fs.readFileSync('web/index.html','utf8');
assert(html.includes('id="backup-rows"'));
assert(!/onclick=.*restore|id="restore-now"/.test(html));
console.log('Backup UI: unknown, validated historical point, failure retention, bilingual/timezone, literal paths, no network, keyed rows and focus/scroll retained');
