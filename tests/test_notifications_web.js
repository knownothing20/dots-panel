'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');require('../web/notifications.js');const {State,Deadline,newerRelease}=globalThis.PanelNotifications;
const base=()=>({tasks:[{id:'t',name:'Synthetic task'}],runs:[],agents:[],agent_run_assignments:[],schedules:[],about:{}});
{
 const s=base(),m=new State();m.update(s);s.runs=[{id:'r',task_id:'t',status:'waiting_external'}];m.update(s);assert.equal(m.counts().conversations,1);assert.equal(m.cards.length,0);
 s.agents=[{id:'a',name:'Agent',status:'running',observed_at:1}];s.agent_run_assignments=[{run_id:'r',agent_id:'a'}];assert.equal(m.update(s).cards.length,1);assert.equal(m.counts().conversations,1);
 s.runs[0].updated=999;s.agents[0].observed_at=999;assert.equal(m.update(s).changed.size,0);m.clear('agents');assert.equal(m.cards.length,1);m.clear('conversations','t');assert.equal(m.cards.length,0);assert.equal(m.update(s).cards.length,0);
}
{
 const s=base();s.runs=[{id:'r',task_id:'t',status:'running'}];s.agents=[{id:'a',status:'running'}];s.agent_run_assignments=[{run_id:'r',agent_id:'a'}];const m=new State();m.update(s);assert.equal(m.cards.length,0);s.agents[0].status='idle';assert(m.update(s).changed.has('agents'));assert.equal(m.update(s).changed.size,0);
}
{
 const s=base();s.schedules=[{id:'s',external_result:{checked_at:1,observation:{latest:{run_id:'run',status:'partial'}}}}];const m=new State();m.update(s);s.schedules[0].external_result.checked_at=3;assert.equal(m.update(s).changed.size,0);s.schedules[0].external_result.observation.latest.status='succeeded';assert(m.update(s).changed.has('schedules'));
}
{
 const about={installed_version:'0.2.0',release:{release_status:'published',release_tag:'v0.3.0',checked_at:1}},m=new State();m.update({about});assert.equal(m.counts().about,1);m.clear('about');about.release.checked_at=40;m.update({about});assert.equal(m.counts().about,0);for(const tag of ['v0.1.0','0.2.0','main','v0.3.0-rc1','v00.3.0','v0.3.0+..','v١.2.3',null]){about.release.release_tag=tag;assert.equal(newerRelease(about),false);}
}
{
 let now=0;const d=new Deadline(()=>now);d.reset();now=1200;assert.equal(d.left(),3800);d.pause(true);now=9200;assert.equal(d.left(),3800);d.pause(false);now=12000;assert.equal(d.left(),1000);d.pause(true);d.reset();assert.equal(d.left(),5000);now=99999;assert.equal(d.left(),5000);d.pause(false);now+=5000;assert.equal(d.left(),0);
}
const js=fs.readFileSync('web/notifications.js','utf8'),css=fs.readFileSync('web/notifications.css','utf8'),app=fs.readFileSync('web/app.js','utf8'),html=fs.readFileSync('web/index.html','utf8');
assert.doesNotMatch(js,/fetch\(|innerHTML|setInterval|window\.open/);assert.match(js,/aria-live','polite/);assert.match(js,/this\.shell\.inert=!this\.expanded/);assert.match(css,/prefers-reduced-motion/);assert.doesNotMatch(css,/animation[^;{}]*infinite/);assert.match(app,/panelNotifications\?\.observe\(state\)/);assert.match(app,/panelNotifications\?\.markRead/);assert(html.indexOf('notifications.js')<html.indexOf('app.js'));
console.log('Notifications: baseline, assignment, per-tab read, status/result dedup, release gating, deadline pause and UI wiring passed');
// Hidden/inert semantics and a deterministic event loop exercise the actual controller.
class Node {
 constructor(tag,doc){this.tagName=tag.toUpperCase();this.doc=doc;this.children=[];this.dataset={};this.listeners={};this.attrs={};this.className='';this.hidden=false;this.offsetWidth=100;this.isConnected=true;this.classList={add:()=>{},remove:()=>{},toggle:()=>{}};}
 append(...children){for(const c of children){c.parent=this;this.children.push(c);}}
 replaceChildren(...children){for(const c of this.children)c.parent=null;this.children=[];this.append(...children);}
 setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,v){this.listeners[k]=v;}removeEventListener(k,v){if(this.listeners[k]===v)delete this.listeners[k];}
 querySelector(s){return this.children.find(c=>s==='.notification-badge'&&c.className==='notification-badge')||null;}
 contains(el){return el===this||this.children.some(c=>c.contains(el));}
 set hidden(value){this._hidden=value;if(value&&this.contains(this.doc.activeElement))this.doc.activeElement=this.doc.body;}get hidden(){return this._hidden;}
 set inert(value){this._inert=value;if(value&&this.contains(this.doc.activeElement))this.doc.activeElement=this.doc.body;}get inert(){return this._inert;}
 focus(){for(let node=this;node;node=node.parent)if(node.hidden||node.inert)return;this.doc.activeElement=this;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(c=>c!==this);this.isConnected=false;}
}
function domCase(reduced,run){
 const doc={activeElement:null,documentElement:{dataset:{reducedMotion:String(reduced)}},listeners:{},addEventListener(k,v){this.listeners[k]=v;},removeEventListener(k,v){if(this.listeners[k]===v)delete this.listeners[k];}};
 doc.createElement=tag=>new Node(tag,doc);doc.body=new Node('body',doc);const navs=Object.fromEntries(['conversations','agents','schedules','about'].map(k=>[k,new Node('a',doc)]));doc.querySelector=s=>navs[/data-nav="(.*?)"/.exec(s)?.[1]]||null;
 const nativeSet=global.setTimeout,nativeClear=global.clearTimeout;let seq=0,now=0;const jobs=new Map();global.setTimeout=(fn,ms)=>{jobs.set(++seq,{fn,at:now+ms});return seq;};global.clearTimeout=id=>jobs.delete(id);
 const advance=ms=>{const stop=now+ms;let steps=0;while(jobs.size){const [id,job]=[...jobs].sort((a,b)=>a[1].at-b[1].at||a[0]-b[0])[0];if(job.at>stop)break;jobs.delete(id);now=job.at;job.fn();if(++steps>10000)throw Error('Timer loop');}now=stop;};
 try{
  let selected=null,intent=null;const detail=new Node('section',doc);doc.body.append(detail);detail.focus();const portraits=[];
  const c=new PanelNotifications.Controller({document:doc,language:()=> 'en',avatar:agent=>{portraits.push(agent);const node=new Node('span',doc);node.className='agent-avatar fixed-portrait';node.agent=agent;return node;},openTask:(id,options)=>{selected=id;intent=options;if(options.keyboard)detail.focus();}});c.deadline.now=()=>now;
  const s=base();c.observe(s);
  const add=(id='r')=>{s.runs.push({id,task_id:'t',status:'running'});s.agents=[{id:'a',name:'Example',name_en:'Example EN',status:'running',portrait:'bloom-mint',portrait_spec:{key:'bloom-mint',shapes:[]}}];s.agent_run_assignments.push({run_id:id,agent_id:'a'});return c.observe(s);};
  run({c,doc,navs,detail,portraits,s,add,advance,jobs,getSelected:()=>selected,getIntent:()=>intent});c.destroy();advance(1000);assert.equal(jobs.size,0);assert.equal(Object.keys(doc.listeners).length,0);
 } finally{global.setTimeout=nativeSet;global.clearTimeout=nativeClear;}
}
for(const reduced of [false,true])domCase(reduced,({c,doc,detail,portraits,s,add,advance})=>{
 assert(c.host.hidden);assert.equal(c.capsule,undefined);add();assert(c.expanded);assert.equal(doc.activeElement,detail);assert.equal(portraits[0].portrait,'bloom-mint');assert.equal(c.face.children[0].agent.portrait,'bloom-mint');
 const started=c.deadline.started;c.observe(s);assert.equal(c.deadline.started,started);
 // A mouse-created button focus does not pin the card or become keyboard focus.
 doc.listeners.pointerdown();c.action.focus();c.syncPause();assert(!c.deadline.paused);assert.equal(c.host.dataset.inputMode,'pointer');advance(5300);assert(c.host.hidden);assert.equal(c.state.counts().conversations,1);
 c.observe(s);assert(c.host.hidden);s.agents[0].portrait='orbit-sky';c.observe(s);assert(c.host.hidden);
 add('new');assert(c.expanded);assert(!c.host.hidden);assert.notEqual(doc.activeElement,c.action);c.markRead('conversations');assert(c.host.hidden);
});
domCase(false,({c,doc,detail,add,advance,getSelected,getIntent})=>{
 add();c.host.listeners.mouseenter();advance(8000);assert(c.expanded);c.host.listeners.mouseleave();assert(!c.deadline.paused);
 doc.listeners.keydown();c.action.focus();c.syncPause();advance(8000);assert(c.expanded);assert(c.deadline.paused);assert.equal(c.host.dataset.inputMode,'keyboard');
 detail.focus();c.syncPause();advance(5300);assert(c.host.hidden);add('next');doc.listeners.keydown();c.action.focus();c.action.listeners.click();assert.equal(getSelected(),'t');assert.equal(getIntent().keyboard,true);assert.equal(doc.activeElement,detail);assert(c.host.hidden);
});
domCase(true,({c,doc,detail,navs,add,getSelected,getIntent})=>{
 add();doc.listeners.pointerdown();c.action.focus();c.action.listeners.click();assert.equal(getSelected(),'t');assert.equal(getIntent().keyboard,false);assert.notEqual(doc.activeElement,detail);assert(c.host.hidden);
 add('another');doc.listeners.keydown();c.close.focus();c.syncPause();c.close.listeners.click();assert(c.host.hidden);assert.equal(c.state.counts().conversations,1);
 for(const page of ['conversations','agents','schedules'])c.state.unread[page].set('extra',true);c.badges();for(const page of ['conversations','agents','schedules']){const badge=navs[page].querySelector('.notification-badge');assert(!badge.hidden);assert.equal(badge.textContent,'');assert.equal(badge.attrs['aria-label'],'Unread updates');}
 c.markRead('agents');assert(navs.agents.querySelector('.notification-badge').hidden);assert(!navs.conversations.querySelector('.notification-badge').hidden);
});
console.log('Transient DOM: full hide, no capsule, pointer vs keyboard focus, fresh-event reshow, uniform dots, shared avatar, navigation and cleanup passed');

