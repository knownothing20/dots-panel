'use strict';
const assert=require('node:assert/strict');require('../web/workspace.js');
const s={tasks:[{id:'goal'}],runs:[{id:'old',task_id:'goal',started:1,status:'running'},{id:'new',task_id:'goal',started:2,status:'succeeded'}],agent_assignments:[{task_id:'goal',agent_id:'owner',work_type:'development'}],agent_run_assignments:[{run_id:'old',agent_id:'a',work_type:'testing'},{run_id:'old',agent_id:'b',work_type:'review'}]};
for(const id of ['owner','a','b']){const w=PanelAgents.work(s,{id,status:'running'});assert.equal(w.current.length,1);assert.equal(w.current[0].run_id,'old');}
assert.equal(PanelAgents.work(s,{id:'a',status:'idle'}).current.length,0);
assert.equal(PanelAgents.work(s,{id:'owner',status:'running'}).recent.length,1);
assert.equal(PanelAgents.work(s,{id:'a',status:'running'}).recent.length,0);
console.log('Parallel participant, legacy owner, finished turn and overlapping run checks passed');
