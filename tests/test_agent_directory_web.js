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
const profile=(id,status='running',extra={})=>({id,name:id+' <literal>',status,observed_at:observed,identity_source:'manual',identity_verification:'observed',identity_observed_at:observed-1000,identity_evidence:'Verified synthetic executor match',...extra});
const base={agents:[profile('working'),profile('idle','idle'),profile('history','running',{identity_source:'historical',identity_verification:'historical'}),profile('stale','running',{observed_at:observed-400}),profile('unknown','running',{identity_verification:'unknown'})],tasks:[{id:'task',name:'Actual ongoing task'}],runs:[{id:'run',task_id:'task',status:'running',started:observed-1000}],agent_run_assignments:['working','idle','history','stale','unknown'].map(id=>({agent_id:id,run_id:'run',assigned_at:observed-500,work_type:'development'}))};
const before=JSON.stringify(base),button=key=>$('agent-summary').children.find(n=>n.dataset.focusKey==='agent-filter:'+key),count=key=>Number(button(key).children[0].textContent),card=id=>$('agent-cards').children.find(n=>n.dataset.agentId===id);
renderAgents(base);
assert.equal(count('all'),3);assert.equal(count('running'),1);assert.equal(count('idle'),1);assert.equal(count('unconfirmed'),1);
assert.equal($('agent-cards').children.length,3);assert.equal($('agent-history').open,false);assert.equal($('agent-history-cards').children.length,0);assert.ok($('agent-history-title').textContent.endsWith('1'));
assert.equal(card('unknown'),undefined);assert.equal($('agent-unknown').open,false);assert.equal($('agent-unknown-cards').children.length,0);
$('agent-unknown').open=true;$('agent-unknown').listeners.toggle();assert.equal($('agent-unknown-cards').children.length,1);assert.equal($('agent-unknown-cards').children[0].children[0].children[2].textContent,'Unverified identities');
$('agent-unknown').open=false;$('agent-unknown').listeners.toggle();assert.equal($('agent-unknown-cards').children.length,0);assert.ok($('agent-count-help-text').textContent.includes('Total profiles: 5'));
assert.equal(card('working').children.length,3);assert.equal(card('working').children[0].children[1].textContent,'working <literal>');assert.equal(card('working').children[0].children[2].textContent,'Working');assert.ok(card('working').children[1].textContent.includes('Current task'));
assert.equal(card('stale').children[0].children[2].textContent,'State unconfirmed');assert.ok(card('stale').children[1].textContent.includes('Recent task · Actual ongoing task'));
assert.ok(!card('working').children.some(n=>['agent-identity-time','agent-observed'].includes(n.className)));
const details=card('working').children[2];assert.equal(details.open,false);assert.ok(details.children.some(n=>n.className==='agent-identity-time'));assert.ok(details.children.some(n=>n.className==='agent-observed'));
button('running').focus();button('running').listeners.click();assert.equal($('agent-cards').children.length,1);assert.equal(document.activeElement.dataset.focusKey,'agent-filter:running');assert.equal(count('all'),3);
renderAgents(base);assert.equal(button('running').attrs['aria-pressed'],'true');assert.equal(document.activeElement.dataset.focusKey,'agent-filter:running');
const ended={...base,agents:base.agents.map(a=>a.id==='working'?{...a,status:'idle'}:a)};renderAgents(ended);assert.equal(count('running'),0);assert.equal(count('idle'),2);assert.equal(base.runs[0].status,'running');
button('unconfirmed').listeners.click();assert.equal($('agent-cards').children.length,1);assert.equal(card('unknown'),undefined);assert.equal($('agent-history').hidden,false);
$('agent-history').open=true;$('agent-history').listeners.toggle();assert.equal($('agent-history-cards').children.length,1);renderAgents(base);assert.equal($('agent-history').open,true);assert.equal($('agent-history-cards').children.length,1);
$('agent-history').open=false;$('agent-history').listeners.toggle();assert.equal($('agent-history-cards').children.length,0);
button('all').listeners.click();language='zh';renderAgents(base);assert.equal(button('all').children[1].textContent,'已核实 Agent');assert.equal(button('running').children[1].textContent,'工作中');assert.equal(card('stale').children[0].children[2].textContent,'状态待核实');assert.ok(card('stale').children[1].textContent.includes('最近任务'));
assert.equal(JSON.stringify(base),before);
renderAgents({agents:[],tasks:[],runs:[]});assert.equal(count('all'),0);assert.equal(count('running'),0);assert.equal($('agent-history').hidden,true);
`,context);
console.log('Directory UI: exact counts, filters, hidden history, recent task retention, compact cards, detail evidence, poll focus and bilingual refresh passed');

vm.runInContext(`
const summaryState={tasks:[{id:'radar-example',name:'Synthetic scheduled result',project:'Example'}],runs:[{id:'old',task_id:'radar-example',status:'paused',started:1,note:'Historical record'},{id:'new',task_id:'radar-example',status:'waiting_external',started:2,note:'Old initial instruction',next_step:'Wait for the first actual result'}]};
const summaryBefore=JSON.stringify(summaryState),work=PanelWorkspace.workProgress(summaryState,'radar-example');
assert.equal(work.open_runs.length,2);assert.equal(work.unpaused_runs.length,1);assert.equal(work.current_step,'Wait for the first actual result');
const summaryCard=taskCard(summaryState.tasks[0],null,summaryState);
assert.equal(summaryCard.children.find(n=>n.className==='task-summary').textContent,'Wait for the first actual result');
assert.ok(!summaryCard.children.some(n=>n.dataset?.disclosureKey==='parallel:radar-example'));assert.equal(JSON.stringify(summaryState),summaryBefore);
`,context);
console.log('Paused history retained outside compact unfinished count; latest run next step replaces old start note without state changes');