for(const count of [2001,5007]){
 const s=base();s.runs=Array.from({length:count},(_,n)=>({id:'r'+n,task_id:'t',status:'running'}));s.agents=[{id:'a',status:'running'}];s.agent_run_assignments=s.runs.map(r=>({run_id:r.id,agent_id:'a'}));
 const initial=new State();initial.update(s);for(let n=0;n<3;n++){const result=initial.update(s);assert.equal(result.cards.length,0);assert.equal(result.changed.size,0);assert.equal(initial.cards.length,0);}
 const m=new State();m.update(base());assert.equal(m.update(s).cards.length,count);assert(m.cards.length<=50);assert(m.counts().conversations<=2000);for(let n=0;n<3;n++){const result=m.update(s);assert.equal(result.cards.length,0);assert.equal(result.changed.size,0);}
 s.runs.push({id:'one-more',task_id:'t',status:'running'});s.agent_run_assignments.push({run_id:'one-more',agent_id:'a'});assert.equal(m.update(s).cards.length,1);assert.equal(m.update(s).changed.size,0);assert.equal(m.seenRuns.size,count+1);assert.equal(m.announcedRuns.size,count+1);m.update(base());assert(m.seenRuns.size<=2000);assert(m.announcedRuns.size<=2000);
}
{
 const s=base();s.agents=Array.from({length:2200},(_,n)=>({id:'a'+n,status:'running'}));s.schedules=Array.from({length:2200},(_,n)=>({id:'s'+n,platform_observation:{last_run_at:'2026-10-01T00:00:00Z'}}));const m=new State();m.update(s);assert.equal(m.update(s).changed.size,0);s.agents[0].status='idle';assert.deepEqual([...m.update(s).changed],['agents']);assert.equal(m.update(s).changed.size,0);
}
console.log('Large snapshots: 2001 / 5007 runs, assignments and 2200 agent/schedule identities never replay; retired history remains bounded');

