'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const code=fs.readFileSync(require('node:path').join(__dirname,'../web/app.js'),'utf8');
const render=code.slice(code.indexOf('function renderRules('),code.indexOf('function renderAbout('));
function element(tag,text='',className=''){return {tag,text,className,dataset:{},attrs:{},setAttribute(key,value){this.attrs[key]=value;},children:[],listeners:{},addEventListener(key,handler){this.listeners[key]=handler;},append(...items){this.children.push(...items);},replaceChildren(){this.children=[];}};}
const area=element('div');const context={language:'en',element,$:()=>area,stamp:v=>String(v),expandedSkills:new Set(),expandedRules:new Set()};vm.createContext(context);vm.runInContext(code.slice(code.indexOf('function disclosure('),code.indexOf('function captureView('))+render,context);
const skill={id:'example',scope:'user_installed',name:'示例',name_en:'Example',purpose:'用途',purpose_en:'<script>literal</script>',when_used:'使用',when_used_en:'When needed',status:'available',version_status:'unverified',observed_at:123,url:'https://chatgpt.com/skills?skill_id=example'};
const nodes=()=>{const out=[];function walk(n){out.push(n);n.children.forEach(walk);}walk(area);return out;};
context.renderRules({skills:[skill],skill_url:skill.url});
assert.equal(nodes().filter(n=>n.tag==='a').length,1);assert.equal(nodes().find(n=>n.tag==='a').rel,'noopener noreferrer');
assert(nodes().some(n=>n.text==='<script>literal</script>'));assert(nodes().some(n=>n.text.includes('Version unverified')));
assert(!nodes().some(n=>n.innerHTML));
context.language='zh';context.renderRules({skills:[skill]});assert(nodes().some(n=>n.text==='示例'));assert(nodes().some(n=>n.text==='使用场景：使用'));
for(const url of ['javascript:alert(1)','https://chatgpt.com.evil/skills?skill_id=x','https://chatgpt.com/skills?skill_id=x\n']){context.renderRules({skills:[{...skill,url}]});assert.equal(nodes().filter(n=>n.tag==='a').length,0);}
context.renderRules({skills:[{...skill,scope:'system'}]});assert(!nodes().some(n=>n.text==='示例'));assert(nodes().some(n=>n.text==='尚未登记用户 Skills'));
context.renderRules({});assert(nodes().some(n=>n.text==='尚未登记用户 Skills'));context.renderRules({skills:[skill]});assert.equal(nodes().filter(n=>n.tag==='section').length,1);context.renderRules({skills:[skill]});assert.equal(nodes().filter(n=>n.tag==='section').length,1);
const details=nodes().find(n=>n.tag==='details');assert.equal(details.open,false);details.open=true;details.listeners.toggle();context.renderRules({skills:[skill]});assert.equal(nodes().find(n=>n.tag==='details').open,true);assert.equal(area.children.filter(n=>n.className==='skill-grid').length,1);
console.log('Skill catalog rendering, localization, safe links, scope, empty state and repeated refresh passed');
