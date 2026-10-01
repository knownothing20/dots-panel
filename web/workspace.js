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
    for(const row of this.rows(state.tasks||[],state.latest_runs||state.runs||[])){
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
    const links=new Map((state.agent_assignments||[]).filter(a=>a.agent_id===agent.id).map(a=>[a.task_id,a]));
    const result={current:[],unfinished:[],recent:[]};
    for(const row of PanelWorkspace.rows(state.tasks||[],state.runs||[])){
      const link=links.get(row.task.id);if(!link)continue;
      const entry={task:row.task,status:row.status,work_type:link.work_type||'unspecified'};
      if(['pending','running','waiting_user','waiting_external','paused','awaiting_review'].includes(row.status)){
        result.unfinished.push(entry);
        if(agent.status==='running'&&row.status==='running')result.current.push(entry);
      }else result.recent.push(entry);
    }
    return result;
  }
};
