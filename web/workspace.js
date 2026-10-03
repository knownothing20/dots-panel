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
    const mirrors=new Set(rows.filter(row=>!row.attribution).map(row=>JSON.stringify([row.task_id,row.created,row.message])));
    for(const row of state.events||[])if(runs.has(row.run_id)&&(row.attribution||!mirrors.has(JSON.stringify([runs.get(row.run_id).task_id,row.created,row.message]))))rows.push({...row,kind:'event',task_id:runs.get(row.run_id).task_id,key:'event:'+row.id});
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
    const priority=status=>status==='running'?0:['succeeded','cancelled','failed'].includes(status)?2:1;
    return tasks.map(task => {
      const run = PanelWorkspace.runSelection(snapshot,task.id).current || latest.get(task.id) || null;
      return {task, run, status:run?.status || task.latest_status || 'pending', stale:Boolean(run?.stale)};
    }).filter(row => (filter === 'all' || row.status === filter || (filter === 'unfinished' && ['pending','running','waiting_user','waiting_external','paused','awaiting_review'].includes(row.status))) && (!query.trim() || `${row.task.name || ''} ${row.task.project || ''}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))).sort((a,b)=>priority(a.status)-priority(b.status)||PanelWorkspace.meaningfulUpdated(snapshot,b.task.id)-PanelWorkspace.meaningfulUpdated(snapshot,a.task.id)||(a.task.id<b.task.id?-1:a.task.id>b.task.id?1:0));
  }
};

// Human-configured profile variants; never machine-translate user text.
globalThis.PanelAgents = {
  reference(agent,language='zh') {return (language==='en'?'Panel ID ':'面板编号 ')+(agent.panel_short_id||agent.id);},
  activityParticipants(state,taskId,now=Date.now()/1000) {
    const run=PanelWorkspace.runSelection(state,taskId,now).current;
    if(!run||!['pending','running','waiting_user','waiting_external','awaiting_review'].includes(run.status))return [];
    const agents=new Map((state.agents||[]).map(a=>[a.id,a])),links=new Map(),episodes=new Map();
    for(const [source,group] of [[state.agent_run_assignments||[],links],[state.assignment_episodes||[],episodes]])for(const entry of source){
      if(entry.run_id!==run.id||(entry.task_id??taskId)!==taskId||!agents.has(entry.agent_id))continue;
      if(!group.has(entry.agent_id))group.set(entry.agent_id,[]);group.get(entry.agent_id).push(entry);
    }
    const rows=[];
    for(const id of new Set([...links.keys(),...episodes.keys()])){
      const candidates=(episodes.has(id)?episodes.get(id).filter(a=>a.ended_at==null):links.get(id)).filter(a=>typeof a.assigned_at==='number'&&Number.isFinite(a.assigned_at)&&a.assigned_at>=0&&a.assigned_at<=now);
      if(!candidates.length)continue;
      const assignment=candidates.slice().sort((a,b)=>b.assigned_at-a.assigned_at||(b.id||'').localeCompare(a.id||''))[0];
      rows.push({agent:agents.get(id),assignments:[{run_id:run.id,work_type:assignment.work_type||'unspecified',assigned_at:assignment.assigned_at,source:'run',execution_config:Object.fromEntries(['requested_model','requested_effort','actual_model','actual_effort','config_verification','config_provider','config_observed_at','config_evidence'].map(k=>[k,assignment[k]??(k==='config_verification'?'unknown':null)]))}]});
    }
    return rows.sort((a,b)=>b.assignments[0].assigned_at-a.assignments[0].assigned_at||a.agent.id.localeCompare(b.agent.id));
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


// Explicit event attribution only. Assignment history is never evidence of authorship.
globalThis.PanelCollaboration = {
  palette:['#eef5ef','#edf3fa','#f8f0e8','#f1eef8','#f8edf1','#eef5f5'],
  scope(state,taskId,includeChildren=true) {
    const task=(state.tasks||[]).find(row=>row.id===taskId),ids=new Set(taskId?[taskId]:[]);
    if(includeChildren&&task?.activity_kind==='project')for(const child of state.tasks||[])if(child.parent_task_id===taskId)ids.add(child.id);
    return ids;
  },
  participants(state,taskId) {
    const merged=new Map();
    for(const id of this.scope(state,taskId))for(const row of PanelAgents.activityParticipants(state,id)){
      if(!merged.has(row.agent.id))merged.set(row.agent.id,{...row,assignments:[...row.assignments]});
      else merged.get(row.agent.id).assignments.push(...row.assignments);
    }
    return [...merged.values()];
  },
  mode(task,language='zh') {
    const en=language==='en';
    if(task?.mode_source!=='explicit')return en?'Unclassified':'未分类';
    const parts=[];if(task?.activity_kind==='project')parts.push(en?'Project':'项目');
    if(task?.collaboration_mode==='team')parts.push(en?'Team':'团队');else if(task?.collaboration_mode==='single')parts.push(en?'Single':'单人');
    return parts.join(' · ');
  },
  matchesMode(task,filter) {
    return filter==='all'||task?.mode_source==='explicit'&&(filter==='project'?task.activity_kind==='project':task.collaboration_mode===filter);
  },
  automationSource(state,taskId) {
    const relation=(state.automation_bindings||[]).find(b=>b.task_id===taskId&&b.verified===true&&b.automation_id);
    return relation?String(relation.name||relation.automation_id):null;
  },
  actor(row,state,language='zh') {
    const a=row.attribution;
    if(!a?.agent_id)return {known:false,label:row.role==='system'||row.kind==='requirement'?(language==='en'?'System record':'系统记录'):(language==='en'?'Historical author unknown':'历史作者未知'),role:language==='en'?'Role unrecorded':'职责未记录',color:'#f3f4ef',agent:null,id:'unattributed'};
    const key=/^[a-f0-9]{8}$/i.test(a.color_key||'')?a.color_key:'00000000';
    const agent={id:a.agent_id,name:a.actor_name||'',name_en:a.actor_name_en||'',portrait:a.portrait||'',portrait_spec:a.portrait_spec,panel_short_id:a.actor_short_id||(language==='en'?'ID unrecorded':'编号未记录')};
    return {known:true,label:(language==='en'&&a.actor_name_en)||a.actor_name||agent.panel_short_id,shortId:agent.panel_short_id,role:PanelAgents.type(a.work_type||'unspecified',language),color:this.palette[parseInt(key,16)%this.palette.length],agent,id:a.agent_id,assignmentId:a.assignment_id,workType:a.work_type||'unspecified'};
  },
  rows(state,taskId,filters={}) {
    const ids=this.scope(state,taskId,filters.includeChildren!==false);
    const rows=[...ids].flatMap(id=>PanelWorkspace.timeline(state,id));
    return this.filter(rows,filters).sort((a,b)=>(b.created||0)-(a.created||0)||a.key.localeCompare(b.key));
  },
  filter(rows,{agent='',role='',task=''}={}) {
    return rows.filter(row=>(!task||row.task_id===task)&&(!agent||(row.attribution?.agent_id||'unattributed')===agent)&&(!role||(row.attribution?.work_type||'unattributed')===role));
  },
  choices(state,taskId) {
    const ids=this.scope(state,taskId),agents=new Map(),roles=new Set();
    for(const episode of state.assignment_episodes||[])if(ids.has(episode.task_id)){const agent=(state.agents||[]).find(a=>a.id===episode.agent_id);if(agent)agents.set(agent.id,agent);roles.add(episode.work_type);}
    for(const id of ids)for(const row of PanelWorkspace.timeline(state,id)){const a=row.attribution;if(a?.agent_id){agents.set(a.agent_id,{id:a.agent_id,name:a.actor_name,name_en:a.actor_name_en,portrait:a.portrait,panel_short_id:(state.agents||[]).find(p=>p.id===a.agent_id)?.panel_short_id||a.color_key});roles.add(a.work_type);}}
    return {agents:[...agents.values()].sort((a,b)=>a.id.localeCompare(b.id)),roles:[...roles].filter(Boolean).sort(),tasks:(state.tasks||[]).filter(t=>ids.has(t.id))};
  }
};


// Keyed local DOM reconciliation. No HTML parsing, synthetic identity or polling side effects.
globalThis.PanelPatch = {
  listen(node,type,callback,options) {
    const capture=typeof options==='boolean'?options:Boolean(options?.capture),key=type+':'+capture;
    if(!node.__panelActions)node.__panelActions=new Map();
    const existing=node.__panelActions.get(key);
    if(existing){existing.callback=callback;return;}
    const record={type,callback,options,wrapped:event=>{const current=node.__panelActions?.get(key);if(current)current.callback.call(node,event,node);}};
    node.__panelActions.set(key,record);node.addEventListener(type,record.wrapped,options);
  },
  actions(target,next) {
    if(next.__panelPreserveActions)return;
    const wanted=next.__panelActions||new Map();
    for(const [key,record] of target.__panelActions||[])if(!wanted.has(key)){
      target.removeEventListener(record.type,record.wrapped,record.options);target.__panelActions.delete(key);
    }
    for(const record of wanted.values())this.listen(target,record.type,record.callback,record.options);
  },
  key(node) {return node?.dataset?.timelineKey||node?.dataset?.patchKey||node?.id||node?.dataset?.focusKey||node?.dataset?.disclosureKey||null;},
  sync(target,next) {
    if(target.nodeType===3&&next.nodeType===3){if(target.nodeValue!==next.nodeValue)target.nodeValue=next.nodeValue;return target;}
    if(target.nodeType!==next.nodeType||target.nodeName!==next.nodeName){target.replaceWith(next);return next;}
    this.actions(target,next);
    const focused=target.ownerDocument?.activeElement===target;
    for(const attr of [...(next.attributes||[])])if(attr.name!=='open'&&target.getAttribute(attr.name)!==attr.value)target.setAttribute(attr.name,attr.value);
    for(const attr of [...(target.attributes||[])])if(attr.name!=='open'&&!next.hasAttribute(attr.name))target.removeAttribute(attr.name);
    if(!focused&&['INPUT','SELECT','TEXTAREA','PROGRESS'].includes(target.nodeName)&&target.value!==next.value)target.value=next.value;
    if('disabled' in next&&target.disabled!==next.disabled)target.disabled=next.disabled;
    if('hidden' in next&&target.hidden!==next.hidden)target.hidden=next.hidden;
    if(!next.childNodes.length&&target.textContent!==next.textContent)target.textContent=next.textContent;
    this.children(target,[...next.childNodes]);return target;
  },
  children(parent,incoming) {
    const old=[...parent.childNodes],keyed=new Map(old.map(n=>[this.key(n),n]).filter(([k])=>k)),used=new Set();
    let cursor=parent.firstChild;
    for(const fresh of incoming){
      const key=this.key(fresh);let current=key?keyed.get(key):old.find(n=>!used.has(n)&&!this.key(n)&&n.nodeType===fresh.nodeType&&n.nodeName===fresh.nodeName);
      if(current){used.add(current);current=this.sync(current,fresh);}else current=fresh;
      if(current!==cursor)parent.insertBefore(current,cursor||null);
      cursor=current.nextSibling;
    }
    for(const node of old)if(!used.has(node)&&node.parentNode===parent)node.remove();
  }
};
