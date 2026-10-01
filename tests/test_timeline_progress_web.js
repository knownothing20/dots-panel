'use strict';
const assert=require('node:assert/strict');
require('../web/workspace.js');
const state={
  metrics:{sampled_at:1000},stale_after_seconds:120,
  tasks:[{id:'goal'},{id:'other'}],
  runs:[{id:'earlier',task_id:'goal',started:10,status:'running',note:'Initial request'},{id:'latest',task_id:'goal',started:100,status:'running',note:'Continue implementation'},{id:'elsewhere',task_id:'other',started:15,status:'running',note:'Unrelated'}],
  latest_runs:[{id:'latest',task_id:'goal',started:100,status:'running',note:'Continue implementation'}],
  activity:[{id:2,task_id:'goal',created:20,stage:'implementation',state:'verified',message:'Older milestone'},{id:1,task_id:'goal',created:100,stage:'testing',state:'in_progress',message:'Test cases prepared'},{id:3,task_id:'goal',created:200,stage:'assignment',message:'Owner changed'}],
  events:[{id:2,run_id:'latest',created:100,message:'Started checking'},{id:1,run_id:'latest',created:100,message:'Another step'},{id:4,run_id:'earlier',created:250,message:'Earlier parallel work finished'},{id:9,run_id:'elsewhere',created:999,message:'Other task'}],
  agents:[{id:'owner',name:'Owner',status:'idle',observed_at:990},{id:'worker',name:'Active contributor',status:'running',observed_at:980},{id:'old',status:'running',observed_at:200},{id:'future',status:'running',observed_at:1001},{id:'unseen',status:'running',observed_at:null}],
  agent_assignments:[{task_id:'goal',agent_id:'owner'}],
  agent_run_assignments:[{run_id:'earlier',agent_id:'worker'},{run_id:'latest',agent_id:'old'},{run_id:'latest',agent_id:'future'},{run_id:'latest',agent_id:'unseen'}]
};
const before=JSON.stringify(state);
const timeline=PanelWorkspace.timeline(state,'goal');
assert.deepEqual(timeline.map(r=>r.key),['event:4','activity:3','activity:1','event:1','event:2','note:latest','activity:2','note:earlier']);
assert.equal(timeline.filter(r=>r.kind==='note').length,2,'All task runs have start notes, no duplicate latest run');
assert(!timeline.some(r=>r.message==='Other task'));
const shuffled={...state,runs:[...state.runs].reverse(),activity:[...state.activity].reverse(),events:[...state.events].reverse()};
assert.deepEqual(PanelWorkspace.timeline(shuffled,'goal'),timeline,'Timestamp and kind/id ties are deterministic');
assert.equal(JSON.stringify(state),before,'Source snapshot is never mutated');
const mirrored={...state,activity:[...state.activity,{id:11,task_id:'goal',created:300,stage:'state_changed',message:'Waiting for review'}],events:[...state.events,{id:12,run_id:'latest',created:300,message:'Waiting for review'},{id:13,run_id:'latest',created:301,message:'Waiting for review'}]};
const merged=PanelWorkspace.timeline(mirrored,'goal');
assert.equal(merged.filter(row=>row.message==='Waiting for review').length,2,'Only exact same-time activity/event mirrors are deduplicated');
assert(merged.some(row=>row.key==='activity:11'));assert(!merged.some(row=>row.key==='event:12'));assert(merged.some(row=>row.key==='event:13'));

