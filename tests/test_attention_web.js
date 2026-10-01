'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.attrs={};this.listeners={};this.value='';this.style={setProperty(){}};this.classList={toggle(){},remove(){},add(){},contains(){return false;}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attrs[k]=v;}
 getAttribute(k){return this.attrs[k];}
 removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,v){this.listeners[k]=v;}
 focus(){this.focused=true;document.activeElement=this;}
 contains(node){return this===node||this.children.some(child=>child.contains?.(node));}
 get firstChild(){return this.children[0];}
}
const ids=new Map();
const document={body:new Node(),documentElement:{},activeElement:null,createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){if(!ids.has(id))ids.set(id,new Node());return ids.get(id);},createElement(tag){return new Node(tag);},createTextNode(text){const n=new Node();n.textContent=text;return n;},querySelectorAll(){return [];}};
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:''},window:{addEventListener(){}},setInterval(){},AbortSignal:{timeout(){}},fetch:async()=>{throw Error('offline');},URL,console};
vm.createContext(context);
for(const f of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+f,'utf8'),context);
context.assert=assert;
vm.runInContext(`
const task={id:'one',name:'<script>Literal title</script>'};
const run={id:'new',task_id:'one',started:2,status:'waiting_user',lifecycle_reason:'Need scope',next_step:'Choose scope',updated:2,stale:true};
const state={tasks:[task,task],runs:[{...run,id:'old',started:1,status:'succeeded'},run,run]};
assert.equal(PanelWorkspace.attention(state).action_required.length,1);
assert.equal(PanelWorkspace.attention({tasks:[],runs:[]}).action_required.length,0);
assert.equal(typeof renderAttention,'undefined');
adviceTaskId='one';renderAdvice(task,run);
assert.equal($('attention-advice').hidden,false);assert.ok($('advice-text').value.includes('[please fill in]'));
assert.ok($('advice-note').textContent.includes('nothing has been sent'));
let prevented=false;$('advice-text').listeners.keydown({key:'Escape',preventDefault(){prevented=true;}});
assert.equal(prevented,true);assert.equal($('attention-advice').hidden,true);assert.equal(document.activeElement,$('back-conversations'));
const external={...state,latest_runs:[{...run,status:'waiting_external'}]};
assert.equal(PanelWorkspace.attention(external).action_required.length,0);
assert.equal(PanelWorkspace.attention(external).external.length,1);
language='zh';
adviceTaskId='one';renderAdvice(task,run);assert.ok($('advice-text').value.includes('[请填写]'));
renderAdvice(task,{...run,status:'running'});assert.equal($('attention-advice').hidden,true);assert.equal($('advice-text').value,'');
`,context);
assert.ok(!fs.readFileSync('web/index.html','utf8').includes('id="needs-attention"'));
console.log('Homepage attention block removed; lifecycle queue, safe bilingual detail suggestions and Escape focus preserved');

vm.runInContext(`
const artifact={id:'file',title:'<script>Final literal</script>',sha256:'hash',designation:'final',delivery_observations:[{status:'accepted',sha256:'hash'}]};
const close={id:'record',summary:'<b>Literal summary</b>',scope:'First pass review',verification:'untested',evidence:'Inspected manually',limits:'No automated tests',artifacts:[{artifact_id:'file'}],completed_at:5};
language='en';renderCloseout({status:'succeeded',closeout:close},{artifacts:[artifact]});
assert.equal($('closeout-pinned').hidden,false);
assert.ok($('closeout-pinned').children[0].textContent.includes('<b>Literal summary</b>'));
assert.ok($('closeout-pinned').children[1].textContent.includes('Untested'));
const delivery=PanelWorkspace.delivery(artifact,'en');assert.ok(delivery.includes('Transport accepted'));assert.ok(delivery.includes('User open unverified'));assert.ok(!delivery.includes('User open confirmed'));
let openedFiles=false;setDetailTab=tab=>{openedFiles=tab==='files';};const closebody=$('closeout-summary');closebody.children[closebody.children.length-1].listeners.click();assert.equal(openedFiles,true);
renderCloseout({status:'running',closeout:{...close,verification:'failed',completed_at:null}},{artifacts:[]});assert.ok($('closeout-summary').children[1].textContent.includes('not yet checked'));assert.ok($('closeout-summary').children[1].textContent.includes('Checks failed'));
renderCloseout({status:'succeeded'},{artifacts:[]});assert.ok($('closeout-summary').children[0].textContent.includes('Legacy completion'));assert.equal($('closeout-pinned').hidden,true);
renderCloseout({status:'running'},{artifacts:[]});assert.equal($('closeout-summary').hidden,true);
assert.ok(PanelWorkspace.delivery({...artifact,delivery_observations:[{status:'user_open_confirmed',sha256:'stale-hash'}]},'en').includes('User open unverified'));
language='zh';renderCloseout({status:'running',closeout:close},{artifacts:[artifact]});assert.ok($('closeout-pinned').children[1].textContent.includes('未测试'));
`,context);
console.log('Closeout pinned summary, verification/limits, delivery distinctions, legacy fallback, safe text and file navigation passed');

vm.runInContext(`
language='en';const doctor={checks:[{id:'schema',status:'ok'},{id:'bundled_skill',status:'ok'}],observations:{scheduler_configuration:{status:'verified',observed_at:1,evidence:'<script>Literal evidence</script>'},scheduler_execution:{status:'unknown'},account_task_skill:{status:'unknown'},account_personal_skill:{status:'unknown'}}};
renderDoctor(doctor);const doctorArea=$('about-doctor');assert.ok(doctorArea.children[0].textContent.includes('read-only'));
assert.ok(doctorArea.children.some(row=>row.textContent==='Scheduler configuration · Manually verified'));
assert.ok(doctorArea.children.some(row=>row.textContent==='Scheduler execution verification · Unverified'));
assert.ok(doctorArea.children.some(row=>row.textContent==='Account task Skill · Unverified'));
const doctorDetails=doctorArea.children.find(row=>row.tag==='details');assert.ok(doctorDetails.children.some(row=>row.textContent.includes('<script>Literal evidence</script>')));
renderDoctor(doctor);assert.equal(doctorArea.children.length,8);
language='zh';renderDoctor(doctor);assert.equal(doctorArea.children[0].textContent,'安装自检 · 只读');
renderDoctor();assert.equal(doctorArea.children[1].textContent,'尚未运行检查');
`,context);
console.log('Doctor bilingual read-only UI, manual setup/execution separation, literal evidence and refresh passed');