{
 const m=new State(),s=base();m.update(s);s.runs=[{id:'r',task_id:'t',status:'running'}];s.agents=[{id:'a',name:'First',status:'running'}];s.agent_run_assignments=[{run_id:'r',agent_id:'a'}];m.update(s);s.agents.push({id:'b',name:'Second',status:'idle'});s.agent_run_assignments.push({run_id:'r',agent_id:'b'});const result=m.update(s);assert.equal(result.cards.length,0);assert(result.content_changed);assert.equal(m.cards[0].participants,2);assert.equal(m.counts().conversations,1);
}
// The notification stylesheet is loaded after the general 40px button minimum.
assert.match(css,/\.notification-layer button\{[^}]*min-height:0/);
assert.match(css,/\.notification-action\{height:34px;min-height:0/);
assert.match(css,/\.notification-more\{height:26px;min-height:0/);
assert(html.indexOf('notifications.css')>html.indexOf('style.css'));
assert.match(app,/detail-scroll'\)\.focus\(\{preventScroll:true\}\)/);
assert.match(app,/avatar:agentAvatar/);assert.match(app,/if\(keyboard\)\$\('detail-scroll'\)\.focus/);assert.doesNotMatch(css,/notification-capsule/);assert.match(css,/notification-badge\{[^}]*width:8px/);assert.match(css,/data-input-mode="pointer"/);
console.log('Shared avatar and input modality glue, hidden surface, button grid, and uniform unread dot styles passed');

assert.match(css,/notification-badge\[hidden\]\{display:none!important/);
