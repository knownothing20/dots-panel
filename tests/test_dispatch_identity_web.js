'use strict';
const assert=require('node:assert/strict');
require('../web/workspace.js');
const s={tasks:[{id:'goal'}],runs:[{id:'run',task_id:'goal',status:'running',started:50}],agents:[{id:'worker',name:'Assigned worker',status:'running',observed_at:100},{id:'owner',name:'Old owner',status:'idle',observed_at:90}],agent_run_assignments:[{agent_id:'worker',run_id:'run',assigned_at:80}],agent_assignments:[{task_id:'goal',agent_id:'owner'}],stale_after_seconds:120};
const before=JSON.stringify(s);
assert.equal(PanelAgents.taskLead(s,'goal',110).active[0].id,'worker');
assert.equal(PanelAgents.taskLead(s,'goal',400).agent.id,'worker');
assert.equal(PanelAgents.taskLead(s,'goal',400).assigned[0].id,'worker');
assert.equal(PanelAgents.taskLead(s,'goal',400).active.length,0);
assert.equal(PanelAgents.observation(s.agents[0],s,400).recent,false);
assert.equal(PanelAgents.taskLead({...s,agent_assignments:[]},'goal',400).agent.id,'worker');
assert.equal(PanelAgents.runNames(s,'run','en'),'Assigned worker');
assert.equal(JSON.stringify(s),before);
for(const status of ['unknown','idle']) {
 const state={...s,agents:s.agents.map(a=>a.id==='worker'?{...a,status}:a)};
 assert.equal(PanelAgents.taskLead(state,'goal',400).agent.id,'worker');
 assert.equal(PanelAgents.taskLead(state,'goal',400).active.length,0);
}
s.runs.push({id:'waiting',task_id:'goal',status:'waiting_external',started:200});
assert.equal(PanelAgents.taskLead(s,'goal',400).run_id,'waiting');
assert.equal(PanelAgents.taskLead(s,'goal',400).assigned.length,0);
assert.equal(PanelAgents.taskLead(s,'goal',400).agent.id,'owner');
assert.equal(PanelWorkspace.workProgress(s,'goal',null,400).open_runs.length,2);
assert.equal(PanelAgents.runNames(s,'run','en'),'Assigned worker');
console.log('Assigned identity, stale observation and per-run parallel attribution checks passed');

const reassigned={...s,runs:[...s.runs,{id:'other',task_id:'new-goal',status:'running',started:85}],agent_run_assignments:[...s.agent_run_assignments,{agent_id:'worker',run_id:'other',assigned_at:90}]};
assert.equal(PanelAgents.taskLead(reassigned,'goal',110).active.length,0);
assert.equal(PanelAgents.taskLead(reassigned,'new-goal',110).active[0].id,'worker');
reassigned.runs.at(-1).status='succeeded';
assert.equal(PanelAgents.taskLead(reassigned,'goal',110).active.length,0);
