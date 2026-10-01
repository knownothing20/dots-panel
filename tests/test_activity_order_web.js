'use strict';
const assert=require('node:assert/strict');require('../web/workspace.js');
const tasks=['done','older','recent','tie'].map(id=>({id,name:id,created:1}));
const runs=tasks.map(task=>({id:task.id,task_id:task.id,status:task.id==='done'?'succeeded':'running',started:5,updated:9999,finished:task.id==='done'?1000:null}));
const state={tasks,runs,activity:[{task_id:'recent',created:20,stage:'testing'},{task_id:'tie',created:20,stage:'testing'},{task_id:'older',created:9000,stage:'heartbeat'}]};
const rows=()=>PanelWorkspace.rows(tasks,runs,'all','',state);
assert.deepEqual(rows().map(r=>r.task.id),['recent','tie','older','done']);
runs.push({id:'backup',task_id:'older',status:'succeeded',started:30,finished:40,updated:40});
assert.equal(rows()[0].task.id,'older');assert.equal(rows()[0].status,'running');
assert.deepEqual(PanelWorkspace.rows(tasks,runs,'unfinished','',state).map(r=>r.task.id),['older','recent','tie']);
assert.deepEqual(PanelWorkspace.rows(tasks,runs,'all','recent',state).map(r=>r.task.id),['recent']);
const before=JSON.stringify(state);rows();assert.equal(JSON.stringify(state),before);
console.log('Unfinished-first activity ordering: meaningful timestamps, heartbeat exclusion, deterministic ties, parallel runs and filters passed');

runs.find(row=>row.id==='older').status='failed'; runs.pop(); assert(rows().findIndex(row=>row.task.id==='older')>rows().findIndex(row=>row.task.id==='done')); assert.equal(rows().find(row=>row.task.id==='older').status,'failed');

const statuses=['waiting_user','failed','pending','running','paused','succeeded','waiting_external','awaiting_review','cancelled'];
const mixed={tasks:statuses.map((_,i)=>({id:'i'+i,name:'i'+i,created:1})),runs:statuses.map((status,i)=>({id:'r'+i,task_id:'i'+i,status,started:1,updated:999999})),activity:statuses.map((status,i)=>({task_id:'i'+i,created:status==='running'?10:1000+i,stage:'progress'}))};
const ordered=PanelWorkspace.rows(mixed.tasks,mixed.runs,'all','',mixed);
assert.equal(ordered[0].status,'running');
assert(ordered.slice(1,6).every(row=>['waiting_user','waiting_external','awaiting_review','pending','paused'].includes(row.status)));
assert(ordered.slice(6).every(row=>['succeeded','failed','cancelled'].includes(row.status)));
