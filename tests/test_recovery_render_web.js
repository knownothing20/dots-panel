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
const metrics={os:'Linux',architecture:'test',python:'3',scope:'Synthetic test',sampled_at:1};
const empty={metrics,tasks:[],runs:[],latest_runs:[],activity:[],events:[],schedules:[],software:[],agents:[],agent_assignments:[],bindings:[],artifacts:[],rules:{},about:{}};
render(empty);
for(const lang of ['en','zh']){
 language=lang;translatePage();
 const task={id:'synthetic',name:'<script>not HTML</script>',project:'Synthetic fixture',created:1};
 const run={id:'run',task_id:task.id,status:'waiting_user',started:1,updated:1,lifecycle_reason:'Need choice',next_step:'Choose',closeout:null};
 const state={...empty,tasks:[task],runs:[run],latest_runs:[run],agents:[{id:'agent',name:'Example',avatar:'mint',status:'idle',observed_at:1}],agent_assignments:[{task_id:task.id,agent_id:'agent',work_type:'testing'}],schedules:[{id:'schedule',name:'Schedule',source:'manual',state:'disconnected',updated:1}],software:[{id:'panel',name:'Panel',kind:'dots-panel',description:'Synthetic software',version:'0.2.0',available:true,verified_at:1}]};
 render(state);$('task-filter').value=task.id;render(state);setDetailTab('files');setDetailTab('timeline');
 adviceTaskId=task.id;render(state);assert.equal($('attention-advice').hidden,false);
 $('task-filter').value='';render(state);render(state);
 assert($('task-list').children.length>0);renderTaskParticipants(state,task.id);assert($('task-participants').children.length>0);
 assert.equal($('schedule-cards').style.gridTemplateColumns,undefined,'Schedule layout belongs to responsive CSS');

 for(const id of ['schedule-cards','software-cards']){const detail=$(id).children[0].children.find(node=>node.tag==='details');assert(detail);detail.open=true;detail.listeners.toggle();}
 render(state);
 for(const id of ['schedule-cards','software-cards'])assert($(id).children[0].children.find(node=>node.tag==='details').open);

}
`,context);
console.log('New full-page render smoke: real HTML IDs, empty/populated states, bilingual, agent/task details, file tabs, advice, repeated refresh passed');
