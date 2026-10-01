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
    const activeRuns=PanelAgents.observedRuns(state,now);
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
      unpaused_runs:openRuns.filter(r=>r.status!=='paused').map(({id,status,note,started})=>({id,status,note:note||'',started})),
      current_step:update?.current_step||meaningful[0]?.message||currentRun?.next_step||latest?.message||currentRun?.note||'',
      verified:[...stages.values()].filter(value=>value==='verified').length,total:stages.size};
  },
  progress(activity, taskId) {
    return (activity||[]).filter(item=>(!taskId||item.task_id===taskId)&&!['assignment','work_type'].includes(item.stage)).sort((a,b)=>b.created-a.created||(b.id||0)-(a.id||0));
  },
  summary(activity, taskId, language='zh') {
    const latest=this.progress(activity,taskId)[0];
    return latest?latest.message:(language==='en'?'No work progress recorded':'尚无工作进展摘要');
  },
  meaningfulUpdated(state,taskId) {
    const runs=new Map(['runs','latest_runs','current_runs','open_runs'].flatMap(key=>state[key]||[]).filter(row=>row.task_id===taskId).map(row=>[row.id,row]));
    const values=[...(state.tasks||[]).filter(row=>row.id===taskId).map(row=>row.created),...[...runs.values()].flatMap(row=>[row.started,row.finished]),...(state.activity||[]).filter(row=>row.task_id===taskId&&!['heartbeat','assignment','work_type'].includes(row.stage)).map(row=>row.created),...(state.progress_updates||[]).filter(row=>runs.has(row.run_id)).map(row=>row.created),...(state.events||[]).filter(row=>runs.has(row.run_id)&&row.kind!=='heartbeat'&&row.stage!=='heartbeat').map(row=>row.created)];
    return Math.max(0,...values.filter(value=>typeof value==='number'&&Number.isFinite(value)));
  },
  rows(tasks, runs, filter = 'all', query = '', state = null) {
    const latest = new Map();
    for (const run of runs) {
      if (!latest.has(run.task_id) || run.started > latest.get(run.task_id).started || (run.started === latest.get(run.task_id).started && (run.id||'') > (latest.get(run.task_id).id||''))) latest.set(run.task_id, run);
    }
    const snapshot=state||{tasks,runs};
    return tasks.map(task => {
      const run = PanelWorkspace.runSelection(snapshot,task.id).current || latest.get(task.id) || null;
      return {task, run, status:run?.status || task.latest_status || 'pending', stale:Boolean(run?.stale)};
    }).filter(row => (filter === 'all' || row.status === filter || (filter === 'unfinished' && ['pending','running','waiting_user','waiting_external','paused','awaiting_review'].includes(row.status))) && (!query.trim() || `${row.task.name || ''} ${row.task.project || ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))).sort((a,b)=>Number(['succeeded','cancelled'].includes(a.status))-Number(['succeeded','cancelled'].includes(b.status))||PanelWorkspace.meaningfulUpdated(snapshot,b.task.id)-PanelWorkspace.meaningfulUpdated(snapshot,a.task.id)||(a.task.id<b.task.id?-1:a.task.id>b.task.id?1:0));
  }
};

// Human-configured profile variants; never machine-translate user text.
globalThis.PanelAgents = {
  reference(agent,language='zh') {return (language==='en'?'Panel ID ':'面板编号 ')+(agent.panel_short_id||agent.id);},
  activityParticipants(state,taskId) {
    const agents=new Map((state.agents||[]).map(a=>[a.id,a])),runs=new Map(['runs','latest_runs','open_runs','current_runs'].flatMap(key=>state[key]||[]).map(r=>[r.id,r])),grouped=new Map();
    for(const link of state.agent_run_assignments||[]){if((link.task_id||runs.get(link.run_id)?.task_id)!==taskId||!agents.has(link.agent_id))continue;if(!grouped.has(link.agent_id))grouped.set(link.agent_id,[]);grouped.get(link.agent_id).push({run_id:link.run_id,work_type:link.work_type||'unspecified',assigned_at:link.assigned_at??null,source:'run'});}
    for(const link of state.agent_assignments||[])if(link.task_id===taskId&&agents.has(link.agent_id)&&!grouped.has(link.agent_id))grouped.set(link.agent_id,[{run_id:null,work_type:link.work_type||'unspecified',assigned_at:link.assigned_at??null,source:'owner'}]);
    const rows=[...grouped].map(([id,assignments])=>({agent:agents.get(id),assignments:assignments.sort((a,b)=>(b.assigned_at||0)-(a.assigned_at||0)||(a.run_id||'').localeCompare(b.run_id||''))}));
    return rows.sort((a,b)=>(b.assignments[0].assigned_at||0)-(a.assignments[0].assigned_at||0)||a.agent.id.localeCompare(b.agent.id));
  },
  directory(state,now=Date.now()/1000) {
    const finite=value=>typeof value==='number'&&Number.isFinite(value);
    const agents=[...new Map((state.agents||[]).map(a=>[a.id,a])).values()],tasks=new Map((state.tasks||[]).map(t=>[t.id,t]));
    const runs=new Map(['runs','latest_runs','current_runs','open_runs'].flatMap(key=>state[key]||[]).map(r=>[r.id,r]));
    const order=['running','idle','unconfirmed','blocked','unavailable'],open=new Set(['running','waiting_user','waiting_external','awaiting_review']);
    const counts={all:0,profiles:0,running:0,idle:0,unconfirmed:0,blocked:0,unavailable:0,historical:0,unverified:0},rows=[];
    for(const agent of agents){
      const historical=agent.identity_verification==='historical'||agent.identity_source==='historical';
      const links=(state.agent_run_assignments||[]).filter(a=>a.agent_id===agent.id);
      const latest=links.length&&links.every(a=>finite(a.assigned_at))?Math.max(...links.map(a=>a.assigned_at)):null;
      const latestLinks=latest===null?[]:links.filter(a=>a.assigned_at===latest),linked=latestLinks.map(a=>runs.get(a.run_id));
      const complete=linked.length>0&&linked.every(r=>r&&tasks.has(r.task_id)),work=[];
      if(complete){const pairs=linked.map((run,i)=>({run,link:latestLinks[i]})).sort((a,b)=>Number(!open.has(a.run.status))-Number(!open.has(b.run.status))||(b.run.started||0)-(a.run.started||0)||a.run.id.localeCompare(b.run.id));for(const {run,link} of pairs)if(!work.some(w=>w.task.id===run.task_id))work.push({task:tasks.get(run.task_id),run_id:run.id,status:run.status,work_type:link.work_type||'unspecified',source:'run'});}
      else if(!links.length){const owners=(state.agent_assignments||[]).filter(a=>a.agent_id===agent.id&&tasks.has(a.task_id)).slice().sort((a,b)=>(b.assigned_at||0)-(a.assigned_at||0)||b.task_id.localeCompare(a.task_id));if(owners.length){const a=owners[0];work.push({task:tasks.get(a.task_id),run_id:null,status:null,work_type:a.work_type||'unspecified',source:'owner'});}}
      const observation=this.observation(agent,state,now),verified=typeof agent.identity_evidence==='string'&&Boolean(agent.identity_evidence.trim())&&agent.identity_verification==='observed'&&agent.identity_source==='manual'&&finite(agent.identity_observed_at)&&agent.identity_observed_at<=now;
      let bucket='unconfirmed',reason='observation';
      if(historical)reason='historical';
      else if(!verified)reason='identity';
      else if(!observation.recent)reason='observation';
      else if(['idle','blocked','unavailable'].includes(agent.status))bucket=reason=agent.status;
      else if(agent.status==='running'){
        if(!complete)reason='assignment';
        else if(new Set(linked.map(r=>r.task_id)).size!==1)reason='conflict';
        else if(agent.observed_at<latest)reason='before_assignment';
        else if(!linked.some(r=>open.has(r.status)))reason=linked.some(r=>r.status==='paused')?'paused':'terminal';
        else bucket=reason='running';
      }
      counts.profiles++;counts.historical+=Number(historical);if(!historical){if(verified){counts.all++;counts[bucket]++;}else counts.unverified++;}rows.push({agent,state:bucket,reason,historical,verified:Boolean(verified&&!historical),work});
    }
    rows.sort((a,b)=>Number(a.historical)-Number(b.historical)||order.indexOf(a.state)-order.indexOf(b.state)||(b.agent.observed_at||0)-(a.agent.observed_at||0)||a.agent.id.localeCompare(b.agent.id));
    return {counts,rows};
  },
  directoryLabel(key,language='zh') {return ({all:['已核实 Agent','Verified agents'],running:['工作中','Working'],idle:['待命','Standby'],unconfirmed:['状态待核实','State unconfirmed'],unverified:['身份待核实档案','Unverified identities'],blocked:['受阻','Blocked'],unavailable:['不可用','Unavailable'],historical:['历史档案','Historical profiles']}[key]||['待核实','Unconfirmed'])[language==='en'?1:0];},
  directoryReason(key,language='zh') {
    const labels={historical:['历史留存，当前执行者未核实','Historical record; current executor unverified'],identity:['执行者对应关系尚未核实','Executor match is unverified'],observation:['状态观察缺失、过期或时间无效','Status observation is missing, expired or invalid'],assignment:['缺少当前有效运行关联或关联时间','Current valid run assignment or assignment time is missing'],conflict:['最新关联包含不同任务，当前归属待核实','Latest assignments span different tasks; current ownership is unconfirmed'],before_assignment:['状态观察早于最新分派','Status was observed before the latest assignment'],paused:['最新关联运行已暂停，不计为工作中','Latest assigned run is paused; not counted as working'],terminal:['最新关联运行已结束，不能据旧观察计为工作中','Latest assigned run is terminal; the old observation cannot establish working'],running:['近期运行观察、已核实身份及有效开放运行相符','Recent running observation, verified identity and valid open run agree'],idle:['近期观察为待命，不代表所关联任务已完成','Recently observed standby; associated tasks are not necessarily complete'],blocked:['近期观察为受阻','Recently observed blocked'],unavailable:['近期观察为不可用','Recently observed unavailable']};
    return (labels[key]||labels.observation)[language==='en'?1:0];
  },
  directoryWork(row,language='zh') {
    const en=language==='en';if(!row.work.length)return row.state==='unconfirmed'?(en?'Current task unconfirmed':'当前任务待核实'):(en?'No task recorded':'暂无任务记录');
    const label=row.state==='running'?(en?'Current task':'当前任务'):row.work[0].source==='owner'?(en?'Linked task':'关联任务'):(en?'Recent task':'最近任务');
    return label+' · '+row.work.map(w=>w.task.name).join(' / ');
  },
  observation(agent,state={},now=Date.now()/1000) {
    const observed=Number(agent?.observed_at),age=now-observed;
    const known=typeof agent?.observed_at==='number'&&Number.isFinite(observed);
    return {known,recent:known&&agent?.identity_verification!=='historical'&&age>=0&&age<=Number(state.stale_after_seconds??120),status:known?agent.status:'unknown'};
  },
  observedRuns(state,now=Date.now()/1000) {
    const runs=new Map(['runs','latest_runs','current_runs','open_runs'].flatMap(key=>state[key]||[]).map(run=>[run.id,run])),active=new Set();
    for(const agent of state.agents||[]) {
      if(agent.status!=='running'||!this.observation(agent,state,now).recent)continue;
      const links=(state.agent_run_assignments||[]).filter(link=>link.agent_id===agent.id);
      const latest=Math.max(...links.map(link=>link.assigned_at||0));
      const newest=links.filter(link=>(link.assigned_at||0)===latest).map(link=>runs.get(link.run_id));
      if(!newest.length||newest.some(run=>!run))continue;
      const topics=new Set(newest.map(run=>run.task_id));
      if(topics.size===1&&newest.some(run=>run.status==='running'))for(const link of links){const run=runs.get(link.run_id);if(run?.status==='running'&&topics.has(run.task_id))active.add(run.id);}
    }
    return active;
  },
  taskLead(state,taskId,now=Date.now()/1000) {
    const ownerId=(state.agent_assignments||[]).find(row=>row.task_id===taskId)?.agent_id;
    const agents=state.agents||[],owner=agents.find(row=>row.id===ownerId)||null;
    const current=PanelWorkspace.runSelection(state,taskId,now).current;
    const links=(state.agent_run_assignments||[]).filter(link=>current&&link.run_id===current.id&&agents.some(agent=>agent.id===link.agent_id)).slice().sort((a,b)=>(b.assigned_at||0)-(a.assigned_at||0)||(a.agent_id<b.agent_id?-1:a.agent_id>b.agent_id?1:0));
    const assigned=links.map(link=>agents.find(agent=>agent.id===link.agent_id));
    const active=(assigned.length?assigned:owner?[owner]:[]).filter(agent=>current?.status==='running'&&this.observation(agent,state,now).recent&&agent.status==='running'&&((state.agent_run_assignments||[]).some(link=>link.agent_id===agent.id)?this.observedRuns({...state,agents:[agent]},now).has(current.id):!assigned.length));
    active.sort((a,b)=>(b.observed_at||0)-(a.observed_at||0)||(a.id<b.id?-1:a.id>b.id?1:0));
    return {agent:active[0]||assigned[0]||owner,owner,active,assigned,run_id:current?.id||null};
  },
  runNames(state,runId,language='zh') {
    return (state.agent_run_assignments||[]).filter(link=>link.run_id===runId).map(link=>({link,agent:(state.agents||[]).find(agent=>agent.id===link.agent_id)})).filter(row=>row.agent).map(({link,agent})=>this.reference(agent,language)+' · '+this.type(link.work_type,language)).join(', ');
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
