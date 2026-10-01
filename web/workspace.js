'use strict';
// Lifecycle and record freshness are deliberately independent.
globalThis.PanelWorkspace = {
  verification(value,language='zh') {
    return ({passed:['检查通过','Checks passed'],failed:['检查失败','Checks failed'],untested:['未测试','Untested']}[value]||['未登记验证','Verification not recorded'])[language==='en'?1:0];
  },
  delivery(artifact,language='zh') {
    const en=language==='en',observed=new Set((artifact.delivery_observations||[]).filter(row=>row.sha256===artifact.sha256).map(row=>row.status));
    const designation=({draft:['草稿','Draft'],final:['最终稿','Final'],unclassified:['未指定版本','Unclassified']}[artifact.designation]||['未指定版本','Unclassified'])[en?1:0];
    const labels=[en?'Archived':'已归档',designation];
    for(const [status,zh,english] of [['sent','已记录发送','Sent recorded'],['accepted','传输已接收','Transport accepted'],['user_open_confirmed','用户打开已确认','User open confirmed']])if(observed.has(status))labels.push(en?english:zh);
    if(!observed.size)labels.push(en?'Delivery unverified':'交付未核验');
    if(!observed.has('user_open_confirmed'))labels.push(en?'User open unverified':'用户打开未核验');
    return labels.join(' · ');
  },
  attention(state) {
    const result={action_required:[],external:[]},seen=new Set();
    for(const row of this.rows(state.tasks||[],this.currentRuns(state))){
      if(seen.has(row.task.id)||!row.run)continue;seen.add(row.task.id);
      const group=['waiting_user','awaiting_review','paused'].includes(row.status)?'action_required':row.status==='waiting_external'?'external':null;
      if(group)result[group].push({task:row.task,run:row.run});
    }
    return result;
  },
  draft(task,run,language='zh') {
    const reason=run.lifecycle_reason||'—',next=run.next_step||'—';
    return language==='en'?`Regarding task ‘${task.name}’, please check its current status.\nRecorded reason: ${reason}\nSuggested next step: ${next}\nMy decision or additional information: [please fill in]`:`关于任务“${task.name}”，请先核对当前状态。\n记录原因：${reason}\n建议下一步：${next}\n我的决定或补充信息：[请填写]`;
  },
  // One chronological list, independent of input order and without mutating snapshots.
  timeline(state, taskId) {
    const runs=new Map([...(state.runs||[]),...(state.latest_runs||[]),...(state.current_runs||[]),...(state.open_runs||[])].filter(row=>!taskId||row.task_id===taskId).map(row=>[row.id,row]));
    const rows=(state.activity||[]).filter(row=>!taskId||row.task_id===taskId).map(row=>({...row,kind:'activity',key:'activity:'+row.id}));
    const mirrors=new Set(rows.map(row=>JSON.stringify([row.task_id,row.created,row.message])));
    for(const row of state.events||[])if(runs.has(row.run_id)&&!mirrors.has(JSON.stringify([runs.get(row.run_id).task_id,row.created,row.message])))rows.push({...row,kind:'event',task_id:runs.get(row.run_id).task_id,key:'event:'+row.id});
    for(const row of runs.values())if(row.note)rows.push({id:row.id,run_id:row.id,task_id:row.task_id,created:row.started,message:row.note,kind:'note',key:'note:'+row.id});
    const rank={activity:0,event:1,note:2},compare=(a,b)=>a<b?-1:a>b?1:0;
    return rows.sort((a,b)=>(Number(b.created)||0)-(Number(a.created)||0)||rank[a.kind]-rank[b.kind]||compare(String(a.id??''),String(b.id??''))||compare(a.message||'',b.message||''));
  },
  runSelection(state,taskId,now=Date.now()/1000,extra=null) {
    const runs=[...new Map([...(state.runs||[]),...(state.latest_runs||[]),...(state.current_runs||[]),...(state.open_runs||[]),...(extra?.task_id===taskId?[extra]:[])].filter(row=>row.task_id===taskId).map(row=>[row.id,row])).values()];
    const newest=(a,b)=>b.started-a.started||(a.id<b.id?1:a.id>b.id?-1:0);
    const openRuns=runs.filter(row=>['pending','running','waiting_user','waiting_external','paused','awaiting_review'].includes(row.status)).sort(newest);
    const freshAgents=new Set((state.agents||[]).filter(agent=>agent.status==='running'&&PanelAgents.observation(agent,state,now).recent).map(agent=>agent.id));
    const activeRuns=new Set((state.agent_run_assignments||[]).filter(link=>freshAgents.has(link.agent_id)).map(link=>link.run_id));
    const current=openRuns.find(row=>row.status==='running'&&activeRuns.has(row.id))||openRuns[0]||runs.slice().sort(newest)[0]||null;
    return {runs,openRuns,current};
  },
  currentRuns(state,now=Date.now()/1000) {
    return (state.tasks||[]).map(task=>this.runSelection(state,task.id,now).current).filter(Boolean);
  },
  activityRun(state,row,runs) {
    const ids=new Set(runs.map(run=>run.id));
    if(ids.has(row.run_id))return row.run_id;
    const linked=(state.progress_updates||[]).filter(update=>ids.has(update.run_id)&&(row.source_event_id==='progress-update:'+update.id||(row.stage==='progress'&&row.created===update.created&&String(row.message||'').split('\n',1)[0]===String(update.current_step||'').split('\n',1)[0]))).map(update=>update.run_id);
    linked.push(...(state.events||[]).filter(event=>ids.has(event.run_id)&&event.created===row.created&&event.message===row.message).map(event=>event.run_id));
    const unique=[...new Set(linked)];return unique.length===1?unique[0]:null;
  },
  workProgress(state, taskId, run=null,now=Date.now()/1000) {
    const {runs,openRuns,current:currentRun}=this.runSelection(state,taskId,now,run);
    const rows=this.timeline(state,taskId).filter(row=>row.kind!=='activity'||!['assignment','work_type','heartbeat'].includes(row.stage));
    const current=currentRun?rows.filter(row=>row.created>=currentRun.started&&(row.kind==='activity'?(!this.activityRun(state,row,runs)||this.activityRun(state,row,runs)===currentRun.id):row.run_id===currentRun.id)):rows;
    const meaningful=current.filter(row=>row.kind==='activity').sort((a,b)=>b.created-a.created||(String(a.id)<String(b.id)?1:String(a.id)>String(b.id)?-1:0));
    const stages=new Map();
    for(const row of meaningful)if(['planned','implementation','testing','review','delivered'].includes(row.stage)&&!stages.has(row.stage))stages.set(row.stage,row.state);
    const updates=(state.progress_updates||[]).filter(row=>row.run_id===currentRun?.id).slice().sort((a,b)=>b.created-a.created||(a.id<b.id?1:a.id>b.id?-1:0));
    const latest=meaningful[0]||current[0]||null;
    const recorded=updates[0]||null,update=recorded&&(!meaningful[0]||meaningful[0].created<=recorded.created)?recorded:null;
    const counts=currentRun?.status==='running'&&update&&typeof update.completed==='number'&&typeof update.total==='number'&&Number.isFinite(update.completed)&&Number.isFinite(update.total)&&update.completed>=0&&update.total>0&&update.completed<=update.total&&update.unit?{completed:update.completed,total:update.total,unit:update.unit}:null;
    const scope=!update&&meaningful[0]&&!this.activityRun(state,meaningful[0],runs)?'task':'run';
    return {latest,steps:current,update,updates,counts,scope,current_run:currentRun,current_run_id:currentRun?.id||null,
      open_runs:openRuns.map(({id,status,note,started})=>({id,status,note:note||'',started})),
      verified:[...stages.values()].filter(value=>value==='verified').length,total:stages.size};
  },
  progress(activity, taskId) {
    return (activity||[]).filter(item=>(!taskId||item.task_id===taskId)&&!['assignment','work_type'].includes(item.stage)).sort((a,b)=>b.created-a.created||(b.id||0)-(a.id||0));
  },
  summary(activity, taskId, language='zh') {
    const latest=this.progress(activity,taskId)[0];
    return latest?latest.message:(language==='en'?'No work progress recorded':'尚无工作进展摘要');
  },
  rows(tasks, runs, filter = 'all', query = '') {
    const latest = new Map();
    for (const run of runs) {
      if (!latest.has(run.task_id) || run.started > latest.get(run.task_id).started || (run.started === latest.get(run.task_id).started && (run.id||'') > (latest.get(run.task_id).id||''))) latest.set(run.task_id, run);
    }
    return tasks.map(task => {
      const run = latest.get(task.id) || null;
      return {task, run, status:run?.status || task.latest_status || 'pending', stale:Boolean(run?.stale)};
    }).filter(row => (filter === 'all' || row.status === filter || (filter === 'unfinished' && ['pending','running','waiting_user','waiting_external','paused','awaiting_review'].includes(row.status))) && (!query.trim() || `${row.task.name || ''} ${row.task.project || ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())));
  }
};

// Human-configured profile variants; never machine-translate user text.
globalThis.PanelAgents = {
  observation(agent,state={},now=Date.now()/1000) {
    const observed=Number(agent?.observed_at),age=now-observed;
    const known=typeof agent?.observed_at==='number'&&Number.isFinite(observed);
    return {known,recent:known&&age>=0&&age<=Number(state.stale_after_seconds??120),status:known?agent.status:'unknown'};
  },
  taskLead(state,taskId,now=Date.now()/1000) {
    const ownerId=(state.agent_assignments||[]).find(row=>row.task_id===taskId)?.agent_id;
    const agents=state.agents||[],owner=agents.find(row=>row.id===ownerId)||null;
    const runs=new Map([...(state.runs||[]),...(state.latest_runs||[]),...(state.current_runs||[]),...(state.open_runs||[])].filter(run=>run.task_id===taskId&&run.status==='running').map(run=>[run.id,run]));
    const active=agents.filter(agent=>this.observation(agent,state,now).recent&&agent.status==='running'&&((state.agent_run_assignments||[]).some(link=>link.agent_id===agent.id&&runs.has(link.run_id))||(agent.id===ownerId&&runs.size>0)));
    active.sort((a,b)=>(b.observed_at||0)-(a.observed_at||0)||(a.id<b.id?-1:a.id>b.id?1:0));
    return {agent:active[0]||owner,owner,active};
  },
  lifecycle(status, language='zh') {
    const labels={waiting_user:['等待用户','Waiting for user'],waiting_external:['等待外部结果','Waiting for external result'],paused:['已暂停记录','Recorded as paused'],awaiting_review:['等待验收','Awaiting review'],pending:['待开始','Pending'],running:['进行中','Running'],succeeded:['已完成','Succeeded'],failed:['失败','Failed'],cancelled:['已取消','Cancelled']};
    return (labels[status]||['未知','unknown'])[language==='en'?1:0];
  },
  text(agent, field, language='zh') { return (language==='en' && agent[field+'_en']) || agent[field] || ''; },
  type(value, language='zh') {
    const labels={unspecified:['未注明','Unspecified'],development:['编程开发','Development'],research:['资料搜集','Research'],testing:['测试验证','Testing'],review:['审查核对','Review'],writing:['内容写作','Writing'],coordination:['任务协调','Coordination']};
    return (labels[value]||labels.unspecified)[language==='en'?1:0];
  },
  work(state,agent) {
    const primary=(state.agent_assignments||[]).filter(a=>a.agent_id===agent.id);
    const scoped=(state.agent_run_assignments||[]).filter(a=>a.agent_id===agent.id);
    const result={current:[],unfinished:[],recent:[]};
    const runs=[...new Map([...(state.runs||[]),...(state.latest_runs||[]),...(state.current_runs||[]),...(state.open_runs||[])].map(run=>[run.id,run])).values()];
    for(const task of state.tasks||[]){
      let links=scoped.flatMap(a=>runs.filter(r=>r.id===a.run_id&&r.task_id===task.id).map(run=>({run,link:a})));
      const owner=primary.find(a=>a.task_id===task.id);
      if(!links.length&&owner){links=runs.filter(r=>r.task_id===task.id).map(run=>({run,link:owner}));if(!links.length)links=[{run:null,link:owner}];}
      for(const {run,link} of links){
        const status=run?.status||task.latest_status||'pending';
        const entry={task,run_id:run?.id||null,status,work_type:link.work_type||'unspecified'};
        if(['pending','running','waiting_user','waiting_external','paused','awaiting_review'].includes(status)){
          result.unfinished.push(entry);
          if(agent.status==='running'&&status==='running')result.current.push(entry);
        }else result.recent.push(entry);
      }
    }
    return result;
  }
};
