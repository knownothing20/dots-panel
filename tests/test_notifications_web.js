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
// A minimal DOM exercises the actual controller without opening a browser.
class Node {
 constructor(tag,doc){this.tagName=tag.toUpperCase();this.doc=doc;this.children=[];this.dataset={};this.listeners={};this.attrs={};this.className='';this.hidden=false;this.offsetWidth=100;this.classList={add:()=>{},remove:()=>{},toggle:()=>{}};}
 append(...children){for(const c of children){c.parent=this;this.children.push(c);}}
 setAttribute(k,v){this.attrs[k]=v;}addEventListener(k,v){this.listeners[k]=v;}
 querySelector(s){return this.children.find(c=>s==='.notification-badge'&&c.className==='notification-badge')||null;}
 contains(el){return el===this||this.children.some(c=>c.contains(el));}
 set hidden(value){this._hidden=value;if(value&&this.contains(this.doc.activeElement))this.doc.activeElement=this.doc.body;}get hidden(){return this._hidden;}
 set inert(value){this._inert=value;if(value&&this.contains(this.doc.activeElement))this.doc.activeElement=this.doc.body;}get inert(){return this._inert;}
 focus(){for(let node=this;node;node=node.parent)if(node.hidden||node.inert)return;this.doc.activeElement=this;}remove(){if(this.parent)this.parent.children=this.parent.children.filter(c=>c!==this);}
}
{
 const doc={activeElement:null,documentElement:{dataset:{reducedMotion:'true'}}};doc.createElement=tag=>new Node(tag,doc);doc.body=new Node('body',doc);const navs=Object.fromEntries(['conversations','agents','schedules','about'].map(k=>[k,new Node('a',doc)]));doc.querySelector=s=>navs[/data-nav="(.*?)"/.exec(s)?.[1]]||null;
 const nativeSet=global.setTimeout,nativeClear=global.clearTimeout;let seq=0;const jobs=new Map();global.setTimeout=(fn,ms)=>{jobs.set(++seq,{fn,ms});return seq;};global.clearTimeout=id=>jobs.delete(id);
 try{
  let selected=null;const detail=new Node('section',doc);doc.body.append(detail);const c=new PanelNotifications.Controller({document:doc,language:()=> 'en',openTask:id=>{selected=id;detail.focus();}});const s=base();c.observe(s);assert(c.host.hidden);
  s.runs=[{id:'r',task_id:'t',status:'running'}];s.agents=[{id:'a',name:'Example',status:'running'}];s.agent_run_assignments=[{run_id:'r',agent_id:'a'}];c.observe(s);assert(c.expanded);assert(!c.shell.inert);const started=c.deadline.started;
  c.observe(s);assert.equal(c.deadline.started,started);c.host.listeners.mouseenter();assert(c.deadline.paused);assert.equal(c.timer,null);c.host.listeners.mouseleave();assert(!c.deadline.paused);
  doc.activeElement=c.action;c.syncPause();assert(c.deadline.paused);doc.activeElement=null;c.syncPause();assert(!c.deadline.paused);
  c.close.listeners.click();assert(!c.expanded);assert(c.shell.inert);assert.equal(c.state.counts().conversations,1);assert.equal(c.state.cards.length,1);c.capsule.focus();c.capsule.listeners.click();assert(c.expanded);assert.equal(doc.activeElement,c.action);assert(c.deadline.paused);doc.activeElement=detail;c.syncPause();assert(!c.deadline.paused);
  c.action.listeners.click();assert.equal(selected,'t');assert.equal(doc.activeElement,detail);assert.equal(c.state.counts().conversations,0);assert(c.host.hidden);c.destroy();assert.equal(jobs.size,0);
 } finally {global.setTimeout=nativeSet;global.clearTimeout=nativeClear;}
}
console.log('Notification DOM controller: polling, hover/focus pause, capsule reopen, close vs read, progress, cleanup passed');

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
console.log('Keyboard capsule expansion transfers visible focus; last progress transfers detail focus; participant refresh is silent; button grid overrides are bounded');
