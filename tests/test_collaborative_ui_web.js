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

context.pending=pending;
const run=script=>vm.runInContext(script,context);
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve();};
(async()=>{
run(`
const a={agent_id:'a',actor_name:'Old name',actor_name_en:'Old English',actor_short_id:'0123abcd',actor_display_id:'a',portrait:'leaf-sky',portrait_spec:{shapes:[{tag:'rect',attrs:{x:0,y:0,width:64,height:64,fill:'#fff'}}]},color_key:'0123abcd',work_type:'review',assignment_id:'ep'};
const fixture={tasks:[{id:'project',name:'Project',activity_kind:'project',collaboration_mode:'team',mode_source:'explicit'},{id:'child',name:'Child',parent_task_id:'project'},{id:'other',name:'Other'}],agents:[{id:'a',name:'Current name',panel_short_id:'changed',portrait:'bloom-mint'}],runs:[{id:'r',task_id:'project',started:1,status:'running'},{id:'c',task_id:'child',started:2,status:'running'}],agent_assignments:[{task_id:'project',agent_id:'a'}],assignment_episodes:[{id:'ep',task_id:'child',agent_id:'a',work_type:'review'}],activity:[{id:1,task_id:'project',created:1,stage:'implementation',message:'Legacy record'},{id:2,task_id:'child',created:2,stage:'review',message:'<script>Literal text</script>',attribution:a}],events:[{id:3,run_id:'c',created:2,message:'<script>Literal text</script>',attribution:{...a,agent_id:'b',actor_short_id:'22222222'}}]};
const before=JSON.stringify(fixture),known=PanelCollaboration.actor(fixture.activity[1],fixture,'en');
assert.equal(known.label,'Old English');assert.equal(known.shortId,'0123abcd');assert.equal(known.role,'Review');assert.equal(known.agent.portrait,'leaf-sky');assert(known.agent.portrait_spec);
assert.equal(PanelCollaboration.actor(fixture.activity[0],fixture,'en').known,false);
assert.equal(PanelCollaboration.actor({...fixture.activity[1],attribution:{...a,actor_short_id:undefined}},fixture,'en').shortId,'ID unrecorded');
assert.equal(PanelCollaboration.rows(fixture,'project').length,3,'Two explicit authors with identical content both survive');
assert.equal(PanelCollaboration.rows(fixture,'project',{agent:'unattributed'}).length,1);
assert.equal(PanelCollaboration.rows(fixture,'project',{role:'review',task:'child'}).length,2);
assert.equal(PanelCollaboration.rows(fixture,'project',{task:'other'}).length,0);
assert.equal(PanelCollaboration.rows(fixture,'project',{includeChildren:false}).length,1);
assert.equal(PanelCollaboration.mode({},'en'),'Unclassified');assert.equal(PanelCollaboration.actor(fixture.activity[0],fixture,'en').label,'Historical author unknown');
lastState=fixture;renderConversationStream(fixture,'project');
const messages=$('project-activity').children;assert.equal(messages.length,3);assert(messages.every(n=>n.tag==='article'));assert.equal(messages[1].children[0].children[0].children[0].tag,'svg','Event portrait uses shared native SVG spec');
assert(messages[1].children.some(n=>n.textContent==='<script>Literal text</script>'),'User text stays literal');
assert.equal($('conversation-task-label').hidden,false);
assert.equal(JSON.stringify(fixture),before);
$('detail-scroll').scrollTop=70;syncConversationHeader();assert($('detail-header').classList.contains('is-compact'));
$('detail-scroll').scrollTop=20;syncConversationHeader();assert($('detail-header').classList.contains('is-compact'));
$('detail-scroll').scrollTop=0;syncConversationHeader();assert(!$('detail-header').classList.contains('is-compact'));
`);
const initial=pending.find(p=>p.url.startsWith('/api/collaboration-timeline'));
assert(initial.url.includes('include_children=true'));assert(initial.url.includes('limit=100'));
run(`conversationFilters.agent='a';renderConversationStream(fixture,'project');`);
const filtered=pending.at(-1);assert(filtered.url.includes('agent_id=a'));
initial.resolve({ok:true,json:async()=>({rows:[{id:99,key:'activity:99',kind:'activity',task_id:'project',created:99,message:'STALE'}],total:1,limit:100,offset:0,has_more:false})});await flush();
run(`assert.equal(conversationRead.data,null,'Old in-flight response cannot overwrite newer filter');`);
filtered.resolve({ok:true,json:async()=>({rows:[{id:2,key:'activity:2',kind:'activity',task_id:'child',created:2,message:'FRESH',attribution:run('a')}],total:205,limit:100,offset:0,has_more:true})});await flush();
run(`assert.equal(conversationRead.data.total,205);assert.equal($('conversation-pagination').hidden,false);assert.equal($('conversation-next').disabled,false);assert.equal($('project-activity').children.length,1);assert.equal($('project-activity').children[0].children[2].textContent,'FRESH');
$('conversation-next').listeners.click();assert.equal(conversationOffset,100);`);
assert(pending.at(-1).url.includes('offset=100'));pending.at(-1).reject(Error('offline'));await flush();
run(`assert(conversationRead.error);assert($('conversation-note').textContent.includes('snapshot window'));`);
const html=fs.readFileSync('web/index.html','utf8');assert(html.indexOf('id="detail-more"')<html.indexOf('id="task-participants"'));assert(html.indexOf('id="task-participants"')<html.indexOf('id="timeline-panel"'));
assert(!html.match(/<details[^>]*id="detail-more"[^>]*\bopen/));
console.log('Collaborative UI: frozen author/role/portrait, unknown history, exact project filters, stable tints, literal text, compact header, full-history pagination and stale-response protection passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
