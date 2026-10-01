'use strict';
const $ = id => document.getElementById(id);
let preference = 'auto';
try { preference = localStorage.getItem('dots-panel-language') || 'auto'; } catch (_) {}
if (!['auto','zh','en'].includes(preference)) preference = 'auto';
let timezone = 'Asia/Shanghai', settingsError = '';
function validateTimezone(value) {
  if(typeof value!=='string'||!value||value.length>128)throw new RangeError('Invalid IANA timezone');
  new Intl.DateTimeFormat('en-US',{timeZone:value}).format(0);
  return value;
}
try { const saved=localStorage.getItem('dots-panel-timezone'); if(saved)timezone=validateTimezone(saved); }
catch (_) { settingsError='read'; }
let language = PanelLocale.resolve(preference,navigator.language);
const t = value => PanelLocale.translate(value,language);
const phrase = (zh,en) => language === 'zh' ? zh : en;
const staticText = [];
const walker = document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
while (walker.nextNode()) { const node = walker.currentNode; if(node.textContent.trim()) staticText.push([node,node.textContent]); }
function translatePage() {
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  document.title = phrase('dots panel · 本地工作台','dots panel · Local workspace');
  for (const [node,original] of staticText) { const core=original.trim(); node.textContent=original.replace(core,t(core)); }
  $('language').value = preference;
  $('detail-scroll').setAttribute('aria-label',phrase('活动详情','Activity details'));
  $('back-conversations').setAttribute('aria-label',phrase('返回活动列表','Back to activities')); 
  $('workspace-search').placeholder=t('搜索任务…');
  $('workspace-search').setAttribute('aria-label',t('搜索任务…'));
  $('toggle-events').textContent=phrase($('toggle-events').getAttribute('aria-expanded')==='true'?'收起原始运行记录':'展开原始运行记录',$('toggle-events').getAttribute('aria-expanded')==='true'?'Hide raw run records':'Show raw run records');
}
const bytes = n => n == null ? t('未知') : n >= 2**30 ? `${(n/2**30).toFixed(1)} GB` : `${(n/2**20).toFixed(0)} MB`;
const stamp = n => {
  if(n==null)return '—';
  if(typeof n==='string'&&!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(n))return n+' [timezone unknown]';
  const date=typeof n==='number'?new Date(n*1000):new Date(n);
  if(!Number.isFinite(date.getTime()))return String(n);
  return new Intl.DateTimeFormat(language==='zh'?'zh-CN':'en-GB',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZoneName:'longOffset'}).format(date)+' · '+timezone;
};
function updateSettings() {
  $('timezone').value=timezone;
  $('timezone-preview').textContent=stamp(Date.now()/1000);
  $('settings-error').textContent=settingsError==='invalid'?phrase('无效或不支持的 IANA 时区','Invalid or unsupported IANA timezone'):settingsError==='save'?phrase('偏好未保存；当前仅本次有效','Preferences not saved; applied for this session only'):settingsError==='read'?phrase('无法读取已保存时区；当前显示北京时间，原设置未被改写','Could not read saved timezone; displaying Beijing time without overwriting saved settings'):'';
}
function renderPreferences() {
  const scroll=window.scrollY, detail=$('detail-scroll').scrollTop;
  translatePage();if(lastState)render(lastState);updateSettings();
  $('detail-scroll').scrollTop=detail;
  window.scrollTo(0,scroll);
}
const statuses = {waiting_user:'等待用户',waiting_external:'等待外部结果',paused:'已暂停记录',awaiting_review:'等待验收',pending:'待开始',running:'运行中', succeeded:'已完成', failed:'失败', cancelled:'已取消'};
let busy = false;
let workspaceFilter = 'all';
let adviceTaskId=null;
let detailTab='timeline';
const detailScrollPositions={timeline:0,files:0};
const expandedRules=new Set(), expandedDiagnostics=new Set(), expandedSteps=new Set();
let renderedTaskId=null;
const expandedSchedules=new Set(), expandedSoftware=new Set(), expandedSkills=new Set();
let workspaceQuery = '';
let lastState = null;
const panelNotifications=typeof PanelNotifications!=='undefined'?new PanelNotifications.Controller({document,language:()=>language,avatar:agentAvatar,openTask:(id,{keyboard=false}={})=>{const task=lastState?.tasks?.find(item=>item.id===id);if(task){selectTask(task);if(keyboard)$('detail-scroll').focus({preventScroll:true});}}}):null;
function element(tag, text, className) { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; }
// Preserve open evidence, focused disclosure and the visible timeline item during polling.
function disclosure(node,store,key) {
  node.setAttribute('data-disclosure-key',key);node.open=store.has(key);
  node.addEventListener('toggle',()=>{if(node.open)store.add(key);else store.delete(key);});
  return node;
}
function captureView(selected) {
  const scroll=$('detail-scroll'),sameTask=renderedTaskId===selected;
  const position={page:window.scrollY||0,detail:sameTask?(scroll.scrollTop||0):0,sameTask,focus:document.activeElement?.dataset?.focusKey||null,scope:document.activeElement?.closest?.('[data-page]')?.dataset.page||null};
  const active=document.activeElement;
  if(active?.tagName==='SUMMARY')position.disclosure=active.parentElement?.dataset?.disclosureKey;
  if(sameTask&&position.detail>0&&scroll.getBoundingClientRect){
    const top=scroll.getBoundingClientRect().top;
    const anchor=[...scroll.querySelectorAll('[data-timeline-key]')].find(node=>node.getBoundingClientRect().bottom>top);
    if(anchor)position.anchor={key:anchor.dataset.timelineKey,offset:anchor.getBoundingClientRect().top-top};
  }
  return position;
}
function restoreView(position,selected) {
  const scroll=$('detail-scroll');scroll.scrollTop=position.detail;
  if(position.anchor&&scroll.querySelectorAll){
    const anchor=[...scroll.querySelectorAll('[data-timeline-key]')].find(node=>node.dataset.timelineKey===position.anchor.key);
    if(anchor)scroll.scrollTop+=anchor.getBoundingClientRect().top-scroll.getBoundingClientRect().top-position.anchor.offset;
  }
  if(position.disclosure){const details=[...document.querySelectorAll('details[data-disclosure-key]')].find(node=>node.dataset.disclosureKey===position.disclosure&&(!position.scope||node.closest?.('[data-page]')?.dataset.page===position.scope));details?.querySelector('summary')?.focus({preventScroll:true});}
  if(position.focus){const control=[...document.querySelectorAll('[data-focus-key]')].find(node=>node.dataset.focusKey===position.focus&&(!position.scope||node.closest?.('[data-page]')?.dataset.page===position.scope));control?.focus({preventScroll:true});}
  // Instant restoration avoids smooth-scroll drift after repeated background refreshes.
  if(window.scrollTo&&window.scrollY!==position.page)window.scrollTo({top:position.page,left:0,behavior:'instant'});
  renderedTaskId=selected;
}
// Keep controls mounted across polling so keyboard focus and native select menus survive.
function renderStatusFilters(state) {
  const tasks=state.tasks, runs=state.current_runs||state.latest_runs||state.runs;
  const main=[['all',t('全部')],['unfinished',phrase('未完成','Unfinished')],['succeeded',phrase('已完成','Completed')]];
  for (const id of ['workspace-tabs','activity-tabs']) {
    const bar=$(id);
    bar.setAttribute('aria-label',phrase('任务状态','Task status'));
    if (!bar.children.length) {
      for (const [value] of main) {
        const button=element('button','','filter-chip');button.type='button';button.dataset.filter=value;
        button.addEventListener('click',()=>{workspaceFilter=value;render(lastState);});bar.append(button);
      }
      const select=element('select','','more-status-filter');
      for (const value of ['more',...Object.keys(statuses)]) {const option=element('option','');option.value=value;select.append(option);}
      select.options[0].disabled=true;
      select.addEventListener('change',()=>{workspaceFilter=select.value;render(lastState);});
      select.addEventListener('blur',()=>{if(lastState)renderStatusFilters(lastState);});
      bar.append(select);
    }
    for (const [index,[value,label]] of main.entries()) {
      const button=bar.children[index];button.textContent=label+' '+PanelWorkspace.rows(tasks,runs,value).length;
      button.classList.toggle('selected',workspaceFilter===value);button.setAttribute('aria-pressed',String(workspaceFilter===value));
    }
    const select=bar.lastElementChild, exact=!main.some(([value])=>value===workspaceFilter,'',state);
    select.setAttribute('aria-label',phrase('更多状态筛选','More status filters'));
    select.classList.toggle('selected',exact);
    // Don't rebuild an open platform-native options list during background refresh.
    if(document.activeElement!==select) {
      for(const option of select.options) option.textContent=option.value==='more'?phrase('更多筛选','More filters'):t(statuses[option.value])+' '+PanelWorkspace.rows(tasks,runs,option.value).length;
    }
    if(select.value!==(exact?workspaceFilter:'more'))select.value=exact?workspaceFilter:'more';
    select.title=exact?t(statuses[workspaceFilter]):phrase('更多筛选','More filters');
  }
}
function showPage() {
  const requested=location.hash.slice(1);
  const page=['overview','conversations','schedules','software','rules','about','settings'].includes(requested)?requested:'overview';
  for(const node of document.querySelectorAll('[data-page]'))node.hidden=node.dataset.page!==page;
  for(const node of document.querySelectorAll('[data-nav]')){node.classList.toggle('active',node.dataset.nav===page);if(node.dataset.nav===page)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');}
  panelNotifications?.markRead(page,page==='conversations'?$('task-filter').value||null:null);
}
function staleLabel(run){return t(run.tracking_mode==='heartbeat'?'心跳过期 · 状态待确认':'进度更新较久，执行状态待确认');}
function registryCard(title, description, icon='▦') {
  const card=element('article','','registry-card');card.append(element('span',icon,'card-icon'),element('h2',title),element('p',description));return card;
}
// A fetched result is evidence of an observation, never of platform scheduling.
function schedulePlatformView(item) {
  const p=item.platform_observation;if(!p)return null;
  const unknown=phrase('未知','Unknown'), enabled=p.enabled===true?phrase('已启用','Enabled'):p.enabled===false?phrase('已停用','Disabled'):unknown;
  const rule=String(p.schedule||'').split(/\r?\n/).find(line=>line.startsWith('RRULE:'))||'';
  const parts=Object.fromEntries(rule.slice(6).split(';').filter(p=>p.includes('=')).map(p=>p.split('=')));
  let compact=phrase('已记录计划；展开查看','Recorded schedule; expand for details');
  const simple=!Object.keys(parts).some(key=>!['FREQ','INTERVAL','BYHOUR','BYMINUTE','BYSECOND'].includes(key))&&!String(p.schedule||'').split(/\r?\n/).some(line=>/^(?:EXDATE|RDATE|EXRULE)/.test(line));
  const hour=/^\d{1,2}$/.test(parts.BYHOUR||'')&&Number(parts.BYHOUR)<24,minute=/^\d{1,2}$/.test(parts.BYMINUTE||'0')&&Number(parts.BYMINUTE||0)<60;
  if(simple&&parts.FREQ==='HOURLY'&&(!parts.INTERVAL||parts.INTERVAL==='1')&&!parts.BYHOUR&&minute)compact=phrase('每小时','Every hour')+(parts.BYMINUTE?phrase(' · 第 ',' · minute ')+parts.BYMINUTE.padStart(2,'0')+phrase(' 分',''):'');
  else if(simple&&parts.FREQ==='DAILY'&&(!parts.INTERVAL||parts.INTERVAL==='1')&&hour&&minute)compact=phrase('每天 ','Daily ')+parts.BYHOUR.padStart(2,'0')+':'+(parts.BYMINUTE||'0').padStart(2,'0');
  return {label:phrase('平台观察 · ','Platform observed · ')+enabled,compact:compact+' · '+(p.timezone||unknown),rows:[
    [phrase('平台','Platform'),p.platform||unknown],[phrase('平台任务 ID','Platform task ID'),p.task_id||unknown],[phrase('已观察启用状态','Observed enabled state'),enabled],[phrase('调度时区','Schedule timezone'),p.timezone||unknown],[phrase('计划','Schedule'),p.schedule||unknown],[phrase('定时方式','Timing mode'),p.timing_mode||unknown],[phrase('上次运行','Last run'),p.last_run_at?stamp(p.last_run_at):unknown],[phrase('下次运行','Next run'),p.next_run_at?stamp(p.next_run_at):unknown],[phrase('平台观察时间','Platform observed at'),stamp(p.observed_at)],[phrase('首次定时执行','First scheduled execution'),phrase('尚未核验','Not yet verified')]]};
}
function scheduleResultView(item) {
  const result=item.external_result;
  if(!result)return null;
  const observation=result.observation, latest=observation?.latest||{}, index=observation?.index||{}, evidence=observation?.evidence||{};
  const unknown=phrase('未知','Unknown'), value=n=>n==null||n===''?unknown:String(n);
  const checked=n=>typeof n==='number'&&Number.isFinite(n)?stamp(n):phrase('尚无记录','Not recorded');
  const stale=latest.stale===true?phrase('是','Yes'):latest.stale===false?phrase('否','No'):unknown;
  const label=item.platform_observation?(observation?phrase('结果已接入 · 平台配置已观察','Results linked · platform config observed'):phrase('暂无结果快照 · 平台配置已观察','No result snapshot · platform config observed')):(observation?phrase('结果已接入 · 配置未核验','Results linked · config unverified'):phrase('暂无结果快照 · 配置未核验','No result snapshot · config unverified'));
  const compact=observation?[
    `${phrase('最近观察尝试','Latest observed attempt')}: ${value(latest.calendar_date)} · ${value(latest.status)} · ${phrase('入选数','Selected')}: ${value(latest.selected_count)}`,
    `${phrase('源过期标记','Source stale flag')}: ${stale} · ${phrase('已接受索引最新日期','Accepted index latest date')}: ${value(index.latest_date)}`,
  ]:[phrase('尚无可用的外部结果快照','No usable external result snapshot')];
  const error=result.fetch_error?`${phrase('获取失败','Fetch failed')}: ${result.fetch_error} · ${observation?phrase('保留上次成功快照','Retaining last good snapshot'):phrase('尚无成功快照','No successful snapshot')}`:'';
  const rows=[
    [phrase('平台配置','Platform configuration'),phrase('未核验；平台 ID、启用状态、下次执行时间均未知','Unverified; platform ID, enabled state and next due are unknown')],
    [phrase('同步方式','Sync mode'),phrase('手动结果快照；非实时连接','Manual result snapshot; not a live connection')],
    [phrase('最近获取检查','Last fetch check'),checked(result.checked_at)],
    [phrase('最近成功获取','Last successful fetch'),checked(result.last_good_at)],
  ];
  if(observation)rows.push(
    [phrase('最近观察尝试日期','Latest observed attempt date'),value(latest.calendar_date)],
    [phrase('源运行编号','Source run ID'),value(latest.run_id)],
    [phrase('源采集时间','Source collected at'),stamp(latest.collected_at)],
    [phrase('源结果状态','Source result status'),value(latest.status)],
    [phrase('入选数','Selected count'),value(latest.selected_count)],
    [phrase('源过期标记','Source stale flag'),stale],
    [phrase('已接受索引最新日期','Accepted index latest date'),value(index.latest_date)],
    [phrase('索引生成时间','Index generated at'),stamp(index.generated_at)],
    [phrase('索引条目数','Index entry count'),value(index.entry_count)],
  );
  if(item.platform_observation)rows[0]=[phrase('平台配置','Platform configuration'),phrase('有人工观察快照；不代表实时状态或首次定时运行成功','Manual snapshot available; not live status or proof of first scheduled execution')];
  rows.push([phrase('结果仓库','Result repository'),value(result.repository)], [phrase('来源版本','Source ref'),value(result.ref)],
    [phrase('状态文件','Status path'),value(result.status_path)], [phrase('索引文件','Index path'),value(result.index_path)]);
  if(observation)rows.push(['Status blob SHA',value(evidence.status_sha)],['Index blob SHA',value(evidence.index_sha)],
    [phrase('状态来源 URL','Status source URL'),value(evidence.status_url)], [phrase('索引来源 URL','Index source URL'),value(evidence.index_url)]);
  return {label,compact,error,rows};
}
function renderSchedules(schedules) {
  const states={disconnected:'未接入',planned:'仅计划',paused:'暂停记录'};
  $('schedule-summary').replaceChildren();
  if(!schedules.length)$('schedule-summary').append(element('p',t('还没有登记的计划'),'empty-caption'));
  for(const item of schedules.slice(0,3)){
    const platform=schedulePlatformView(item),result=scheduleResultView(item), row=element('a','','schedule-row');row.href='#schedules';row.append(element('span','◷','small-icon'));
    const title=element('div','');title.append(element('strong',item.name),element('small',platform?.label||result?.label||t(states[item.state]||item.state)));
    if(platform)title.append(element('small',platform.compact));
    if(result)title.append(element('small',result.error||result.compact[0]));
    row.append(title,element('span','›','row-chevron'));$('schedule-summary').append(row);
  }
  const boundary=phrase('平台配置为人工观察快照；结果快照不证明定时器已启用或首次执行成功','Platform configuration is a manual observation; result snapshots do not prove schedules are enabled or their first execution succeeded');
  $('schedule-summary').append(element('p',boundary,'empty-caption'));
  $('schedule-cards').replaceChildren();
  if(!schedules.length)$('schedule-cards').append(registryCard(t('还没有登记的计划'),t('使用本地 CLI 登记元数据，不会自动创建定时器。')));
  for(const item of schedules){
    const platform=schedulePlatformView(item),result=scheduleResultView(item), card=element('article','','registry-card schedule-card');
    const head=element('div','','registry-heading');
    const title=element('h2',item.name);title.style.margin='0';title.style.overflowWrap='anywhere';
    const badge=element('span',platform?.label||result?.label||t(states[item.state]||item.state),'status');badge.style.whiteSpace='normal';head.append(title,badge);card.append(head);
    if(platform){card.append(element('p',platform.compact,'schedule-cadence'));if(item.platform_observation.next_run_at)card.append(element('p',`${phrase('下次运行（观察）','Next run (observed)')}: ${stamp(item.platform_observation.next_run_at)}`,'schedule-next'));}
    if(item.project){const project=element('small',item.project);project.style.overflowWrap='anywhere';card.append(project);}
    if(result){
      for(const line of result.compact){const summary=element('p',line);summary.style.margin='4px 0';summary.style.overflowWrap='anywhere';card.append(summary);}
      if(result.error){const warning=element('p',result.error,'freshness-warning');warning.style.overflowWrap='anywhere';card.append(warning);}
    }
    const details=element('details','','registry-details');details.dataset.disclosureKey='schedule:'+item.id;details.open=expandedSchedules.has(item.id);details.append(element('summary',phrase('详情','Details')));
    details.addEventListener('toggle',()=>{if(details.open)expandedSchedules.add(item.id);else expandedSchedules.delete(item.id);});
    const rows=[...(platform?.rows||[]),...(result?.rows||[])];
    for(const [label,value] of rows){const line=element('p',`${label}: ${value}`);line.style.overflowWrap='anywhere';if(label===phrase('计划','Schedule')||label===phrase('平台任务 ID','Platform task ID'))line.className='technical-record';details.append(line);}
    details.append(element('p',`${t('来源')} · ${item.source}`),
      element('p',`${phrase('登记状态（元数据）','Registered state (metadata)')}: ${t(states[item.state]||item.state)}`),
      element('p',`${phrase('登记计划时间（未核验）','Registered planned time (unverified)')}: ${item.next_run==null?t('未知'):stamp(item.next_run)}`),
      element('small',`${t('最近更新')} ${stamp(item.updated)}`),element('p',phrase('登记不会创建、启动或恢复任何定时器','Registration does not create, start or resume a scheduler')));
    card.append(details);$('schedule-cards').append(card);
  }
  const note=element('p',phrase('每 5 秒只刷新本地数据，不轮询 GitHub；外部结果须手动同步','Every 5 seconds refreshes local data only, without polling GitHub; external results require manual sync'),'empty-caption');note.style.gridColumn='1 / -1';$('schedule-cards').append(note);
}
function selectTask(task,advice=false) {if($('task-filter').value!==task.id){setDetailTab('timeline');detailScrollPositions.timeline=0;detailScrollPositions.files=0;$('detail-scroll').scrollTop=0;}adviceTaskId=advice?task.id:null;$('task-filter').value=task.id;render(lastState);location.hash='conversations';showPage();if(advice)$('advice-text').focus();}
function outputSummary(state,taskId){return state.output_summaries?.[taskId]||{count:0,kinds:[],main:null};}
function outputCountText(summary){
  if(!summary.count)return phrase('尚无已登记成果','No registered outputs');
  const names={report:['报告','reports'],image:['图片','images'],document:['文档','documents'],data:['数据','data'],video:['视频','videos'],other:['其他','other']};
  const kinds=(summary.kinds||[]).map(row=>language==='en'?`${row.count} ${(names[row.kind]||names.other)[1]}`:`${(names[row.kind]||names.other)[0]} ${row.count}`).join(' · ');
  return phrase('成果','Outputs')+' '+summary.count+(kinds?' · '+kinds:'');
}
function outputMainText(summary){
  const main=summary.main;if(!main)return '';
  const labels={final:['最终稿','Final'],draft:['草稿','Draft'],unclassified:['未指定版本','Unclassified']};
  const status=[phrase('已归档','Archived'),(labels[main.designation]||labels.unclassified)[language==='en'?1:0]];
  for(const [key,zh,en] of [['sent','已记录发送','Sent recorded'],['opened','已记录打开','Opened recorded'],['accepted','已记录验收','Acceptance recorded']])if((main.delivery||[]).includes(key))status.push(phrase(zh,en));
  return (main.designation==='final'?phrase('最近最终稿：','Latest final: '):phrase('最近登记：','Recently registered: '))+(main.title||main.filename||'')+' · '+status.join(' · ');
}
function openTaskFiles(task){
  if(!task)return;
  selectTask(task);setDetailTab('files');$('tab-files').focus();
}
function renderOutputBar(state,taskId){
  const summary=outputSummary(state,taskId);
  $('output-summary-count').textContent=outputCountText(summary);
  $('output-summary-main').textContent=outputMainText(summary);
  $('output-summary-main').title=summary.main?.filename||'';
  $('output-summary-files').textContent=phrase('查看文件','View files');
  $('output-summary-note').textContent=phrase('仅显示已登记文件；归档不等于发送或验收。打开文件夹请使用云桌面原生面板。','Registered files only; archiving is not delivery or acceptance. Open folders in the native cloud desktop panel.');
}
function taskCard(task,run,state) {
  const work=PanelWorkspace.workProgress(state,task.id,run);run=work.current_run||run;
  const status=run?.status||task.latest_status||'pending';
  const card=element('article','','task-card '+status);card.title=t('选择此活动，查看阶段与记录');
  const top=element('div','','task-card-top');top.append(element('span','▣','card-icon'));const people=avatarGroup(task,state),badge=element('span',t(statuses[status]||status),'status '+status);top.append(people,badge);
  card.append(top,element('h2',task.name),element('p',task.project,'task-project'),ownerBadge(task.id,state));
  const summaryText=run?.lifecycle_reason||work.current_step||phrase('尚无工作进展摘要','No work progress recorded');
  card.append(element('small',run?.lifecycle_reason?phrase('状态原因','Status reason'):work.scope==='task'?phrase('任务最新摘要','Latest task update'):phrase('最近登记步骤','Latest recorded step'),'task-step-label'),element('p',summaryText,'task-summary'));
  const nextStep=run?.next_step||work.update?.next_step;
  if(nextStep)card.append(element('p',phrase('下一步：','Next: ')+nextStep,'task-next'));
  const progress=element('div','','task-progress');
  if(work.counts){const count=work.counts;const measure=element('progress','');measure.max=count.total;measure.value=count.completed;measure.setAttribute('aria-label',phrase('已登记实际进度','Recorded measured progress'));progress.append(measure,element('small',`${count.completed} / ${count.total} ${count.unit}`));}
  else if(work.total)progress.append(element('small',phrase(`已验证 ${work.verified} / ${work.total} 个已记录阶段`,`${work.verified} / ${work.total} recorded stages verified`)));
  if(work.steps.length){
    const steps=disclosure(element('details','','task-steps'),expandedSteps,task.id);steps.append(element('summary',phrase(`步骤记录 · ${work.steps.length}`,`Recorded steps · ${work.steps.length}`)));
    steps.addEventListener('click',event=>event.stopPropagation());
    for(const step of work.steps.slice(0,4)){const line=element('div','','task-step');line.append(element('small',stamp(step.created)),element('p',step.message));steps.append(line);}
    if(work.update?.evidence)steps.append(element('small',phrase('依据：','Evidence: ')+work.update.evidence));
    if(work.steps.length>4)steps.append(element('small',phrase('其余记录见活动详情','More records in activity details')));
    progress.append(steps);
  }else progress.append(element('small',t('尚无阶段记录')));
  card.append(progress);
  if(work.unpaused_runs.length>1){
    const parallel=disclosure(element('details','','task-steps'),expandedSteps,'parallel:'+task.id);parallel.append(element('summary',phrase(`未完成运行 · ${work.unpaused_runs.length}`,`Unfinished runs · ${work.unpaused_runs.length}`)));
    parallel.addEventListener('click',event=>event.stopPropagation());
    for(const entry of work.unpaused_runs){const line=element('div','','task-step');line.append(element('small',`${t(statuses[entry.status]||entry.status)} · ${stamp(entry.started)}${entry.id===work.current_run_id?phrase(' · 当前展示',' · Shown above'):''}`),element('p',entry.note||phrase('未登记开始说明','No start note recorded')),element('small',`${phrase('运行','Run')} ${entry.id} · ${PanelAgents.runNames(state,entry.id,language)||t('未分配')}`));parallel.append(line);}
    card.append(parallel);
  }
  const bottom=element('div','','task-card-footer');bottom.append(element('span',`${phrase('进展记录','Progress recorded')} ${stamp(work.update?.created??work.latest?.created??null)}`));card.append(bottom);
  if(run?.stale)card.append(element('small',staleLabel(run),'freshness-warning'));
  const summary=outputSummary(state,task.id),outputs=element('div','','task-outputs');
  outputs.append(element('strong',outputCountText(summary),'output-count'),...(summary.main?[element('span',outputMainText(summary),'output-main')]:[]));
  outputs.title=summary.main?.filename||'';card.append(outputs);
  const actions=element('div','','task-card-actions');
  const details=element('button',phrase('查看详情','View details'),'filter-chip');details.type='button';details.dataset.focusKey='task-details:'+task.id;details.setAttribute('aria-label',phrase('查看活动详情：','View task details: ')+task.name);details.addEventListener('click',event=>{event.stopPropagation();selectTask(task);});actions.append(details);
  if(summary.count){const files=element('button',phrase('查看文件','View files'),'filter-chip');files.type='button';files.dataset.focusKey='task-files:'+task.id;files.setAttribute('aria-label',phrase('查看成果文件：','View output files: ')+task.name);files.addEventListener('click',event=>{event.stopPropagation();openTaskFiles(task);});actions.append(files);}
  card.append(actions);card.addEventListener('click',()=>selectTask(task));return card;
}
function renderRules(data={}){
  const area=$('rules-content');area.replaceChildren();
  const en=language==='en', locale=en?'en':'zh';
  const labels={enforced:en?'App enforced':'程序校验',workflow:en?'Workflow':'执行约定',planned:en?'Planned':'待落地'};
  area.append(element('p',(en?'Rules version · ':'规则版本 · ')+(data.version||'—')));
  area.append(element('p',en?'App enforced: checked by panel operations. Workflow: followed by the executor. Planned: not implemented. These guidelines do not grant permissions.':'程序校验：面板操作已实施检查；执行约定：由执行者遵循；待落地：尚未实现。规则本身不授予权限。','empty-caption'));
  area.append(element('h2',en?'Your installed Skills':'用户安装的 Skills'));
  area.append(element('p',en?'Manually recorded summaries · no automatic sync or guaranteed activation':'人工登记的用途摘要 · 不自动同步，不保证每次触发','empty-caption'));
  const skills=(data.skills||[]).filter(item=>item.scope==='user_installed');
  const safeSkillURL=url=>typeof url==='string'&&/^https:\/\/chatgpt\.com\/skills\?skill_id=[A-Za-z0-9_-]{1,100}$/.test(url)&&!/[\r\n]/.test(url);
  const skillText=(item,key)=>(en&&item[key+'_en'])||item[key]||'';
  const statuses={available:en?'Observed readable':'已观察可读取',unavailable:en?'Observed unreadable':'已观察不可读取',unknown:en?'Availability unverified':'可用性未核验'};
  const versions={unverified:en?'Version unverified':'版本未核验',saved_verified:en?'Saved content checked':'已核验保存内容'};
  const skillGrid=element('div','','skill-grid');area.append(skillGrid);
  for(const item of skills){
    const row=element('section','','skill-row'),head=element('div','','skill-heading');
    head.append(element('h3',skillText(item,'name')));
    if(safeSkillURL(item.url)){const link=element('a',en?'Manage ↗':'管理 ↗','binding-link');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';head.append(link);}
    row.append(head,element('p',skillText(item,'purpose')),element('p',(en?'When: ':'使用场景：')+skillText(item,'when_used'),'skill-caption'));
    const details=element('details','','registry-details');details.dataset.disclosureKey='skill:'+item.id;details.open=expandedSkills.has(item.id);details.append(element('summary',en?'Details':'详情'));
    details.addEventListener('toggle',()=>{if(details.open)expandedSkills.add(item.id);else expandedSkills.delete(item.id);});
    details.append(element('p',(en?'Manual observation · ':'人工观察 · ')+(statuses[item.status]||statuses.unknown)+' · '+stamp(item.observed_at)+' · '+(versions[item.version_status]||versions.unverified),'skill-caption'));
    if(skillText(item,'version_note'))details.append(element('p',skillText(item,'version_note'),'skill-caption'));
    // Reconstructed origin presentation over retained source metadata.
    const origin=item.source||{};
    const originLabels={unknown:['来源未标记','Origin unspecified'],project_bundled:['项目配套','Project bundled'],personal:['个人规则','Personal rules'],independent:['独立 Skill','Independent Skill']};
    const publicationLabels={unknown:['发布未核验','Publication unverified'],pending:['待发布','Pending publication'],published:['已核验发布','Publication checked'],not_applicable:['不随项目发布','Not bundled for publication']};
    details.append(element('p',(originLabels[origin.origin]||originLabels.unknown)[en?1:0]+' · '+(publicationLabels[origin.publication]||publicationLabels.unknown)[en?1:0],'skill-caption'));

    row.append(details);skillGrid.append(row);
  }
  if(!skills.length)area.append(element('p',en?'No user Skills registered':'尚未登记用户 Skills','empty-caption'));
  if(safeSkillURL(data.skill_url)&&!skills.some(item=>item.url===data.skill_url)){
    const link=element('a',en?'Task skill ↗':'任务 Skill ↗','binding-link');link.href=data.skill_url;link.target='_blank';link.rel='noopener noreferrer';area.append(link);
  }
  area.append(element('h2',en?'Project guidelines':'项目规范'));
  for(const group of data.groups||[]){
    const details=disclosure(element('details','','rule-group'),expandedRules,'rule:'+group.id),summary=element('summary',group.title?.[locale]||'');details.append(summary);
    for(const item of group.items||[]){details.append(element('h3',(labels[item.level]||labels.planned)+' · '+(item.title?.[locale]||'')),element('p',item.body?.[locale]||''));}area.append(details);
  }
  area.append(element('p',en?'Source: packaged project_rules.json · read-only':'统一来源：项目 project_rules.json · 只读展示','empty-caption'));
}

function renderAbout(about={}){
  renderDoctor(about.doctor);
  const release=about.release||{};
  const labels={unknown:'未核验',unpublished:'未发布',published:'已发布',matched:'已核验一致',different:'已核验不同',local_changes:'有本地更改'};
  $('about-rows').replaceChildren();
  const rows=[['当前安装版本',about.installed_version||t('未知')],['已发布版本',`${t(labels[release.release_status]||'未核验')}${release.release_tag?' · '+release.release_tag:''}`],['源码同步状态',t(labels[release.sync_status]||'未核验')],['已核验远端提交',release.remote_commit||'—'],['最近核验',release.checked_at?stamp(release.checked_at):t('尚未核验')]];
  for(const [label,value] of rows){const row=element('div','','about-row');row.append(element('span',t(label)),element('strong',value));$('about-rows').append(row);}
  $('about-repository').replaceChildren();
  const url=release.repo_url;
  if(typeof url==='string'&&/^https:\/\/github\.com\/[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\/?$/.test(url)){
    const link=element('a',t('GitHub 项目 ↗'),'binding-link');link.href=url;link.target='_blank';link.rel='noopener noreferrer';$('about-repository').append(link,element('small',url));
  }else $('about-repository').append(element('p',t('尚未登记已核验的 GitHub 项目'),'empty-caption'));
  $('about-notes').replaceChildren();for(const item of about.install_notes||[])$('about-notes').append(element('p','• '+(item[language]||'')));
}
function agentAvatar(agent) {
  const avatar=element('span','','agent-avatar fixed-portrait');
  avatar.setAttribute('aria-hidden','true');
  const spec=agent.portrait_spec;
  if(spec?.shapes?.length){
    const create=tag=>document.createElementNS?document.createElementNS('http://www.w3.org/2000/svg',tag):document.createElement(tag);
    const svg=create('svg');svg.setAttribute('viewBox','0 0 64 64');svg.setAttribute('focusable','false');
    const allowed=new Set(['x','y','width','height','rx','ry','cx','cy','fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','points']);
    for(const shape of spec.shapes.slice(0,32)){
      if(!['rect','ellipse','polyline','polygon'].includes(shape.tag))continue;
      const node=create(shape.tag);
      for(const [key,value] of Object.entries(shape.attrs||{}))if(allowed.has(key))node.setAttribute(key,String(value));
      svg.append(node);
    }
    avatar.append(svg);
  }else{
    // Read-only compatibility view for an older server; no initials tied to a task title.
    avatar.append(element('span','••','agent-eyes'),element('span','⌣','agent-mouth'));
  }
  return avatar;
}
function identityLabel(agent) {
  return ({observed:["人工核验对应关系 · 非永久会话","Manually matched · not a permanent session"],historical:["历史档案 · 当前执行者未核验","Historical profile · current executor unverified"],unknown:["面板档案 · 执行者对应未核验","Panel profile · executor match unverified"]}[agent.identity_verification]||["面板档案 · 执行者对应未核验","Panel profile · executor match unverified"])[language==='en'?1:0];
}
function identitySource(agent) {
  return ({manual:['人工核验','Manual verification'],historical:['历史留存','Historical records'],unknown:['来源未核验','Source unverified']}[agent.identity_source]||['来源未核验','Source unverified'])[language==='en'?1:0];
}
function taskOwner(taskId,state) { return PanelAgents.taskLead(state,taskId).agent; }
function avatarGroup(task,state) {
  const rows=PanelAgents.activityParticipants(state,task.id),group=element('button','','participant-avatar-group');group.type='button';group.hidden=!rows.length;
  group.setAttribute('aria-label',phrase(`查看全部 ${rows.length} 位活动参与者`,`View all ${rows.length} activity participants`));
  for(const row of rows.slice(0,3))group.append(agentAvatar(row.agent));
  if(rows.length>3)group.append(element('span','+'+(rows.length-3),'participant-overflow'));
  group.addEventListener('click',event=>{event.stopPropagation();selectTask(task);setDetailTab('timeline');$('task-participants').scrollIntoView?.({block:'start'});});return group;
}
function renderTaskParticipants(state,taskId) {
  const area=$('task-participants');area.replaceChildren();const rows=PanelAgents.activityParticipants(state,taskId);area.hidden=!rows.length;if(!rows.length)return;
  area.append(element('h3',phrase('活动参与者 · ','Activity participants · ')+rows.length));
  for(const {agent,assignments} of rows){
    const item=element('article','','activity-participant'),head=element('div','','agent-heading');head.append(agentAvatar(agent),element('strong',PanelAgents.reference(agent,language)));item.append(head);
    const roles=[...new Set(assignments.map(a=>PanelAgents.type(a.work_type,language)))];item.append(element('p',phrase('已登记职责 · ','Recorded roles · ')+roles.join(' / ')));
    const observed=PanelAgents.observation(agent,state),label=observed.recent?({running:['已观察运行','Observed running'],idle:['空闲','Idle'],blocked:['受阻','Blocked'],unavailable:['不可用','Unavailable']}[agent.status]||['状态未知','State unknown'])[language==='en'?1:0]:phrase('状态待核实','State unconfirmed');item.append(element('small',label+' · '+stamp(agent.observed_at)));
    const detail=element('details','','participant-details');detail.dataset.disclosureKey='participant:'+taskId+':'+agent.id;detail.append(element('summary',t('详情')),element('p',phrase('昵称 · ','Nickname · ')+PanelAgents.text(agent,'name',language)),element('p',identityLabel(agent)),element('p',identitySource(agent)+' · '+stamp(agent.identity_observed_at)),element('p',phrase('面板短编号由完整档案ID派生，不是平台 UUID；不使用短片段匹配。','Panel short IDs derive from full profile IDs, not platform UUIDs; short fragments are never used for matching.')));
    for(const assignment of assignments)detail.append(element('p',(assignment.run_id||phrase('负责人记录','Owner record'))+' · '+PanelAgents.type(assignment.work_type,language)));
    item.append(detail);area.append(item);
  }
}

function ownerBadge(taskId,state) {
  const lead=PanelAgents.taskLead(state,taskId),owner=lead.agent,row=element('div','','owner-badge');row.dataset.taskId=taskId;
  if(owner){
    const observation=PanelAgents.observation(owner,state);
    const states={running:['已观察运行','Observed running'],idle:['空闲','Idle'],blocked:['受阻','Blocked'],unavailable:['不可用','Unavailable'],unknown:['未知','Unknown']};
    const observed=(states[observation.status]||states.unknown)[language==='en'?1:0];
    const active=lead.active.some(agent=>agent.id===owner.id);
    const assigned=lead.assigned.some(agent=>agent.id===owner.id);
    const role=(state.agent_run_assignments||[]).find(a=>a.agent_id===owner.id&&a.run_id===lead.run_id)?.work_type;
    const caption=element('span',`${assigned?phrase('已分派参与者','Assigned participant'):t('负责人')} · ${PanelAgents.reference(owner,language)} · ${PanelAgents.type(role,language)}${lead.assigned.length>1?' +'+(lead.assigned.length-1):''}${assigned?' · '+phrase('运行 ','Run ')+lead.run_id:''}`);
    row.append(agentAvatar(owner),caption,element('small',`${phrase('人工观察','Manual observation')}: ${observed} · ${stamp(owner.observed_at)}${observation.known&&!observation.recent?phrase(' · 较早，当前待确认',' · Older; current state unconfirmed'):''}`));
    if(lead.assigned.length>1)row.append(element('small',phrase('本运行参与者：','Run participants: ')+PanelAgents.runNames(state,lead.run_id,language)));
    if(active)row.classList.add('observed-running');
  }else row.append(element('span',`${t('负责人')} · ${t('未分配')}`));
  return row;
}
function renderCloseout(run,state) {
  const pinned=$('closeout-pinned'),body=$('closeout-summary'),record=run?.closeout;
  pinned.replaceChildren();body.replaceChildren();pinned.hidden=!record;body.hidden=!record&&run?.status!=='succeeded';
  if(!record){if(run?.status==='succeeded')body.append(element('p',phrase('历史完成记录；未登记完成门槛依据','Legacy completion; no evidence gate record')));return;}
  pinned.append(element('strong',`${phrase('交付','Deliverables')}: ${record.summary}`),element('small',`${PanelWorkspace.verification(record.verification,language)} · ${phrase('限制','Limits')}: ${record.limits}`));
  body.append(element('h3',phrase('最终产出与验证','Final deliverables & verification')),element('p',`${record.completed_at?phrase('已通过完成门槛','Completion gate checked'):phrase('已登记；尚未通过完成门槛','Recorded; completion gate not yet checked')} · ${PanelWorkspace.verification(record.verification,language)}`));
  for(const [key,zh,en] of [['summary','交付摘要','Summary'],['scope','检查范围','Scope'],['evidence','验证依据','Evidence'],['limits','剩余限制 / 未测部分','Limits / untested areas'],['no_artifact_reason','无文件产出的理由','No-artifact reason']])if(record[key])body.append(element('p',`${phrase(zh,en)}: ${record[key]}`));
  for(const item of record.artifacts||[]){const artifact=(state.artifacts||[]).find(file=>file.id===item.artifact_id);if(artifact)body.append(element('p',`${artifact.title} · ${PanelWorkspace.delivery(artifact,language)}`));}
  const files=element('button',phrase('查看文件','View files'),'filter-chip');files.type='button';files.addEventListener('click',()=>setDetailTab('files'));body.append(files);
}

function renderAdvice(task,run) {
  const visible=task&&task.id===adviceTaskId&&['waiting_user','awaiting_review','paused'].includes(run?.status);
  $('attention-advice').hidden=!visible;
  $('advice-title').textContent=phrase('处理建议','Suggested reply');
  $('advice-note').textContent=phrase('填写决定后可复制到聊天；此处没有发送任何消息','Copy into chat after filling in your decision; nothing has been sent');
  $('advice-text').setAttribute('aria-label',phrase('可复制的处理建议','Copyable suggested reply'));
  const draft=visible?PanelWorkspace.draft(task,run,language):'';
  if($('advice-text').value!==draft)$('advice-text').value=draft;
}

function renderDoctor(report={}){
  const area=$('about-doctor'),en=language==='en';
  const names={source_readable:['源码可读','Source readable'],source_writable:['源码可写','Source writable'],data_separate:['源码/数据分离','Source/data separate'],data_readable:['数据可读','Data readable'],data_writable:['数据可写','Data writable'],data_private:['数据私有权限','Private data permissions'],schema:['数据库结构','Database schema'],bundled_skill:['随附任务 Skill','Bundled task Skill'],account_task_skill:['账户任务 Skill','Account task Skill'],account_personal_skill:['账户个人规则 Skill','Account personal rules Skill'],scheduler_configuration:['定时器配置','Scheduler configuration'],scheduler_execution:['定时器执行验证','Scheduler execution verification']};
  const statuses={ok:['通过','OK'],read_only:['只读','Read-only'],missing:['缺失','Missing'],unsafe:['需核对安全边界','Safety review needed'],unavailable:['不可用','Unavailable'],migration_required:['需显式升级','Migration required'],verified:['人工核验','Manually verified'],failed:['核验失败','Check failed'],unknown:['未核验','Unverified']};
  const label=key=>(names[key]||[key,key])[en?1:0],status=value=>(statuses[value]||statuses.unknown)[en?1:0];
  area.replaceChildren(element('h3',phrase('安装自检 · 只读','Installation checks · read-only')));
  const checks=report.checks||[],passed=checks.filter(row=>row.status==='ok').length;
  area.append(element('p',checks.length?phrase(`本机检查：${passed}/${checks.length} 通过 · 仅探测权限`,`Local checks: ${passed}/${checks.length} OK · permission probes only`):phrase('尚未运行检查','No diagnostics available')));
  for(const component of ['account_task_skill','account_personal_skill','scheduler_configuration','scheduler_execution'])area.append(element('p',`${label(component)} · ${status(report.observations?.[component]?.status)}`));
  const details=disclosure(element('details','','doctor-details'),expandedDiagnostics,'diagnostics');details.append(element('summary',phrase('本机检查详情','Local check details')));
  for(const row of checks)details.append(element('p',`${label(row.id)} · ${status(row.status)}`));
  for(const [component,row] of Object.entries(report.observations||{}))if(row.evidence)details.append(element('p',`${label(component)} · ${stamp(row.observed_at)} · ${row.evidence}`));
  area.append(details,element('small',phrase('不扫描账户、不安装、不创建定时器；源码可用不等于账户已配置','No account scan, installation or scheduling; source availability does not verify account setup')));
}

function render(state) {
  state={...state,current_runs:PanelWorkspace.currentRuns(state)};
  const view=captureView($('task-filter').value);
  const focusedFilter=(document.activeElement?.id?.startsWith('filter-')||document.activeElement?.id?.startsWith('attention-'))?document.activeElement.id:null;
  lastState = state;
  $('recovery-notice').hidden=!state.recovery;
  $('recovery-notice').textContent=state.recovery?.[language==='en'?'notice_en':'notice_zh']||'';
  renderRules(state.rules);

  renderAbout(state.about);
  const m = state.metrics;
  $('scope').textContent = t(m.scope);
  $('updated').textContent = `${phrase('采样','Sampled')} ${stamp(m.sampled_at)}`;
  $('cpu').textContent = m.cpu_percent == null ? t('等待采样') : `${m.cpu_percent}%`;
  $('cpu-ring').style.setProperty('--meter',`${Math.max(0,Math.min(100,m.cpu_percent || 0))}%`);
  $('cpu-bar').style.width = `${Math.max(0,Math.min(100,m.cpu_percent || 0))}%`;
  $('cpu-detail').textContent = `${m.visible_cpu_count ?? t('未知')} ${phrase('个可见逻辑核 · cgroup 配额','visible cores · cgroup quota')} ${m.cpu_quota_cores == null ? phrase('未知 / 无有限值','unknown / no finite value') : m.cpu_quota_cores + phrase(' 核',' cores')}`;
  const used = m.memory_total != null && m.memory_available != null ? m.memory_total - m.memory_available : null;
  const memoryPercent=m.memory_total && used!=null ? Math.max(0,Math.min(100,used/m.memory_total*100)):null;
  $('memory').textContent=memoryPercent==null?t('未知'):`${Math.round(memoryPercent)}%`;
  $('memory-ring').style.setProperty('--meter',`${memoryPercent||0}%`);
  $('memory-bar').style.width = `${m.memory_total ? Math.max(0,Math.min(100,used/m.memory_total*100)) : 0}%`;
  $('memory-detail').textContent = `${phrase('可见使用','Visible used')} ${bytes(used)} / ${bytes(m.memory_total)} · ${phrase('cgroup 限额','cgroup limit')} ${bytes(m.memory_quota)}`;
  const diskPercent=m.disk_total?m.disk_used/m.disk_total*100:null;
  $('disk').textContent=diskPercent==null?t('未知'):`${Math.round(diskPercent)}%`;
  $('disk-ring').style.setProperty('--meter',`${diskPercent||0}%`);
  $('disk-bar').style.width = `${m.disk_total ? m.disk_used/m.disk_total*100 : 0}%`;
  $('disk-detail').textContent = `${phrase('卷使用率 · 剩余','Volume usage · free')} ${bytes(m.disk_free)} / ${bytes(m.disk_total)} ${phrase('（非账户配额）','(not account quota)')}`;
  $('os').textContent = m.os;
  $('system-detail').textContent = `${m.architecture} · Python ${m.python}`;
  const selected = $('task-filter').value;
  const taskChoices=JSON.stringify([language,...state.tasks.map(task=>[task.id,task.name])]);
  if($('task-filter').dataset.choices!==taskChoices&&document.activeElement!==$('task-filter')){
    $('task-filter').replaceChildren(element('option',t('所有活动 / 进度记录')));$('task-filter').firstChild.value='';
    for(const task of state.tasks){const option=element('option',task.name);option.value=task.id;$('task-filter').append(option);}
    $('task-filter').value=selected;$('task-filter').dataset.choices=taskChoices;
  }
  const chosen=state.tasks.find(task=>task.id===selected);
  $('conversation-list').hidden=Boolean(chosen);$('conversation-detail').hidden=!chosen;
  $('selected-task-title').textContent=chosen?chosen.name:'';
  const chosenRun=chosen?PanelWorkspace.rows([chosen],state.current_runs||state.latest_runs||state.runs)[0].run:null;
  renderAdvice(chosen,chosenRun);
  renderCloseout(chosenRun,state);
  renderFiles(state,selected);renderTaskParticipants(state,selected);
  renderOutputBar(state,selected);
  $('detail-status').textContent=chosen?t(statuses[chosenRun?.status||chosen.latest_status||'pending']):'';
  $('detail-updated').textContent=chosen?`${t('最近更新')} ${stamp(chosenRun?.progress_updated||chosenRun?.updated||chosen.created)}`:'';
  $('task-lifecycle-meta').replaceChildren();
  $('task-agent').replaceChildren();if(chosen){
    $('task-agent').append(ownerBadge(chosen.id,state));
    const progress=PanelWorkspace.workProgress(state,chosen.id,chosenRun);
    if(progress.unpaused_runs.length>1)$('task-agent').append(element('small',phrase(`未完成运行 · ${progress.unpaused_runs.length}`,`Unfinished runs · ${progress.unpaused_runs.length}`),'empty-caption'));
    for(const entry of progress.open_runs)if(entry.id!==progress.current_run_id)$('task-lifecycle-meta').append(element('p',`${phrase('其他未完成运行','Other unfinished run')}: ${t(statuses[entry.status]||entry.status)} · ${entry.note||phrase('未登记开始说明','No start note recorded')} · ${phrase('运行','Run')} ${entry.id} · ${PanelAgents.runNames(state,entry.id,language)||t('未分配')}`,'lifecycle-detail'));
    for(const [field,zh,en] of [['lifecycle_reason','状态原因','Reason'],['next_step','下一步','Next step'],['lifecycle_evidence','状态依据','Evidence']]){
      if(chosenRun?.[field])$('task-lifecycle-meta').append(element('p',`${phrase(zh,en)}: ${chosenRun[field]}`,'lifecycle-detail'));
    }
    if(chosenRun?.lifecycle_reason)$('task-lifecycle-meta').append(element('small',phrase('仅登记任务状态，不会控制执行者','Recorded lifecycle only; does not control the executor')));
    const owner=taskOwner(chosen.id,state);
    if(owner){const current=PanelAgents.taskLead(state,chosen.id).active.some(agent=>agent.id===owner.id)&&PanelAgents.work(state,owner).current.find(row=>row.run_id===progress.current_run_id);$('task-agent').append(element('p',current?`${t('当前工作（按最近观察）')} · ${PanelAgents.type(current.work_type,language)}`:t(owner.status==='idle'?'待命 · 无当前任务':'未确认为当前工作'),'agent-current'));}
  }
  $('session-binding').replaceChildren();
  const binding=(state.bindings||[]).find(item=>item.task_id===selected);
  if(!binding){$('session-binding').append(element('span',t('尚未绑定独立执行会话'),'binding-title'),element('p',t('这里是已登记活动与工作记录，不代表新建会话。')));}
  else{
    const sources={cloud_thread:'Cloud task',codex_thread:'Codex task'};
    const environments={cloud:t('云环境'),desktop:t('桌面环境'),remote:t('远程环境')};
    const observed={created:t('已创建'),running:t('运行中'),completed:t('已完成'),failed:t('失败'),interrupted:t('已中断'),unknown:t('未知')};
    $('session-binding').append(element('span',t('已登记会话绑定'),'binding-title'),element('p',`${sources[binding.source_type]||binding.source_type} · ${environments[binding.environment_kind]||binding.environment_kind}`),element('p',`${t('最近观察状态')} · ${observed[binding.observed_status]||binding.observed_status} · ${stamp(binding.observed_at)}`),element('small',`${t('手动同步摘要，非实时聊天')} · ${t('最近同步')} ${stamp(binding.synced_at)}`));
    if(binding.verified_url){try{const link=new URL(binding.verified_url);if(link.protocol==='https:'&&['chatgpt.com','chat.openai.com','codex.openai.com'].includes(link.hostname)&&!link.username&&!link.password&&(!link.port||link.port==='443')){const anchor=element('a',t('打开已核实的会话链接'),'binding-link');anchor.href=link.href;anchor.target='_blank';anchor.rel='noopener noreferrer';$('session-binding').append(anchor);}}catch(_){}}
  }
  $('task-count').textContent = state.tasks.length;
  $('task-empty').hidden = state.tasks.length > 0;
  $('task-list').replaceChildren();
  for (const {task,run} of PanelWorkspace.rows(state.tasks,state.current_runs||state.latest_runs||state.runs,workspaceFilter,workspaceQuery,state)) {
    $('task-list').append(taskCard(task,run,state));
  }
  $('project-activity').replaceChildren();
  const activity = PanelWorkspace.timeline(state,selected).filter(row=>row.kind==='activity');
  const stageNames = {planned:'规划',implementation:'实现',testing:'测试',review:'审查',delivered:'交付'};
  const stageState = {unknown:'历史状态未保留',planned:'计划中',in_progress:'进行中',verified:'已验证'};
  $('pipeline').replaceChildren();
  for (const [stage, title] of Object.entries(stageNames)) { const recent = activity.find(e=>e.stage===stage); $('pipeline').append(element('span', `${t(title)} · ${recent ? t(stageState[recent.state]) : t('未记录')}`, recent ? recent.state : '')); }
  $('progress-summary').textContent = activity.length ? `${t('最近更新')} ${stamp(activity[0].created)}` : t('尚无此任务的阶段记录');
  const timeline=PanelWorkspace.timeline(state,selected);
  if(!timeline.length)$('project-activity').append(element('p',t('还没有项目沟通摘要'),'event-empty'));
  for(const event of timeline){
    const item=element('div','','event');item.dataset.timelineKey=event.key;
    const role={user:'你',assistant:'助手',system:'系统',unknown:'来源未保留'}[event.role]||event.role;
    const stage=event.kind==='note'?phrase('开始说明','Start note'):event.kind==='event'?phrase('运行事件','Run event'):t(event.stage==='progress'?phrase('工作进展','Work progress'):event.stage==='recovered_summary'?'恢复摘要':event.stage==='assignment'?'负责人变更':event.stage==='work_type'?'任务类型更新':event.stage==='state_changed'?phrase('状态变更','State changed'):event.stage==='closeout'?phrase('交付与验证','Delivery & verification'):stageNames[event.stage]||event.stage);
    const metadata=[stamp(event.created),stage,event.state?t(stageState[event.state]||event.state):'',event.kind==='activity'?t(role):''].filter(Boolean).join(' · ');
    item.append(element('small',metadata),document.createTextNode(event.message));$('project-activity').append(item);
  }
  $('events').replaceChildren();
  const events=PanelWorkspace.timeline({...state,activity:[]},selected).filter(event=>event.kind==='event');
  if (!events.length) $('events').append(element('p',t('还没有运行记录'),'event-empty'));
  for (const event of events) { const item = element('div','','event'); item.append(element('small',`${stamp(event.created)} · ${event.run_id}`),document.createTextNode(event.message)); $('events').append(item); }
  $('active-work').replaceChildren();
  $('workspace-filter').value=workspaceFilter;
  renderStatusFilters(state);
  const workspace=PanelWorkspace.rows(state.tasks,state.current_runs||state.latest_runs||state.runs,workspaceFilter,'',state);
  if(!workspace.length)$('active-work').append(element('p',t('没有符合此状态的任务'),'empty-caption'));
  for(const {task,run} of workspace)$('active-work').append(taskCard(task,run,state));
  renderSchedules(state.schedules||[]);
  $('software-cards').replaceChildren();
  const software=state.software||[];
  if(!software.length)$('software-cards').append(registryCard(t('还没有登记的软件'),t('只会检查明确登记的白名单软件，不会扫描系统。')));
  for(const item of software){
    const card=registryCard(item.name,item.version||t('未知'));card.append(element('span',t(item.available?'已检测到':'未检测到'),'status '+(item.available?'succeeded':'')));
    const details=element('details','','registry-details');details.dataset.disclosureKey='software:'+item.id;details.open=expandedSoftware.has(item.id);details.append(element('summary',phrase('详情','Details')));
    details.addEventListener('toggle',()=>{if(details.open)expandedSoftware.add(item.id);else expandedSoftware.delete(item.id);});
    details.append(element('p',`${phrase('简介','Description')} · ${item.description}`),element('p',`${phrase('类型','Kind')} · ${item.kind}`),element('p',`${t('版本')} · ${item.version||t('未知')}`),element('small',`${t('检测时间')} ${stamp(item.verified_at)}`));
    const controls=element('div','','software-controls');for(const label of ['启动','停止']){const button=element('button',t(label));button.disabled=true;button.title=t('Web 只读；请使用本机快捷方式或管理入口');controls.append(button);}details.append(controls,element('p',t('Web 只读；请使用本机快捷方式或管理入口'),'empty-caption'));card.append(details);$('software-cards').append(card);
  }
  if(focusedFilter)$(focusedFilter)?.focus({preventScroll:true});
  restoreView(view,selected);
  panelNotifications?.observe(state);
}
function headerRegion(value) {
  if(!value||value.scope!=='panel_backend_exit'||value.provider!=='ipwho.is'||!Number.isFinite(value.checked_at)||!value.country)return phrase('后台出口：未核验','Backend exit: unverified');
  const parts=[...new Set([value.country,value.region,value.city].filter(Boolean))];
  return phrase('后台出口（约）：','Backend exit (approx.): ')+parts.join(', ')+(Date.now()/1000-value.checked_at>86400?phrase(' · 旧观察',' · old observation'):'');
}
function headerStamp(value) {
  if(value==null)return '—';
  return new Intl.DateTimeFormat(language==='zh'?'zh-CN':'en-GB',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(new Date(value*1000));
}
async function refresh() {
  if (busy) return;
  busy = true; $('refresh').disabled = true;
  try { const response = await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(4000)}); if(!response.ok) throw new Error('offline'); render(await response.json()); $('connection').textContent = phrase('本地数据','Local data')+' · '+phrase('每 5 秒','Every 5s')+' · '+headerStamp(lastState?.metrics?.sampled_at)+' · '+headerRegion(lastState?.exit_region); $('connection').title=lastState?.exit_region?'ipwho.is · '+stamp(lastState.exit_region.checked_at):''; $('indicator').classList.remove('offline'); }
  catch (_) { if(lastState){const view=captureView($('task-filter').value);for(const id of ['task-list','active-work','task-agent'])for(const badge of $(id).querySelectorAll?.('.owner-badge')||[])badge.replaceWith(ownerBadge(badge.dataset.taskId,lastState));restoreView(view,$('task-filter').value);} $('connection').textContent = t('连接中断 · 显示上次数据'); $('indicator').classList.add('offline'); }
  finally {busy = false; $('refresh').disabled = false;}
}
$('workspace-search').addEventListener('input',()=>{workspaceQuery=$('workspace-search').value;if(lastState)render(lastState);});
$('workspace-filter').addEventListener('change',()=>{workspaceFilter=$('workspace-filter').value;if(lastState)render(lastState);});
window.addEventListener('hashchange',showPage);
for(const nav of document.querySelectorAll('[data-nav]'))nav.addEventListener('click',()=>panelNotifications?.markRead(nav.dataset.nav));
$('back-conversations').addEventListener('click',()=>{adviceTaskId=null;$('task-filter').value='';if(lastState)render(lastState);});
showPage();
$('toggle-events').addEventListener('click',()=>{ const expanded=$('toggle-events').getAttribute('aria-expanded')==='true'; $('events').hidden=expanded; $('toggle-events').setAttribute('aria-expanded',String(!expanded)); $('toggle-events').textContent=phrase(expanded?'展开原始运行记录':'收起原始运行记录',expanded?'Show raw run records':'Hide raw run records'); });
$('language').addEventListener('change',()=>{
  preference=$('language').value;
  try { localStorage.setItem('dots-panel-language',preference); settingsError=''; } catch (_) { settingsError='save'; }
  language=PanelLocale.resolve(preference,navigator.language);
  renderPreferences();
  $('connection').textContent=t($('indicator').classList.contains('offline') ? '连接中断 · 显示上次数据' : lastState ? phrase('本地数据 · 每 5 秒','Local data · Every 5s') : '正在连接');
});
window.addEventListener('languagechange',()=>{
  if(preference==='auto'){language=PanelLocale.resolve(preference,navigator.language);translatePage();if(lastState)render(lastState);$('connection').textContent=t($('indicator').classList.contains('offline') ? '连接中断 · 显示上次数据' : lastState ? phrase('本地数据 · 每 5 秒','Local data · Every 5s') : '正在连接');}
});
translatePage();
updateSettings();
$('apply-timezone').addEventListener('click',()=>{
  let next;try { next=validateTimezone($('timezone').value.trim()); }
  catch (_) { settingsError='invalid';$('settings-error').textContent=phrase('无效或不支持的 IANA 时区','Invalid or unsupported IANA timezone');return; }
  try { localStorage.setItem('dots-panel-timezone',next);settingsError=''; } catch (_) {settingsError='save';}
  timezone=next;renderPreferences();
});
$('timezone').addEventListener('keydown',event=>{if(event.key==='Enter')$('apply-timezone').click();});
$('task-filter').addEventListener('change',()=>{if(lastState)render(lastState);});
$('refresh').addEventListener('click',refresh);
refresh(); setInterval(refresh,5000);

function renderFiles(state,taskId){
  const records=(state.artifacts||[]).filter(item=>item.task_id===taskId);
  $('task-files').replaceChildren();$('tab-files').textContent=`${t('文件')} · ${outputSummary(state,taskId).count}`;
  if(!records.length)$('task-files').append(element('p',t('尚无已登记产出'),'empty-caption'));
  for(const item of records){const card=element('article','','file-card');card.append(element('h3',item.title),element('small',`${t({report:'报告',image:'图片',document:'文档',data:'数据',video:'视频',other:'其他'}[item.kind]||'其他')} · ${Number(item.size).toLocaleString()} B · ${stamp(item.created)}`),element('p',PanelWorkspace.delivery(item,language),'file-delivery'),element('p',item.relative_path,'file-path'),element('small',`SHA-256 · ${item.sha256}`));$('task-files').append(card);}
}
function setDetailTab(tab){
  detailScrollPositions[detailTab]=$('detail-scroll').scrollTop||0;detailTab=tab;
  $('timeline-panel').hidden=tab!=='timeline';$('files-panel').hidden=tab!=='files';
  $('tab-timeline').setAttribute('aria-selected',String(tab==='timeline'));$('tab-files').setAttribute('aria-selected',String(tab==='files'));
  $('detail-scroll').scrollTop=detailScrollPositions[tab];
}
$('tab-timeline').addEventListener('click',()=>setDetailTab('timeline'));
$('tab-files').addEventListener('click',()=>setDetailTab('files'));
$('advice-text').addEventListener('keydown',event=>{if(event.key==='Escape'){adviceTaskId=null;$('attention-advice').hidden=true;$('back-conversations').focus();event.preventDefault();}});

$('output-summary-files').addEventListener('click',()=>{setDetailTab('files');$('tab-files').focus();});
