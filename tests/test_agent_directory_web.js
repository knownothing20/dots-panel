'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(tag='div'){this.tag=tag;this.dataset={};this.children=[];this.attrs={};this.listeners={};this.value='';this.style={setProperty(){}};this.classList={toggle(){},remove(){},add(){},contains(){return false;}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attrs[k]=v;}
 getAttribute(k){return this.attrs[k];}
 removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,v){this.listeners[k]=v;}
 focus(){this.focused=true;document.activeElement=this;}
 contains(node){return this===node||this.children.some(child=>child.contains?.(node));}
 get options(){return this.children;}
 get lastElementChild(){return this.children.at(-1);}
 get firstChild(){return this.children[0];}
}
const ids=new Map();
const document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){if(!ids.has(id))throw Error('Missing real HTML id: '+id);return ids.get(id);},createElement(tag){return new Node(tag);},createTextNode(text){const n=new Node();n.textContent=text;return n;},querySelectorAll(){return [];}};
for(const match of fs.readFileSync('web/index.html','utf8').matchAll(/\bid="([^"]+)"/g))ids.set(match[1],new Node());
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:''},window:{addEventListener(){}},setInterval(){},AbortSignal:{timeout(){}},fetch:async()=>{throw Error('offline');},URL,console};
vm.createContext(context);
for(const f of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+f,'utf8'),context);

context.assert=assert;
vm.runInContext(`
const observed=Date.now()/1000;
const agents=Array.from({length:6},(_,i)=>({id:'p'+i,panel_short_id:'0000000'+i,name:'Private nickname '+i,portrait:'leaf-sky',status:'running',observed_at:observed,identity_source:'manual',identity_verification:'observed'}));
const task={id:'task',name:'Actual activity'},state={agents,tasks:[task],runs:[{id:'one',task_id:'task',status:'running',started:1},{id:'two',task_id:'task',status:'succeeded',started:0},{id:'other',task_id:'elsewhere',status:'running',started:2}],agent_run_assignments:[...agents.slice(0,5).map((a,i)=>({agent_id:a.id,run_id:'one',assigned_at:i+1,work_type:'development'})),{agent_id:'p0',run_id:'two',work_type:'review',assigned_at:0},{agent_id:'p5',run_id:'other',assigned_at:100,work_type:'research'}]};
const before=JSON.stringify(state),rows=PanelAgents.activityParticipants(state,'task');assert.equal(rows.length,5);assert.ok(!rows.some(r=>r.agent.id==='p5'));assert.equal(rows.find(r=>r.agent.id==='p0').assignments.length,2);
const group=avatarGroup(task,state);assert.equal(group.children.length,4);assert.equal(group.children[3].textContent,'+2');assert.equal(group.attrs['aria-label'],'View all 5 activity participants');
const card=taskCard(task,state.runs[0],state),top=card.children[0];assert.equal(top.children[1].className,'participant-avatar-group');assert.ok(top.children[2].className.includes('status'));
renderTaskParticipants(state,'task');assert.equal($('task-participants').children.length,6);assert.equal($('task-participants').children[1].children[0].children[1].textContent,'Panel ID 00000004');assert.ok($('task-participants').children[1].children[1].textContent.includes('Development'));
assert.ok(!$('task-participants').children[1].children[0].children[1].textContent.includes('Private nickname'));
const stale={...state,agents:agents.map(a=>({...a,observed_at:observed-400}))};renderTaskParticipants(stale,'task');assert.ok($('task-participants').children[1].children[2].textContent.includes('State unconfirmed'));
const retained={...state,runs:[],agent_run_assignments:[{agent_id:'p0',run_id:'outside-window',task_id:'task',work_type:'writing',assigned_at:1}]};assert.equal(PanelAgents.activityParticipants(retained,'task').length,1);
language='zh';renderTaskParticipants(state,'task');assert.equal($('task-participants').children[1].children[0].children[1].textContent,'面板编号 00000004');assert.equal(JSON.stringify(state),before);
`,context);
assert.ok(!ids.has('page-agents'));assert.ok(!ids.has('agent-history'));assert.ok(!ids.has('agent-unknown'));
console.log('Activity participants: related-only dedup, avatar 3+N before status, full detail, role linkage, stale states, no standalone Agent page and bilingual IDs passed');

vm.runInContext(`
const summaryState={tasks:[{id:'radar-example',name:'Synthetic scheduled result',project:'Example'}],runs:[{id:'old',task_id:'radar-example',status:'paused',started:1,note:'Historical record'},{id:'new',task_id:'radar-example',status:'waiting_external',started:2,note:'Old initial instruction',next_step:'Wait for the first actual result'}]};
const summaryBefore=JSON.stringify(summaryState),work=PanelWorkspace.workProgress(summaryState,'radar-example');
assert.equal(work.open_runs.length,2);assert.equal(work.unpaused_runs.length,1);assert.equal(work.current_step,'Wait for the first actual result');
const summaryCard=taskCard(summaryState.tasks[0],null,summaryState);
assert.equal(summaryCard.children.find(n=>n.className==='task-summary').textContent,'Wait for the first actual result');
assert.ok(!summaryCard.children.some(n=>n.dataset?.disclosureKey==='parallel:radar-example'));assert.equal(JSON.stringify(summaryState),summaryBefore);
`,context);
console.log('Paused history retained outside compact unfinished count; latest run next step replaces old start note without state changes');
