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
const {execFileSync}=require('node:child_process');
context.specs=JSON.parse(execFileSync('python3',['-c',"import json;from dots_panel.agent_identity import PORTRAITS,portrait_spec;print(json.dumps([portrait_spec({'portrait':p}) for p in PORTRAITS]))"],{env:{...process.env,PYTHONPATH:'src'}}));
vm.runInContext(`
const copy=node=>({tag:node.tag,attrs:node.attrs,text:node.textContent,children:node.children.map(copy)});
const observed=Date.now()/1000;
const a={id:'fixed',name:'青芽',name_en:'Qingya',status:'running',observed_at:observed,portrait:'leaf-mint',portrait_spec:specs[0],identity_source:'manual',identity_verification:'observed',identity_observed_at:observed,identity_evidence:'Matched through a supported observation',previous_names:[{name:'Old task label',name_en:'Old task label'}]};
const state={agents:[a],tasks:[{id:'goal',name:'Actual task'}],runs:[{id:'run',task_id:'goal',status:'running',started:observed}],agent_run_assignments:[{agent_id:'fixed',run_id:'run',assigned_at:observed,work_type:'development'}]};
const before=JSON.stringify(state);
for(const spec of specs){const portrait=agentAvatar({...a,portrait_spec:spec});assert.equal(portrait.attrs['aria-hidden'],'true');assert.equal(portrait.children[0].children.length,spec.shapes.length);assert.equal(portrait.children[0].attrs.viewBox,'0 0 64 64');}
const zh=JSON.stringify(copy(agentAvatar(a)));language='en';assert.equal(JSON.stringify(copy(agentAvatar({...a,name:'Different fixed display',work_type:'review'}))),zh);
renderAgents(state);let card=$('agent-cards').children[0];assert.equal(card.children[0].children[1].textContent,'Qingya');assert.ok(card.children[1].textContent.includes('Manually matched'));assert.ok(card.children[2].textContent.includes('Current work'));assert.ok(card.children[2].textContent.includes('Actual task'));
let details=card.children.find(n=>n.tag==='details');assert.ok(details.children.some(n=>n.textContent?.includes('Old task label')));details.open=true;details.listeners.toggle();
renderAgents(state);assert.equal($('agent-cards').children[0].children.find(n=>n.tag==='details').open,true);
const historical={...a,identity_source:'historical',identity_verification:'historical'};renderAgents({...state,agents:[historical]});card=$('agent-cards').children[0];assert.ok(card.children[1].textContent.includes('Historical profile'));assert.ok(!card.children[2].textContent.includes('Actual task'));assert.equal(PanelAgents.taskLead({...state,agents:[historical]},'goal').active.length,0);assert.equal(PanelAgents.taskLead({...state,agents:[historical]},'goal').assigned[0].id,'fixed');
const differentTimes={...a,identity_observed_at:946684800,observed_at:1609459200};
renderAgents({...state,agents:[differentTimes]});card=$('agent-cards').children[0];
const identityTime=card.children.find(n=>n.className==='agent-identity-time');
const statusTime=card.children.find(n=>n.className==='agent-observed');
assert.ok(identityTime.textContent.includes(stamp(946684800)));assert.ok(!identityTime.textContent.includes(stamp(1609459200)));
assert.ok(statusTime.textContent.includes(stamp(1609459200)));assert.ok(!statusTime.textContent.includes(stamp(946684800)));
language='zh';renderAgents(state);card=$('agent-cards').children[0];assert.equal(card.children[0].children[1].textContent,'青芽');assert.ok(card.children[1].textContent.includes('人工核验'));assert.ok(card.children[2].textContent.includes('当前职责'));assert.equal(JSON.stringify(state),before);
`,context);
console.log('Fixed portraits: all 48 shared shapes, locale/name independence, identity evidence, historical safety and retained disclosure verified');