let work=PanelWorkspace.workProgress(state,'goal',state.runs[1]);
assert.equal(work.latest.message,'Test cases prepared','Current-run milestones lead; other parallel run logs stay in the full timeline');
assert.equal(work.total,1,'Old-run stages do not become a made-up completion percentage');
assert.equal(work.verified,0);
assert.equal(work.counts,null,'Missing measurements remain unknown');
const update={id:'update-a',run_id:'latest',created:260,current_step:'Check examples',result:'Cases discovered',next_step:'Run checks',evidence:'Example case list',completed:0,total:6,unit:'checks'};
state.progress_updates=[update,{...update,id:'unrelated',run_id:'elsewhere',created:999}];
work=PanelWorkspace.workProgress(state,'goal',state.runs[1]);
assert.equal(work.update.id,'update-a');assert.deepEqual(work.counts,{completed:0,total:6,unit:'checks'});
for(const fields of [{completed:null,total:null},{completed:1,total:0},{completed:7,total:6},{completed:NaN,total:6},{completed:'3',total:6}]){
  assert.equal(PanelWorkspace.workProgress({...state,progress_updates:[{...update,...fields}]},'goal').counts,null);
}
assert.equal(PanelAgents.taskLead(state,'goal',1000).agent.id,'worker','Fresh parallel contributor leads despite idle original owner');
assert.equal(PanelAgents.taskLead(state,'goal',1000).owner.id,'owner','Original ownership is preserved');
assert.deepEqual(PanelAgents.taskLead(state,'goal',1000).active.map(a=>a.id),['worker']);
assert.equal(PanelAgents.taskLead(state,'goal',1200).agent.id,'owner','Stale observation cannot prove current activity');
assert.equal(PanelAgents.observation(state.agents[4],state,1000).known,false);
assert.equal(PanelAgents.observation(state.agents[3],state,1000).recent,false,'Future observations are not fresh');
assert.equal(PanelAgents.taskLead({...state,runs:state.runs.map(r=>({...r,status:'succeeded'})),latest_runs:[]},'goal',1000).active.length,0,'Finished run never indicates current execution');
const outside={...state,runs:[],latest_runs:[state.runs[1]],agent_run_assignments:[{agent_id:'worker',run_id:'latest'}]};
assert.equal(PanelAgents.taskLead(outside,'goal',1000).agent.id,'worker','Latest runs outside bounded history remain visible');
// Starting a new run cannot inherit a finished run's measured completion.
const finished={...state.runs[1],status:'succeeded'},fresh={id:'fresh',task_id:'goal',started:400,status:'running',note:'New request'};
const restarted={...state,runs:[finished,fresh],latest_runs:[fresh],activity:[],events:[],progress_updates:[{...update,completed:576,total:576,unit:'checks'}]};
work=PanelWorkspace.workProgress(restarted,'goal');assert.equal(work.update,null);assert.equal(work.counts,null);assert.equal(work.latest.message,'New request');assert.equal(work.steps.length,1);
const review={...state,runs:[{...state.runs[1],status:'awaiting_review'}],latest_runs:[]};
work=PanelWorkspace.workProgress(review,'goal');assert.equal(work.counts,null,'Waiting for review never displays a live completion meter');
const superseded={...state,activity:[...state.activity,{id:9,task_id:'goal',created:300,stage:'review',state:'in_progress',message:'New finding supersedes measured work'}]};
work=PanelWorkspace.workProgress(superseded,'goal');assert.equal(work.update,null);assert.equal(work.counts,null);assert.equal(work.latest.message,'New finding supersedes measured work');
assert.equal(work.updates.length,1,'Superseded structured evidence remains available in history');
// A completed parallel backup never replaces the older unfinished UI run.
const uiRun={id:'ui',task_id:'goal',started:100,status:'running',note:'Improve the interface'};
const backupRun={id:'backup',task_id:'goal',started:500,status:'succeeded',note:'Archive a backup'};
const parallel={...state,runs:[uiRun,backupRun],latest_runs:[backupRun],activity:[],events:[],progress_updates:[{...update,run_id:'ui'},{...update,id:'backup-counts',run_id:'backup',created:510,completed:576,total:576}]};
work=PanelWorkspace.workProgress(parallel,'goal',backupRun);
assert.equal(work.current_run_id,'ui','Supplied newer completed display run cannot override unfinished work');
assert.equal(work.update.run_id,'ui');assert.deepEqual(work.counts,{completed:0,total:6,unit:'checks'});assert.equal(work.scope,'run');
assert.deepEqual(work.open_runs,[{id:'ui',status:'running',note:'Improve the interface',started:100}]);
for(const status of ['waiting_user','waiting_external','paused','awaiting_review']){
  const waiting={...parallel,runs:[{...uiRun,status},backupRun]};
  work=PanelWorkspace.workProgress(waiting,'goal',backupRun);assert.equal(work.current_run_id,'ui');assert.equal(work.counts,null);
}
const ordinary={...parallel,activity:[{id:20,task_id:'goal',created:520,stage:'review',state:'in_progress',message:'Task-wide review note'}]};
work=PanelWorkspace.workProgress(ordinary,'goal');
assert.equal(work.current_run_id,'ui');assert.equal(work.scope,'task','A run-less ordinary milestone is task-scoped');assert.equal(work.counts,null);assert.equal(work.latest.message,'Task-wide review note');assert.equal(work.latest.run_id,undefined,'Do not assign an invented run to task-wide evidence');
const twoOpen={...parallel,runs:[uiRun,{id:'second',task_id:'goal',status:'paused',started:200,note:'Another open thread'},backupRun]};
work=PanelWorkspace.workProgress(twoOpen,'goal');assert.equal(work.current_run_id,'second');assert.deepEqual(work.open_runs.map(row=>row.id),['second','ui']);
const allClosed={...parallel,runs:[{...uiRun,status:'succeeded'},backupRun]};work=PanelWorkspace.workProgress(allClosed,'goal');assert.equal(work.current_run_id,'backup');assert.equal(work.open_runs.length,0);assert.equal(work.counts,null);
const waitingRun={id:'decision',task_id:'goal',status:'waiting_user',started:200,note:'Confirm scope',lifecycle_reason:'Choose scope'};
const waitingOlder={...parallel,runs:[waitingRun,backupRun],latest_runs:[backupRun],agents:[],activity:[],events:[]};
work=PanelWorkspace.workProgress(waitingOlder,'goal',backupRun,1000);assert.equal(work.current_run.status,'waiting_user');assert.equal(work.counts,null);assert.equal(PanelWorkspace.attention(waitingOlder).action_required[0].run.id,'decision');
const activeOlder={...parallel,runs:[uiRun,waitingRun,backupRun],latest_runs:[backupRun],agents:[{id:'fresh',status:'running',observed_at:980}],agent_run_assignments:[{agent_id:'fresh',run_id:'ui'}],stale_after_seconds:120};
work=PanelWorkspace.workProgress(activeOlder,'goal',waitingRun,1000);assert.equal(work.current_run_id,'ui','Fresh explicitly assigned execution takes priority over a newer waiting run');assert.equal(work.open_runs.length,2);
assert.equal(PanelWorkspace.workProgress(activeOlder,'goal',null,1200).current_run_id,'decision','Expired observation returns to the newest unfinished run');
assert.equal(PanelWorkspace.workProgress({...activeOlder,agents:[{id:'fresh',status:'running',observed_at:1001}]},'goal',null,1000).current_run_id,'decision','Future observation cannot create execution priority');
assert.equal(PanelWorkspace.workProgress({...activeOlder,agent_run_assignments:[]},'goal',null,1000).current_run_id,'decision','Name/status alone cannot establish run execution');
const markedBackup={...activeOlder,activity:[{id:30,task_id:'goal',created:510,stage:'progress',source_event_id:'progress-update:backup-counts',message:'Backup check complete'}]};
work=PanelWorkspace.workProgress(markedBackup,'goal',null,1000);assert.equal(work.update.run_id,'ui','Explicitly attributed other-run progress cannot replace current work');assert.equal(work.scope,'run');assert(!work.steps.some(row=>row.id===30));
const mirroredBackup={...activeOlder,activity:[{id:31,task_id:'goal',created:511,stage:'state_changed',message:'Backup completed'}],events:[{id:32,run_id:'backup',created:511,message:'Backup completed'}]};
work=PanelWorkspace.workProgress(mirroredBackup,'goal',null,1000);assert.equal(work.update.run_id,'ui');assert(!work.steps.some(row=>row.message==='Backup completed'));
const legacyBackup={...activeOlder,activity:[{id:33,task_id:'goal',created:510,stage:'progress',message:'Check examples\nBackup measurements'}]};
work=PanelWorkspace.workProgress(legacyBackup,'goal',null,1000);assert.equal(work.update.run_id,'ui','Legacy structured progress links by timestamp and first message line');
const markedCurrent={...activeOlder,activity:[{id:34,task_id:'goal',run_id:'ui',created:530,stage:'review',message:'Current run review'}]};
work=PanelWorkspace.workProgress(markedCurrent,'goal',null,1000);assert.equal(work.scope,'run');assert.equal(work.latest.message,'Current run review');assert.equal(work.counts,null);
const oldOutsideWindow={...activeOlder,runs:[backupRun],latest_runs:[backupRun],current_runs:[],open_runs:[uiRun,waitingRun]};
work=PanelWorkspace.workProgress(oldOutsideWindow,'goal',null,1000);assert.equal(work.current_run_id,'ui');assert.equal(work.open_runs.length,2);assert(PanelWorkspace.timeline(oldOutsideWindow,'goal').some(row=>row.key==='note:ui'));assert.equal(PanelAgents.taskLead(oldOutsideWindow,'goal',1000).agent.id,'fresh');assert(PanelAgents.work(oldOutsideWindow,oldOutsideWindow.agents[0]).current.some(row=>row.run_id==='ui'));
console.log('Timeline/progress: deterministic chronology, all start notes, real counts, isolated task scope, no mutation and fresh active-participant leadership passed');
