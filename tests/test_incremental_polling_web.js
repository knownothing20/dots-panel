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
const metrics={os:'Linux',architecture:'test',python:'3',scope:'Synthetic',sampled_at:1};
const base={metrics,tasks:[{id:'goal',name:'Goal',project:'Fixture',created:1,activity_kind:'task',collaboration_mode:'team',mode_source:'explicit'}],runs:[{id:'r',task_id:'goal',status:'running',started:1,updated:1}],latest_runs:[],activity:[{id:1,task_id:'goal',created:1,message:'First',stage:'progress'}],events:[],agents:[],agent_assignments:[],agent_run_assignments:[],assignment_episodes:[],artifacts:[],output_summaries:{},bindings:[],schedules:[{id:'s',name:'Schedule',state:'planned',source:'manual',updated:1}],software:[{id:'tool',name:'Tool',version:'1',kind:'dots-panel',available:true,verified_at:1,description:'Local'}],rules:{groups:[{id:'g',title:{en:'Group',zh:'组'},items:[]}]},about:{installed_version:'1',doctor:{},release:{},install_notes:[]}};
render(base);
assert.equal(t('任务'),'Tasks');assert.equal(t('自动化'),'Automations');
assert.equal(PanelCollaboration.mode(base.tasks[0],'en'),'Team');
assert.equal(PanelCollaboration.mode({collaboration_mode:'team'},'en'),'Unclassified');
assert.equal(PanelCollaboration.matchesMode({collaboration_mode:'single'},'single'),false);assert.equal(PanelCollaboration.matchesMode(base.tasks[0],'team'),true);
assert.equal(PanelCollaboration.automationSource({...base,bindings:[{task_id:'goal',source_type:'cloud_thread',thread_id:'real'}]},'goal'),null,'Session binding is not automation origin');
assert.equal(PanelCollaboration.automationSource({...base,automation_bindings:[{task_id:'goal',automation_id:'a',verified:true,name:'Verified automation'}]},'goal'),'Verified automation');
for(const page of ['overview','conversations','schedules','software','rules','about','settings']){
 location.hash='#'+page;showPage();const before=[$('task-list').children[0],$('active-work').children[0],$('schedule-cards').children[0],$('software-cards').children[0],$('rules-content').children[0],$('about-rows').children[0]];
 let writes=0;const original=PanelPatch.sync;PanelPatch.sync=function(...args){writes++;return original.apply(this,args);};
 render(base,true);assert.equal(writes,0,'Unchanged '+page+' is a true no-op');PanelPatch.sync=original;
 assert.deepEqual(before,[$('task-list').children[0],$('active-work').children[0],$('schedule-cards').children[0],$('software-cards').children[0],$('rules-content').children[0],$('about-rows').children[0]]);
}
const taskNode=$('task-list').children[0],scheduleNode=$('schedule-cards').children[0],softwareNode=$('software-cards').children[0];
const changed={...base,runs:[{...base.runs[0],status:'awaiting_review',updated:2,lifecycle_reason:'Ready for review'}],schedules:[{...base.schedules[0],name:'Updated automation',updated:2}],software:[{...base.software[0],version:'2',verified_at:2}]};
render(changed,true);
assert.equal($('task-list').children[0],taskNode,'Task identity retained');assert.equal($('schedule-cards').children[0],scheduleNode,'Automation identity retained');assert.equal($('software-cards').children[0],softwareNode,'Software identity retained');
assert(walk(taskNode).some(n=>n.textContent==='Ready for review'));assert(walk(scheduleNode).some(n=>n.textContent==='Updated automation'));assert(walk(softwareNode).some(n=>n.textContent==='2'));
location.hash='#conversations';$('task-filter').value='goal';render(changed);const message=$('project-activity').children[0];const filter=$('conversation-agent');filter.focus();$('detail-scroll').scrollTop=145;$('detail-scroll').scrollHeight=900;$('detail-scroll').clientHeight=300;
const appended={...changed,activity:[...changed.activity,{id:2,task_id:'goal',created:2,stage:'progress',message:'Second'}]};
render(appended,true);assert.equal($('project-activity').children[0],message,'Existing message preserved when a new event arrives');assert.equal(document.activeElement,filter,'Filter focus retained');assert.equal($('detail-scroll').scrollTop,145,'Reading position retained away from bottom');
assert.equal($('project-activity').children.length,2);assert.equal($('project-activity').children[1].children[2].textContent,'Second');
assert.equal($('project-activity').children[0].children[0].children[1].children[0].textContent,'Anonymous');assert.equal($('project-activity').children[0].children[0].children[0].className,'unattributed-avatar anonymous-avatar');
$('detail-scroll').scrollTop=600;const next={...appended,activity:[...appended.activity,{id:3,task_id:'goal',created:3,stage:'progress',message:'Third'}]};render(next,true);assert.equal($('detail-scroll').scrollTop,900,'Follow bottom only when already near bottom');
conversationFilters.agent='unattributed';renderConversationFilterChips();assert.equal($('conversation-filter-chips').children.length,1);$('conversation-filter-chips').children[0].listeners.click();assert.equal(conversationFilters.agent,'');
`);

run(`
// Action payloads must change while the clicked DOM node survives.
const oldSelect=selectTask,oldOpenFiles=openTaskFiles,oldTab=setDetailTab;let clickedTask=null,clickedFile=null;
selectTask=task=>{clickedTask=task;};openTaskFiles=task=>{clickedFile=task;};setDetailTab=()=>{};
const oldTask={...base.tasks[0],name:'Old payload',actionRevision:'old'},newTask={...oldTask,name:'New payload',actionRevision:'new'};
const actionState={...base,tasks:[oldTask],agents:[{id:'worker',name:'Worker',status:'running',observed_at:Date.now()/1000}],agent_run_assignments:[{run_id:'r',task_id:'goal',agent_id:'worker',work_type:'development',assigned_at:1}],output_summaries:{goal:{count:1,kinds:['report'],main:null}}};
const actionCard=taskCard(oldTask,base.runs[0],actionState),oldButton=walk(actionCard).find(n=>n.dataset.focusKey==='task-details:goal'),oldFileButton=walk(actionCard).find(n=>n.dataset.focusKey==='task-files:goal'),oldAvatar=walk(actionCard).find(n=>n.className==='participant-avatar-group');
const detailWrapper=oldButton.listeners.click;
PanelPatch.sync(actionCard,taskCard(newTask,base.runs[0],{...actionState,tasks:[newTask]}));
assert.equal(walk(actionCard).find(n=>n.dataset.focusKey==='task-details:goal'),oldButton);assert.equal(oldButton.listeners.click,detailWrapper,'Listener dispatcher remains mounted');
oldButton.listeners.click({stopPropagation(){}});assert.equal(clickedTask.actionRevision,'new','Details handler uses new task payload');
oldFileButton.listeners.click({stopPropagation(){}});assert.equal(clickedFile.actionRevision,'new','File handler uses new task payload');
oldAvatar.listeners.click({stopPropagation(){}});assert.equal(clickedTask.actionRevision,'new','Avatar handler uses new task payload');
const generic=element('button','Action');let result='';PanelPatch.listen(generic,'click',()=>{result='old';});
const fresh=element('button','Action');PanelPatch.listen(fresh,'click',()=>{result='new role/file/path';});PanelPatch.sync(generic,fresh);generic.listeners.click();assert.equal(result,'new role/file/path');
PanelPatch.sync(generic,element('button','No action'));assert.equal(generic.listeners.click,undefined,'Removed actions do not remain callable');
// Disclosure callbacks read the retained currentTarget, never a detached draft node.
const schedule=$('schedule-cards').children[0],detail=walk(schedule).find(n=>n.tag==='details');detail.open=true;detail.listeners.toggle();assert(expandedSchedules.has('s'));
const staticPageHandler=$('conversation-next').listeners.click,staticFilterHandler=$('conversation-agent').listeners.change;
render({...next,schedules:[{...next.schedules[0],name:'Latest schedule'}]},true);
assert.equal($('conversation-next').listeners.click,staticPageHandler);assert.equal($('conversation-agent').listeners.change,staticFilterHandler);
const currentDetail=walk($('schedule-cards').children[0]).find(n=>n.tag==='details');currentDetail.open=false;currentDetail.listeners.toggle();assert(!expandedSchedules.has('s'));
assert(walk($('software-cards').children[0]).filter(n=>n.tag==='button').every(n=>n.disabled&&!n.listeners.click),'Read-only software buttons never acquire actions');
selectTask=oldSelect;openTaskFiles=oldOpenFiles;setDetailTab=oldTab;
`);

run(`
const longTitle='A long task title '.repeat(60),longSummary='Long progress note and detailed result '.repeat(250);
for(const status of ['running','succeeded','waiting_user','waiting_external','paused','awaiting_review','failed','cancelled']){
 const task={...base.tasks[0],name:longTitle},run={id:'bound-run',task_id:'goal',status,started:1,updated:123,lifecycle_reason:longSummary,lifecycle_evidence:'Detail-only evidence',next_step:'Full next action'};
 const state={...base,tasks:[task],runs:[run],latest_runs:[],agents:[],agent_run_assignments:[],assignment_episodes:[],activity:[],events:[]};
 const snapshot=JSON.stringify(state),card=taskCard(task,run,state);
 assert.equal(card.children.length,6,'Card row count stays bounded for '+status);assert.equal(card.children[0].tag,'h2');assert.equal(card.children[1].className,'task-card-top');assert.equal(card.children[2].className,'task-summary');
 assert.equal(card.children.find(n=>n.tag==='h2').title,longTitle);assert(card.title.includes(longSummary));
 assert.equal(card.children.find(n=>n.className==='task-summary').textContent,longSummary,'Clamping does not destroy full text');
 assert(!walk(card).some(n=>n.tag==='details'||['task-next','task-card-footer','freshness-warning'].includes(n.className)),'Run history and evidence belong to detail');
 assert(!walk(card).some(n=>String(n.textContent||'').includes('bound-run')),'No generated run ID on card');
 assert(card.children.find(n=>n.className==='task-card-top').children[1].hidden,'No participant leaves the avatar area blank');
 assert.equal(card.className,'task-card '+status);assert.equal(JSON.stringify(state),snapshot);
}
`);
run(`
// Compact toolbar keeps native menu/search handlers and focus across changed polls.
$('task-filter').value='';workspaceFilter='all';workspaceQuery='';collaborationModeFilter='all';
const recoveryState={...base,recovery:{notice_en:'Recovered history needs verification',notice_zh:'历史待核对'}};render(recoveryState);
assert.equal($('recovery-info').hidden,false);assert.equal(Boolean($('recovery-info').open),false);
const modeControl=$('collaboration-mode-filter'),modeAction=modeControl.listeners.change,searchControl=$('workspace-search');
modeControl.value='team';modeControl.listeners.change();assert.equal(collaborationModeFilter,'team');assert.equal($('task-list').children.length,1);
modeControl.value='single';modeControl.listeners.change();assert.equal($('task-list').children.length,0);
modeControl.value='all';modeControl.listeners.change();searchControl.value='Goal';searchControl.listeners.input();assert.equal(workspaceQuery,'Goal');assert.equal($('task-list').children.length,1);
searchControl.focus();$('recovery-info').open=true;
render({...recoveryState,recovery:{...recoveryState.recovery,notice_en:'Changed recovery evidence'},runs:[{...base.runs[0],updated:9}]},true);
assert.equal(document.activeElement,searchControl);assert.equal(searchControl.value,'Goal');assert.equal(modeControl.listeners.change,modeAction);
assert.equal($('recovery-info').open,true);assert.equal($('recovery-notice').textContent,'Changed recovery evidence');
render({...base,runs:[{...base.runs[0],updated:10}]},true);assert.equal($('recovery-info').hidden,true);
`);
run(`
for (const filters of [
  {status:'all',mode:'single',query:''},
  {status:'all',mode:'all',query:'no-such-task'},
  {status:'succeeded',mode:'all',query:''}
]) {
  workspaceFilter=filters.status;collaborationModeFilter=filters.mode;workspaceQuery=filters.query;
  render(base);
  assert.equal($('task-list').children.length,0);
  assert.equal(String($('task-count').textContent),'0');
  assert.equal($('task-empty').hidden,false);
  render({...base,runs:[{...base.runs[0],updated:99}]},true);
  assert.equal(String($('task-count').textContent),'0');
  assert.equal($('task-empty').hidden,false);
}
workspaceFilter='all';collaborationModeFilter='all';workspaceQuery='';render(base);
assert.equal(String($('task-count').textContent),'1');assert.equal($('task-empty').hidden,true);
`);
const html=fs.readFileSync('web/index.html','utf8'),css=fs.readFileSync('web/style.css','utf8');
assert(css.includes('height:232px;min-height:0;max-height:232px'));assert(css.includes('line-clamp:2;overflow:hidden;overflow-wrap:anywhere;font-size:18px'));assert(css.includes('line-clamp:2;max-height:42px'));
assert(html.includes('id="collaboration-filters" hidden'));assert(css.includes('.task-detail-open main>header'));assert(css.includes('.task-detail-open #page-conversations>.intro'));
console.log('Action payloads and all-tab incremental matrix passed: no-op identity, keyed task/automation/software updates, focus/scroll, chronological append, bottom-follow, anonymous identity, labels and folded filters');

assert(html.includes('id="recovery-info" class="recovery-info" hidden'));assert(css.includes("grid-template-columns:minmax(0,1fr) auto minmax(120px,210px)"));
