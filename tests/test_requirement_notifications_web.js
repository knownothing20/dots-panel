'use strict';
const assert=require('node:assert/strict');require('../web/notifications.js');const {State,Storage}=PanelNotifications;
const base=(stream='synthetic-stream')=>({requirement_stream_id:stream,requirement_events:[],requirement_counters:{receipt:0,state:0,owner:0,link:0},requirements:[]});
function add(s,key='q',kind='receipt',status='received'){const id=s.requirement_events.length+1;s.requirement_events.push({id,kind,requirement_id:key,task_id:'t',source_event_id:'source-'+id});s.requirement_counters[kind]=id;let r=s.requirements.find(q=>q.id===key);if(!r){r={id:key,task_id:'t',summary:'Original '+key,source_event_id:'request-'+key,current_event_id:id,current_owner_event_id:0,status,owner:{},run_ids:['r']};s.requirements.push(r);}if(kind==='owner'){r.current_owner_event_id=id;r.owner={name:'Fern',actual_model:null};}else{r.current_event_id=id;r.status=status;}return r;}
const memory=()=>{const values=new Map();return {getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};};
{
 const s=base();add(s);const m=new State();assert(m.update(s).baseline);assert.equal(m.cards.length,0);add(s,'second');assert.equal(m.update(s).cards.length,1);add(s,'second','owner');assert.equal(m.update(s).cards.length,1);assert.equal(m.cards.length,1);assert.equal(m.cards[0].agent,'Fern');add(s,'second','state','pending_acceptance');m.update(s);assert.equal(m.cards[0].status,'pending_acceptance');assert.equal(m.update(s).changed.size,0);
 m.clear('conversations');assert.equal(m.counts().conversations,1);m.clear('conversations','t');assert.equal(m.counts().conversations,1);m.clear('conversations','t','second');assert.equal(m.counts().conversations,0);assert.equal(m.update(s).cards.length,0);
}
{
 const backend=memory(),s=base(),first=new State(new Storage(backend));first.update(s);add(s);first.update(s);const restarted=new State(new Storage(backend));assert.equal(restarted.counts().conversations,1);assert.equal(restarted.cards.length,1);assert.equal(restarted.update(s).changed.size,0);restarted.clear('conversations','t','q');const again=new State(new Storage(backend));assert.equal(again.update(s).cards.length,0);assert.equal(again.cards.length,0);add(s,'q','owner');const offline=new State(new Storage(backend));assert.equal(offline.update(s).cards.length,1);
}
for(const replacement of [true,false]){
 const s=base(),m=new State();m.update(s);const original=structuredClone(s);add(s);m.update(s);const changed=replacement?structuredClone(s):original;if(replacement)changed.requirement_stream_id='other';assert(m.update(changed).baseline);assert.equal(m.cards.length,0);assert.equal(m.counts().conversations,0);add(changed,'new');assert.equal(m.update(changed).cards.length,1);
}
{
 const s=base(),m=new State();m.update(s);add(s);m.update(s);s.requirement_events[0].source_event_id='rewrite';assert(m.update(s).baseline);assert.equal(m.cards.length,0);
}
{
 const storage=new Storage({getItem:()=>null,setItem:()=>{throw Error('Denied');}}),m=new State(storage),s=base();m.update(s);assert.equal(m.persistence,'session_only');assert.match(m.storage_error,/session-only/);add(s);m.update(s);assert.equal(m.counts().conversations,1);
}
{
 const storage=new Storage({getItem:()=>'{bad',setItem:()=>{}}),m=new State(storage);assert.equal(m.persistence,'session_only');assert(m.update(base()).baseline);
}
console.log('Persistent requirement notifications: receipt/owner/state, restart/offline, explicit read, source reset/rewind, storage failure passed');
{
 const backend=memory(),s=base(),m=new State(new Storage(backend));m.update(s);for(let i=0;i<2001;i++)add(s,'q'+i);assert.equal(m.update(s).cards.length,2001);assert.equal(m.counts().conversations,2001);assert.equal(m.cards.length,2001);
 s.runs=[{id:'legacy',task_id:'legacy-task',status:'running'}];m.update(s);assert(m.unread.conversations.has('requirement:q0'));assert.equal(m.counts().conversations,2002);
 const n=new State(new Storage(backend));assert.equal(n.counts().conversations,2002);assert.equal(n.cards.length,2001);assert.equal(n.update(s).changed.size,0);assert(n.cards.some(c=>c.id==='requirement:q0'));n.clear('conversations','t','q0');const again=new State(new Storage(backend));assert(!again.unread.conversations.has('requirement:q0'));assert.equal(again.counts().conversations,2001);
}
{
 const backend=memory();let fail=false;const storage=new Storage({getItem:k=>backend.getItem(k),setItem:(k,v)=>{if(fail)throw Error('Temporary write failure');backend.setItem(k,v);}}),s=base(),m=new State(storage);m.update(s);for(let i=0;i<2001;i++)add(s,'q'+i);fail=true;m.update(s);assert.equal(m.persistence,'session_only');assert.equal(m.counts().conversations,2001);fail=false;assert.equal(m.update(s).changed.size,0);assert.equal(m.persistence,'persistent');assert.equal(m.storage_error,null);const n=new State(new Storage(backend));assert.equal(n.counts().conversations,2001);assert.equal(n.cards.length,2001);assert(n.unread.conversations.has('requirement:q0'));
}
console.log('2001 requirement unread entries and cards survive restart, mixed legacy arrivals, explicit first-item read, and failed-write retry');
{
 const backend=memory(),s=base(),m=new State(new Storage(backend));m.update(s);add(s,'existing');m.update(s);let writes=0;const inaccessible=new Storage({getItem:()=>{throw Error('Temporary read failure');},setItem:()=>{writes++;}}),fresh=new State(inaccessible);fresh.update(s);add(s,'new');fresh.update(s);assert.equal(fresh.persistence,'session_only');assert.equal(writes,0);const reopened=new State(new Storage(backend));assert(reopened.unread.conversations.has('requirement:existing'));reopened.update(s);assert.equal(reopened.counts().conversations,2);
}
console.log('Failed initial storage reads never overwrite unloaded persisted unread state');
