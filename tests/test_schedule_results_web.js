'use strict';
// Synthetic state only. Fetch is a recording stub, never a network request.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(tag='div'){this.tag=tag;this.dataset={};this.children=[];this.attrs={};this.listeners={};this.style={};this.classList={toggle(){},remove(){},add(){},contains(){return false;}};}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=items;}
 setAttribute(k,v){this.attrs[k]=v;}
 getAttribute(k){return this.attrs[k];}
 removeAttribute(k){delete this.attrs[k];}
 addEventListener(k,v){this.listeners[k]=v;}
 set innerHTML(value){throw new Error('Result fields must never be rendered as HTML');}
}
const ids=new Map();
const document={body:new Node(),documentElement:{},createTreeWalker(){return {nextNode(){return false;}};},getElementById(id){if(!ids.has(id))ids.set(id,new Node());return ids.get(id);},createElement(tag){return new Node(tag);},querySelectorAll(){return [];}};
const fetches=[],intervals=[];
const context={document,NodeFilter:{SHOW_TEXT:4},localStorage:{getItem(){return 'en';}},navigator:{language:'en'},location:{hash:''},window:{addEventListener(){}},setInterval(cb,ms){intervals.push(ms);},AbortSignal:{timeout(){}},fetch:async path=>{fetches.push(path);throw Error('Synthetic offline');},console,assert};
vm.createContext(context);
for(const file of ['i18n.js','workspace.js','app.js'])vm.runInContext(fs.readFileSync('web/'+file,'utf8'),context);
vm.runInContext(`
function allNodes(node){return [node,...node.children.flatMap(allNodes)];}
function textOf(node){return allNodes(node).map(n=>n.textContent||'').join(' ');}
const item={id:'synthetic',name:'Synthetic Radar',project:'Example',state:'disconnected',source:'manual',next_run:946684800,updated:200,external_result:{
 repository:'example-owner/example-repo',ref:'main',status_path:'example/status.json',index_path:'example/index.json',platform_configuration:'unverified',sync_mode:'manual',checked_at:200,last_good_at:100,fetch_error:null,
 observation:{latest:{calendar_date:'2000-01-03',run_id:'synthetic-attempt',collected_at:'2000-01-03T08:00:00+08:00',status:'rejected',selected_count:0,stale:false},index:{generated_at:'2000-01-03T00:02:00Z',entry_count:2,latest_date:'2000-01-02'},evidence:{status_sha:'a'.repeat(40),index_sha:'b'.repeat(40),status_url:'https://github.com/example-owner/example-repo/blob/main/example/status.json',index_url:'https://github.com/example-owner/example-repo/blob/main/example/index.json'}}}};
const original=JSON.stringify(item);
for(const lang of ['en','zh']){
 language=lang;
 const result=scheduleResultView(item), rows=Object.fromEntries(result.rows);
 assert(result.label.includes(lang==='en'?'Results linked':'结果已接入'));
 assert(result.label.includes(lang==='en'?'config unverified':'配置未核验'));
 assert.equal(rows[lang==='en'?'Source stale flag':'源过期标记'],lang==='en'?'No':'否');
 assert.equal(rows[lang==='en'?'Selected count':'入选数'],'0');
 assert.equal(rows[lang==='en'?'Latest observed attempt date':'最近观察尝试日期'],'2000-01-03');
 assert.equal(rows[lang==='en'?'Accepted index latest date':'已接受索引最新日期'],'2000-01-02');
 assert.equal(rows[lang==='en'?'Last fetch check':'最近获取检查'],stamp(200));
 assert.equal(rows[lang==='en'?'Last successful fetch':'最近成功获取'],stamp(100));
 assert.equal(rows[lang==='en'?'Source collected at':'源采集时间'],stamp('2000-01-03T08:00:00+08:00'));
 assert(rows[lang==='en'?'Platform configuration':'平台配置'].includes(lang==='en'?'platform ID, enabled state and next due are unknown':'平台 ID、启用状态、下次执行时间均未知'));
 renderSchedules([item]);
 let card=$('schedule-cards').children[0],detail=card.children.find(node=>node.tag==='details');
 assert(!detail.open);assert(textOf(card).includes('2000-01-03'));assert(textOf(card).includes('2000-01-02'));
 assert(textOf($('automation-info-content')).includes(lang==='en'?'without polling GitHub':'不轮询 GitHub'));
 assert(!textOf($('schedule-cards')).includes(lang==='en'?'without polling GitHub':'不轮询 GitHub')); 
 assert(textOf($('schedule-summary')).includes(lang==='en'?'Configuration unverified':'配置待核实'));
 const surface=card.children.filter(node=>node.tag!=='details').map(textOf).join(' ');
 assert(surface.includes('2000-01-03')&&surface.includes('rejected'));
 assert(!surface.includes('2000-01-02')&&!surface.includes('example-owner')&&!surface.includes('synthetic-attempt'));
 assert.equal(card.children.length,5,'Closed card has title, state, cadence, latest result and one disclosure');
 detail.open=true;detail.listeners.toggle();renderSchedules([item]);
 detail=$('schedule-cards').children[0].children.find(node=>node.tag==='details');assert(detail.open);
 detail.open=false;detail.listeners.toggle();renderSchedules([item]);assert(!$('schedule-cards').children[0].children.find(node=>node.tag==='details').open);
 assert.equal(JSON.stringify(item),original);
}
language='en';
for(const [stale,expected] of [[true,'Yes'],[false,'No'],[null,'Unknown'],[undefined,'Unknown']]){
 item.external_result.observation.latest.stale=stale;
 assert.equal(Object.fromEntries(scheduleResultView(item).rows)['Source stale flag'],expected);
}
item.external_result.fetch_error='Synthetic <img src=x> failure';
item.external_result.observation.evidence.status_url='javascript:alert(1)';
renderSchedules([item]);
let card=$('schedule-cards').children[0];
assert(textOf(card).includes('Retaining last good snapshot'));
assert(allNodes(card.children.find(n=>n.tag==='details')).some(n=>n.textContent?.includes('Synthetic <img src=x> failure')));
assert(!card.children.filter(n=>n.tag!=='details').map(textOf).join(' ').includes('Synthetic <img'));
assert(card.children.some(n=>n.textContent?.includes('Check failed')));
assert(!allNodes(card).some(node=>node.tag==='img'||node.tag==='script'||node.href));
assert(textOf(card).includes('javascript:alert(1)'));
item.external_result.observation=null;item.external_result.last_good_at=null;
renderSchedules([item]);card=$('schedule-cards').children[0];
assert(textOf(card).includes('No result snapshot · config unverified'));
assert(textOf(card).includes('No successful snapshot'));
assert(textOf(card).includes('Last successful fetch: Not recorded'));
assert(!textOf(card).includes('Source run ID'));
item.external_result=null;renderSchedules([item]);
assert.equal(scheduleResultView(item),null);
assert(textOf($('schedule-cards')).includes('Registration does not create, start or resume a scheduler'));
item.platform_observation={platform:'example',task_id:'synthetic-platform-key',enabled:false,timezone:'UTC',schedule:'RRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=30',observed_at:100,next_run_at:null};
for(const lang of ['en','zh']){
 language=lang;renderSchedules([item]);card=$('schedule-cards').children[0];
 const surface=card.children.filter(n=>n.tag!=='details').map(textOf).join(' ');
 assert(surface.includes(lang==='en'?'Observed disabled':'已观察停用'));
 assert(surface.includes(lang==='en'?'Daily 08:30':'每天 08:30'));
 assert(!surface.includes('synthetic-platform-key'));
 assert(!surface.includes(lang==='en'?'Next run':'下次运行'));
 assert(textOf(card.children.find(n=>n.tag==='details')).includes('synthetic-platform-key'));
 assert.equal(t('任务'),lang==='en'?'Tasks':'任务');assert.equal(t('自动化'),lang==='en'?'Automations':'自动化');
 assert.equal(t('查看自动化'),lang==='en'?'View automations':'查看自动化');
 assert.equal(t('所有任务 / 进度记录'),lang==='en'?'All tasks / progress records':'所有任务 / 进度记录');
}
const sourceName='历史活动与定时任务';item.name=sourceName;renderSchedules([item]);assert.equal($('schedule-cards').children[0].children[0].textContent,sourceName,'User-authored names stay verbatim');
renderSchedules([]);assert($('schedule-cards').children.length>0);

`,context);
assert.deepEqual(fetches,['/api/state']);
assert.deepEqual(intervals,[5000]);
const html=fs.readFileSync('web/index.html','utf8');
assert(!html.includes('活动')&&!html.includes('定时任务'),'Static page headings and controls use current vocabulary');
assert(html.includes('id="automation-info"')&&!/id="automation-info"[^>]* open/.test(html),'Automation explanation starts collapsed');
console.log('Schedule results UI: bilingual evidence, distinct dates, stale tri-state, retained failure, safe text, persistent details, local-only refresh passed');
