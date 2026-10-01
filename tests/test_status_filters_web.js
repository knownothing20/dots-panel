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
const document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){if(!ids.has(id))ids.set(id,new Node());return ids.get(id);},createElement(tag){return new Node(tag);},createTextNode(text){const n=new Node();n.textContent=text;return n;},querySelectorAll(){return [];}};
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:''},window:{addEventListener(){}},setInterval(){},AbortSignal:{timeout(){}},fetch:async()=>{throw Error('offline');},URL,console};
vm.createContext(context);
for(const f of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+f,'utf8'),context);
context.assert=assert;
vm.runInContext(`
const allStatuses=['pending','running','waiting_user','waiting_external','paused','awaiting_review','succeeded','failed','cancelled'];
const state={tasks:allStatuses.map(id=>({id,name:id,project:'Demo'})),runs:allStatuses.filter(s=>s!=='pending').map(status=>({id:status,task_id:status,status,started:1}))};
lastState=state;
renderStatusFilters(state);
const bars=[$('workspace-tabs'),$('activity-tabs')];
for(const bar of bars){assert.equal(bar.children.length,4);assert.equal(bar.children[0].textContent,'All 9');assert.equal(bar.children[1].textContent,'Unfinished 6');assert.equal(bar.children[2].textContent,'Completed 1');assert.equal(bar.lastElementChild.options.length,10);}
const before=bars[0].children.slice();
render=(state)=>renderStatusFilters(state);
bars[1].children[1].listeners.click();assert.equal(workspaceFilter,'unfinished');
assert.equal(PanelWorkspace.rows(state.tasks,state.runs,workspaceFilter).length,6);
assert.equal(bars[0].children[1].attrs['aria-pressed'],'true');
const more=bars[0].lastElementChild;more.value='failed';more.listeners.change();
assert.equal(workspaceFilter,'failed');assert.equal(bars[1].lastElementChild.value,'failed');
more.focus();renderStatusFilters(state);assert.equal(document.activeElement,more);assert.equal(more.value,'failed');
assert.equal(bars[0].children[0],before[0]);assert.equal(bars[0].lastElementChild,more);
document.activeElement=null;language='zh';renderStatusFilters(state);
assert.equal(bars[0].children[1].textContent,'未完成 6');assert.equal(more.options.find(o=>o.value==='failed').textContent,'失败 1');
assert.equal(PanelWorkspace.rows(state.tasks,state.runs,'unfinished','missing').length,0);
assert.equal(PanelWorkspace.rows(state.tasks,state.runs,'cancelled').length,1);
assert.equal(PanelWorkspace.rows(state.tasks,state.runs,'succeeded').length,1);
renderStatusFilters({tasks:[],runs:[]});assert.equal(more.value,'failed');assert.equal(more.options.find(o=>o.value==='failed').textContent,'失败 0');
`,context);
console.log('Compact filters: both pages, all lifecycle states, counts, bilingual labels, shared selection, search isolation, stable focus/control identity and empty refresh passed');
