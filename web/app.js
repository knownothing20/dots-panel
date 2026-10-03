'use strict';
let renderTargets=null;
const $ = id => renderTargets?.get(id)||document.getElementById(id);
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
  $('detail-scroll').setAttribute('aria-label',phrase('任务详情','Task details'));
  $('back-conversations').setAttribute('aria-label',phrase('返回任务列表','Back to tasks')); 
  $('recovery-info-label').textContent=phrase('ⓘ 记录说明','ⓘ Record info');
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
let stateReadEpoch=0, stateNavigationPending=false;
let workspaceFilter = 'unfinished';
let adviceTaskId=null;
let detailTab='timeline';
let collaborationModeFilter='all', conversationTask=null, conversationFilters={agent:'',role:'',task:''}, conversationOffset=0;
let conversationRead={key:'',signature:'',data:null,error:'',serial:0};
const detailScrollPositions={timeline:0,files:0};
const expandedRules=new Set(), expandedDiagnostics=new Set(), expandedSteps=new Set(), expandedRequirements=new Set();
let renderedTaskId=null;
let requirementPreview={id:null,returnFocus:null};
const expandedSchedules=new Set(), expandedSoftware=new Set(), expandedSkills=new Set();
let workspaceQuery = '';
let lastState = null;
const panelNotifications=typeof PanelNotifications!=='undefined'?new PanelNotifications.Controller({document,language:()=>language,avatar:agentAvatar,openTask:async(id,{keyboard=false,requirementId=null}={})=>{if(requirementId)return openRequirement(requirementId,{preserveView:false});const task=lastState?.tasks?.find(item=>item.id===id);if(!task)throw Error('Task is unavailable');selectTask(task);if($('conversation-detail').hidden)throw Error('Task did not become visible');if(keyboard)$('detail-scroll').focus({preventScroll:true});return true;}}):null;
function element(tag, text, className) { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; }
// Preserve open evidence, focused disclosure and the visible timeline item during polling.
function disclosure(node,store,key) {
  node.setAttribute('data-disclosure-key',key);node.open=store.has(key);
  PanelPatch.listen(node,'toggle',(_event,current)=>{if(current.open)store.add(key);else store.delete(key);});
  return node;
}
function captureView(selected) {
  const scroll=$('detail-scroll'),sameTask=renderedTaskId===selected;
  const position={followBottom:sameTask&&conversationOffset===0&&Number.isFinite(scroll.scrollHeight)&&scroll.scrollHeight-scroll.clientHeight-scroll.scrollTop<=48,page:window.scrollY||0,detail:sameTask?(scroll.scrollTop||0):0,sameTask,focus:document.activeElement?.dataset?.focusKey||null,scope:document.activeElement?.closest?.('[data-page]')?.dataset.page||null};
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
  if(position.followBottom&&conversationOffset===0)scroll.scrollTop=scroll.scrollHeight;
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
        PanelPatch.listen(button,'click',()=>{workspaceFilter=value;render(lastState);});bar.append(button);
      }
      const select=element('select','','more-status-filter');
      for (const value of ['more',...Object.keys(statuses)]) {const option=element('option','');option.value=value;select.append(option);}
      select.options[0].disabled=true;
      PanelPatch.listen(select,'change',(_event,current)=>{workspaceFilter=current.value;render(lastState);});
      PanelPatch.listen(select,'blur',()=>{if(lastState)renderStatusFilters(lastState);});
      bar.append(select);
    }
    for (const [index,[value,label]] of main.entries()) {
      const button=bar.children[index];const caption=label+' '+PanelWorkspace.rows(tasks,runs,value).length;if(button.textContent!==caption)button.textContent=caption;
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
  const page=['overview','conversations','schedules','memory','reset','software','rules','about','settings'].includes(requested)?requested:'overview';
  for(const node of document.querySelectorAll('[data-page]'))node.hidden=node.dataset.page!==page;
  for(const node of document.querySelectorAll('[data-nav]')){node.classList.toggle('active',node.dataset.nav===page);if(node.dataset.nav===page)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');}
  if(page!=='conversations'||!$('task-filter').value)panelNotifications?.markRead(page,page==='conversations'?null:undefined);
  syncDetailShell(Boolean($('task-filter').value));
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
  const compactView=item=>{
    const platform=schedulePlatformView(item), result=scheduleResultView(item), observed=item.platform_observation, latest=item.external_result?.observation?.latest;
    const label=observed?(observed.enabled===true?phrase('已观察启用','Observed enabled'):observed.enabled===false?phrase('已观察停用','Observed disabled'):phrase('启用状态未知','Enabled state unknown')):phrase('配置待核实','Configuration unverified');
    const cadence=platform?.compact||phrase('计划待核实','Schedule unverified');
    let recent=latest?[latest.calendar_date,latest.status].filter(value=>value!=null&&value!=='').join(' · '):phrase('暂无结果记录','No result recorded');
    if(item.external_result?.fetch_error)recent=phrase('检查失败','Check failed')+' · '+recent;
    return {platform,result,label,cadence,recent};
  };
  $('schedule-summary').replaceChildren();
  if(!schedules.length)$('schedule-summary').append(element('p',t('还没有登记的自动化'),'empty-caption'));
  for(const item of schedules.slice(0,3)){
    const view=compactView(item),row=element('a','','schedule-row');row.dataset.patchKey='summary:'+item.id;row.href='#schedules';row.append(element('span','◷','small-icon'));
    const title=element('div','');title.append(element('strong',item.name),element('small',view.label),element('small',view.cadence),element('small',view.recent));
    row.append(title,element('span','›','row-chevron'));$('schedule-summary').append(row);
  }
  const boundary=phrase('平台配置为人工观察快照；结果快照不证明定时器已启用或首次执行成功','Platform configuration is a manual observation; result snapshots do not prove schedules are enabled or their first execution succeeded');
  $('automation-info-content').replaceChildren(element('p',boundary),element('p',phrase('每 5 秒只刷新本地数据，不轮询 GitHub；外部结果须手动同步','Every 5 seconds refreshes local data only, without polling GitHub; external results require manual sync')));
  $('schedule-cards').replaceChildren();
  if(!schedules.length)$('schedule-cards').append(registryCard(t('还没有登记的自动化'),t('使用本地 CLI 登记元数据，不会自动创建定时器。')));
  for(const item of schedules){
    const view=compactView(item),{platform,result}=view,card=element('article','','registry-card schedule-card');card.dataset.patchKey='schedule:'+item.id;
    const heading=element('div','','bundled-heading');heading.append(element('h2',item.name,'schedule-title'));if(schedulerBundled(item,lastState))heading.append(bundledBadge());card.append(heading,element('span',view.label,'status schedule-status'),element('p',view.cadence,'schedule-cadence'),element('p',view.recent,'schedule-result'));
    const details=element('details','','registry-details');details.dataset.disclosureKey='schedule:'+item.id;details.open=expandedSchedules.has(item.id);details.append(element('summary',phrase('详情','Details')));
    PanelPatch.listen(details,'toggle',(_event,current)=>{if(current.open)expandedSchedules.add(item.id);else expandedSchedules.delete(item.id);});
    if(item.project)details.append(element('p',`${phrase('项目','Project')}: ${item.project}`));
    if(result){details.append(element('p',result.label));for(const line of result.compact)details.append(element('p',line));if(result.error)details.append(element('p',result.error,'freshness-warning'));}
    const rows=[...(platform?.rows||[]),...(result?.rows||[])];
    for(const [label,value] of rows){const line=element('p',`${label}: ${value}`);line.style.overflowWrap='anywhere';if(label===phrase('计划','Schedule')||label===phrase('平台任务 ID','Platform task ID'))line.className='technical-record';details.append(line);}
    details.append(element('p',`${t('来源')} · ${item.source}`),
      element('p',`${phrase('登记状态（元数据）','Registered state (metadata)')}: ${t(states[item.state]||item.state)}`),
      element('p',`${phrase('登记计划时间（未核验）','Registered planned time (unverified)')}: ${item.next_run==null?t('未知'):stamp(item.next_run)}`),
      element('small',`${t('最近更新')} ${stamp(item.updated)}`),element('p',phrase('登记不会创建、启动或恢复任何定时器','Registration does not create, start or resume a scheduler')));
    card.append(details);$('schedule-cards').append(card);
  }
}
function selectTask(task,advice=false) {closeRequirementPreview(false);if($('task-filter').value!==task.id){$('detail-more').open=false;setDetailTab('timeline');detailScrollPositions.timeline=0;detailScrollPositions.files=0;$('detail-scroll').scrollTop=0;}adviceTaskId=advice?task.id:null;$('task-filter').value=task.id;render(lastState);location.hash='conversations';showPage();if(advice)$('advice-text').focus();}
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
  const status=run?.status||task.latest_status||'pending',summaryText=run?.lifecycle_reason||work.current_step||phrase('尚无工作进展摘要','No work progress recorded');
  const nextStep=run?.next_step||work.update?.next_step;
  const card=element('article','','task-card '+status);card.dataset.patchKey='task:'+task.id;
  card.title=[task.name,t(statuses[status]||status),summaryText,nextStep?phrase('下一步：','Next: ')+nextStep:''].filter(Boolean).join('\n');
  card.setAttribute('aria-label',task.name+' · '+t(statuses[status]||status));
  const top=element('div','','task-card-top'),origin=PanelCollaboration.automationSource(state,task.id);
  const mode=element('span',PanelCollaboration.mode(task,language)+(origin?' · '+phrase('自动化','Automation'):''),'task-mode-tag');mode.title=origin||PanelCollaboration.mode(task,language);
  const shortStatus=({waiting_user:['待回复','Reply needed'],waiting_external:['待外部','External wait'],awaiting_review:['待验收','Review'],paused:['已暂停','Paused'],pending:['未开始','Pending'],running:['进行中','Working'],succeeded:['已完成','Done'],failed:['失败','Failed'],cancelled:['已取消','Cancelled']}[status]||[status,status])[language==='en'?1:0];
  const people=avatarGroup(task,state),badge=element('span',shortStatus,'status '+status);badge.title=t(statuses[status]||status);badge.setAttribute('aria-label',t(statuses[status]||status));top.append(mode,people,badge);
  const title=element('h2',task.name);title.title=task.name;
  const summary=element('p',summaryText,'task-summary');summary.title=summaryText;summary.setAttribute('aria-label',summaryText);
  const progress=element('div','','task-progress');
  if(work.counts){const count=work.counts,measure=element('progress','');measure.max=count.total;measure.value=count.completed;measure.setAttribute('aria-label',phrase('已登记实际进度','Recorded measured progress'));progress.append(measure,element('small',`${count.completed} / ${count.total} ${count.unit}`));}
  const output=outputSummary(state,task.id),outputs=element('div','','task-outputs');outputs.append(element('strong',outputCountText(output),'output-count'));outputs.title=outputCountText(output);
  const actions=element('div','','task-card-actions');
  const details=element('button',phrase('详情','Details'),'filter-chip');details.type='button';details.dataset.focusKey='task-details:'+task.id;details.setAttribute('aria-label',phrase('查看任务详情：','View task details: ')+task.name);PanelPatch.listen(details,'click',event=>{event.stopPropagation();selectTask(task);});actions.append(details);
  if(output.count){const files=element('button',phrase('成果','Files'),'filter-chip');files.type='button';files.dataset.focusKey='task-files:'+task.id;files.setAttribute('aria-label',phrase('查看成果文件：','View output files: ')+task.name);PanelPatch.listen(files,'click',event=>{event.stopPropagation();openTaskFiles(task);});actions.append(files);}
  card.append(title,top,summary,progress,outputs,actions);PanelPatch.listen(card,'click',()=>selectTask(task));return card;
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
    const row=element('section','','skill-row');row.dataset.patchKey='skill:'+item.id;const head=element('div','','skill-heading');
    head.append(element('h3',skillText(item,'name')));if(item.source?.origin==='project_bundled')head.append(bundledBadge());
    if(safeSkillURL(item.url)){const link=element('a',en?'Manage ↗':'管理 ↗','binding-link');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';head.append(link);}
    row.append(head,element('p',skillText(item,'purpose')),element('p',(en?'When: ':'使用场景：')+skillText(item,'when_used'),'skill-caption'));
    const details=element('details','','registry-details');details.dataset.disclosureKey='skill:'+item.id;details.open=expandedSkills.has(item.id);details.append(element('summary',en?'Details':'详情'));
    PanelPatch.listen(details,'toggle',(_event,current)=>{if(current.open)expandedSkills.add(item.id);else expandedSkills.delete(item.id);});
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
  const projectTitle=element('div','','bundled-heading');projectTitle.append(element('h2',en?'Project guidelines':'项目规范'),bundledBadge());area.append(projectTitle);
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
  for(const [label,value] of rows){const row=element('div','','about-row');row.dataset.patchKey='about:'+label;row.append(element('span',t(label)),element('strong',value));$('about-rows').append(row);}
  $('about-repository').replaceChildren();
  const url=release.repo_url;
  if(typeof url==='string'&&/^https:\/\/github\.com\/[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?\/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\/?$/.test(url)){
    const link=element('a',t('GitHub 项目 ↗'),'binding-link');link.href=url;link.target='_blank';link.rel='noopener noreferrer';$('about-repository').append(link,element('small',url));
  }else $('about-repository').append(element('p',t('尚未登记已核验的 GitHub 项目'),'empty-caption'));
  $('about-notes').replaceChildren();for(const item of about.install_notes||[])$('about-notes').append(element('p','• '+(item[language]||'')));
}
function backupView(value={}) {
  const names={unconfigured:['未配置备份展示','Backup display not configured'],unavailable:['备份记录不可用','Backup records unavailable'],unverified:['尚无可核验恢复点','No verified recovery point'],verified:['有已核验恢复点','Verified recovery point recorded'],stale:['恢复记录较旧','Recovery evidence is older'],failed:['最近尝试受阻','Latest attempt blocked'],pending:['有未完成尝试记录','Pending attempt recorded']};
  const title=(names[value.status]||names.unconfigured)[language==='en'?1:0],point=value.last_verified,destination=value.destination,attempt=value.last_attempt,unknown=phrase('未知','Unknown');
  const watch=value.task_watch||{},watchNames={unverified:['巡检未核验','Task checks unverified'],checked:['最近任务巡检成功','Last task check succeeded'],stale:['任务巡检记录较旧','Task check observation is older'],failed:['任务巡检失败','Task check failed'],unavailable:['任务巡检不可用','Task checks unavailable'],record_unavailable:['巡检记录不可用','Task check records unavailable'],invalid:['巡检记录无效','Task check record invalid']};
  const watchTitle=(watchNames[watch.status]||watchNames.unverified)[language==='en'?1:0],watchSuccess=watch.last_success_at?stamp(watch.last_success_at):unknown;
  const watchCompact=watchTitle+' · '+phrase('最后成功：','Last successful: ')+watchSuccess;
  const rows=[
    ['destination',phrase('私有备份目的地','Private destination'),destination?(destination.label===destination.provider||destination.label.startsWith(destination.provider+' · ')?destination.label:destination.provider+' · '+destination.label):unknown],
    ['path',phrase('Library 路径','Library path'),destination?.path||unknown],
    ['state',phrase('本机状态目录','Local state directory'),value.state_dir||unknown],
    ['snapshot',phrase('最后核验快照','Last verified snapshot'),point?stamp(point.captured_at):unknown],
    ['verified',phrase('恢复核验时间','Restore verification time'),point?stamp(point.verified_at):unknown],
    ['version',phrase('已记录索引版本','Recorded index version'),point?String(point.index_version):unknown],
  ];
  if(point)rows.push(['scope',phrase('已核验清单','Verified inventory'),phrase(`源码 ${point.source_file_count} · 数据 ${point.data_file_count} · 外部固定依赖 ${point.external_file_count} · checkpoint ${point.checkpoint_count}`,`Source ${point.source_file_count} · Data ${point.data_file_count} · Pinned external dependencies ${point.external_file_count} · Checkpoints ${point.checkpoint_count}`)],['exclusions',phrase('清单排除记录','Recorded exclusions'),String(point.exclusion_count)],['logical_size',phrase('快照逻辑体积（非云端占用）','Snapshot logical size (not cloud storage use)'),Number.isSafeInteger(point.size_bytes)?point.size_bytes.toLocaleString('en-US')+' bytes':unknown]);
  rows.push(
    ['attempt',phrase('最近尝试观察','Last attempt observation'),attempt?stamp(attempt.checked_at)+' · '+attempt.stage+' · '+attempt.result+(attempt.error_type?' · '+attempt.error_type:''):unknown],
    ['watch_check',phrase('任务巡检最近检查','Last task check attempt'),watch.checked_at?stamp(watch.checked_at):unknown],
    ['watch_success',phrase('任务巡检最后成功','Last successful task check'),watchSuccess],
    ['watch_error',phrase('任务巡检错误类别','Task check error type'),watch.error_type||unknown],
    ['quota',phrase('Library 容量与剩余额度','Library quota and free capacity'),unknown],
    ['live',phrase('远端当前状态','Current remote state'),phrase('未实时查询；本页只读本机历史回执','Not queried live; local historical receipts only')],
    ['limits',phrase('覆盖边界','Coverage limits'),phrase('按已核验清单恢复源码、数据库、登记文件与选定 checkpoint；不恢复平台会话、账户 Skill 或调度器','Restore source, database, registered files and selected checkpoints per the verified manifest; not platform sessions, account Skills or schedulers')],
    ['excluded',phrase('默认排除','Excluded by default'),phrase('凭据、cookie、环境秘密、日志、缓存、逐帧渲染及未授权目录；具体以冻结 policy 和清单为准','Credentials, cookies, environment secrets, logs, caches, render frames and unapproved folders; frozen policy and manifest are authoritative')]
  );
  let note=phrase('本机缓存不是异地备份；恢复必须先在全新私有目录核验。快照之后的进展未必已备份。','Local cache is not an off-machine backup. Verify recovery in a new private directory first. Progress after the snapshot may not be backed up.');
  if(value.observation_state==='invalid')note=phrase('最近尝试观察无效；保留已核验恢复点。','Latest attempt observation is invalid; retaining the verified recovery point. ')+note;
  if(point?.hydrated)note+=phrase(' 本机状态由远端回读重建，不代表原历史提交过程已独立证明。',' Local state was rebuilt from remote readback; original historical commit steps were not independently proven.');
  return {title,rows,note,watchCompact,compact:title+(point?' · '+phrase('最后核验快照：','Last verified snapshot: ')+stamp(point.captured_at):'')};
}
function renderBackup(value={}) {
  const view=backupView(value);
  textPatch('backup-title',phrase('备份与恢复','Backup & recovery'));
  textPatch('backup-summary-title',phrase('备份与恢复','Backup & recovery'));
  textPatch('backup-details-link',phrase('查看详情','View details'));
  textPatch('backup-summary-status',view.compact);
  textPatch('task-watch-summary',view.watchCompact);textPatch('task-watch-status',view.watchCompact);
  textPatch('backup-summary-note',phrase('本机历史回执；未实时查询远端状态。','Local historical evidence; remote state is not queried live.'));
  textPatch('backup-status',view.title);textPatch('backup-note',view.note);
  const warning=['failed','unavailable','unverified','stale','pending'].includes(value.status);
  $('backup-status').classList.toggle('backup-warning',warning);$('backup-summary-status').classList.toggle('backup-warning',warning);
  const rows=view.rows.map(([key,title,value])=>{const row=element('div','','backup-row');row.dataset.patchKey='backup:'+key;row.append(element('dt',title),element('dd',value));return row;});
  PanelPatch.children($('backup-rows'),rows);
  textPatch('backup-about-title',phrase('云工作区与恢复','Cloud workspace & recovery'));
  textPatch('backup-about-note',phrase('云电脑可在使用之间保留状态，但本机文件不能单独作为持久保存保证。曾观察到工作区目录不可用，原因未确认，不能据此断言每天重置。恢复以私有 Library 最后核验快照为准；GitHub 只同步源码，不含私有 DATA。','Cloud computers can retain state between uses, but local files alone are not a durability guarantee. Workspace directories have been observed unavailable; the cause is unconfirmed, not evidence of a daily reset. Recovery relies on the last verified private Library snapshot. GitHub contains source only, never private DATA.'));
  textPatch('backup-about-link',phrase('查看备份与恢复 →','Backup details →'));
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
  const rows=PanelCollaboration.participants(state,task.id),group=element('button','','participant-avatar-group');group.type='button';group.hidden=!rows.length;
  group.setAttribute('aria-label',phrase(`查看全部 ${rows.length} 位任务参与者`,`View all ${rows.length} task participants`));
  for(const row of rows.slice(0,3))group.append(agentAvatar(row.agent));
  if(rows.length>3)group.append(element('span','+'+(rows.length-3),'participant-overflow'));
  PanelPatch.listen(group,'click',event=>{event.stopPropagation();selectTask(task);setDetailTab('timeline');$('detail-more').open=true;$('task-participants').scrollIntoView?.({block:'start'});});return group;
}
function renderTaskParticipants(state,taskId) {
  const area=$('task-participants');area.replaceChildren();const rows=PanelCollaboration.participants(state,taskId);area.hidden=!rows.length;if(!rows.length)return;
  area.append(element('h3',phrase('任务参与者 · ','Task participants · ')+rows.length));
  for(const {agent,assignments} of rows){
    const item=element('div','','activity-participant');item.dataset.patchKey='participant:'+agent.id;const head=element('div','','agent-heading');head.append(agentAvatar(agent),element('strong',PanelAgents.reference(agent,language)),element('span',PanelAgents.text(agent,'name',language)));item.append(head);
    const roles=[...new Set(assignments.map(a=>PanelAgents.type(a.work_type,language)))];item.append(element('small',phrase('已登记职责 · ','Recorded roles · ')+roles.join(' / ')));
    const observed=PanelAgents.observation(agent,state);item.append(element('small',(observed.recent?PanelAgents.lifecycle(agent.status,language):phrase('状态待核实','State unconfirmed'))+' · '+stamp(agent.observed_at)));
    const detail=element('details','','participant-details');detail.append(element('summary',t('详情')),element('p',phrase('昵称 · ','Nickname · ')+PanelAgents.text(agent,'name',language)),element('p',identityLabel(agent)),element('p',identitySource(agent)+' · '+stamp(agent.identity_observed_at)),element('p',phrase('面板短编号，不是平台 UUID','Panel-local short ID, not a platform UUID')));for(const assignment of assignments)detail.append(element('p',stamp(assignment.assigned_at)+' · '+PanelAgents.type(assignment.work_type,language)+' · '+executionConfigLabel(assignment.execution_config||assignment),'execution-config'));item.append(detail);
    area.append(item);
  }
}


function renderConversationHeader(state,task) {
  PanelPatch.children($('detail-avatars'),task?[avatarGroup(task,state)]:[]);
  textPatch('detail-mode',task?PanelCollaboration.mode(task,language):'');
  textPatch('detail-artifacts',(detailTab==='files'?phrase('← 会话','← Conversation'):phrase('成果','Files'))+' · '+(task?outputSummary(state,task.id).count:0));
  textPatch('detail-more-toggle',phrase('更多','More'));
  textPatch('tab-timeline',phrase('协作会话','Conversation'));
  textPatch('conversation-agent-label',phrase('作者','Author'));textPatch('conversation-role-label',phrase('事件时职责','Role at event'));textPatch('conversation-task-caption',phrase('任务','Task'));
  textPatch('conversation-previous',phrase('上一页','Previous'));textPatch('conversation-next',phrase('下一页','Next'));
  for(const [i,value] of [phrase('类型 · 全部','Type · All'),phrase('单人','Single'),phrase('团队','Team'),phrase('项目','Project')].entries())if($('collaboration-mode-filter').options[i]&&$('collaboration-mode-filter').options[i].textContent!==value)$('collaboration-mode-filter').options[i].textContent=value;
  syncConversationHeader();
}
function syncConversationHeader() {
  const header=$('detail-header'),scroll=$('detail-scroll'),collapsed=header.classList.contains('is-compact');
  const secondary=header.querySelector?.('.detail-secondary');
  if(secondary?.contains(document.activeElement))return;
  header.classList.toggle('is-compact',collapsed?scroll.scrollTop>8:scroll.scrollTop>64);
}
function conversationSelect(id,choices,value) {
  const select=$(id),signature=JSON.stringify(choices);
  if(select.dataset.choices!==signature&&document.activeElement!==select){select.replaceChildren();for(const [key,label] of choices){const option=element('option',label);option.value=key;select.append(option);}select.dataset.choices=signature;}
  select.value=value;
}
function renderConversationStream(state,taskId) {
  if(conversationTask!==taskId){conversationTask=taskId;conversationFilters={agent:'',role:'',task:''};conversationOffset=0;conversationRead={key:'',signature:'',data:null,error:'',serial:conversationRead.serial+1};}
  const choices=PanelCollaboration.choices(state,taskId),unknown=phrase('匿名','Anonymous');
  conversationSelect('conversation-agent',[['',phrase('所有作者','All authors')],['unattributed',unknown],...choices.agents.map(a=>[a.id,PanelAgents.text(a,'name',language)+' · '+(a.panel_short_id||a.id)])],conversationFilters.agent);
  conversationSelect('conversation-role',[['',phrase('所有职责','All roles')],['unattributed',unknown],...choices.roles.map(role=>[role,PanelAgents.type(role,language)])],conversationFilters.role);
  conversationSelect('conversation-task',[['',phrase('整个项目','Whole project')],...choices.tasks.map(t=>[t.id,t.name])],conversationFilters.task);
  const task=(state.tasks||[]).find(t=>t.id===taskId);$('conversation-task-label').hidden=task?.activity_kind!=='project';
  const key=JSON.stringify([taskId,conversationFilters,conversationOffset]),cached=conversationRead.key===key?conversationRead.data:null;
  const requirementMap=new Map((state.requirements||[]).map(q=>[q.id,q]));
  let baseRows=[...(cached?.rows||PanelCollaboration.rows(state,taskId,conversationFilters))];
  if(!cached&&!conversationFilters.agent&&!conversationFilters.role){const ids=new Set([taskId,...(task?.activity_kind==='project'?(state.tasks||[]).filter(t=>t.parent_task_id===taskId).map(t=>t.id):[])]);for(const q of requirementMap.values())if(ids.has(q.task_id)&&!baseRows.some(r=>r.key==='requirement:'+q.id))baseRows.push({kind:'requirement',key:'requirement:'+q.id,requirement_id:q.id,created:q.observed_at,task_id:q.task_id});}
  const rows=baseRows.map(row=>row.kind==='requirement'?{...row,requirement:requirementMap.get(row.requirement_id||row.source_id||row.id)||row.requirement}:row).sort((a,b)=>(a.created||0)-(b.created||0)||String(a.key).localeCompare(String(b.key)));
  const area=$('project-activity'),nextRows=[];area.setAttribute('aria-label',phrase('已登记协作记录','Recorded conversation'));
  for(const event of rows){
    if(event.kind==='requirement'){nextRows.push(requirementCard(event.requirement||{},event));continue;}
    const actor=PanelCollaboration.actor(event,state,language),item=element('article','','event conversation-message');item.dataset.timelineKey=event.key;item.style.setProperty('--actor-tint',actor.color);
    const head=element('div','','message-author');
    const system=event.actor_type==='system'||event.role==='system'||event.kind==='system'||['state_changed','assignment','requirement_state','requirement_owner'].includes(event.stage);if(system){actor.label=phrase('系统记录','System record');actor.role='';actor.known=false;}
    head.append(actor.known?agentAvatar(actor.agent):anonymousAvatar());
    const identity=element('div','','message-identity');identity.append(element('strong',actor.label),element('small',[actor.shortId,actor.role].filter(Boolean).join(' · ')));head.append(identity,element('time',stamp(event.created)));item.append(head);
    const stage=event.kind==='note'?phrase('开始说明','Start note'):event.kind==='event'?phrase('运行事件','Run event'):t(event.stage==='progress'?phrase('工作进展','Work progress'):({planned:'规划',implementation:'实现',testing:'测试',review:'审查',delivered:'交付'}[event.stage]||event.stage||''));
    const taskName=(state.tasks||[]).find(t=>t.id===event.task_id)?.name||event.task_id;
    item.append(element('small',[stage,event.state?t(({unknown:'历史状态未保留',planned:'计划中',in_progress:'进行中',verified:'已验证'}[event.state]||event.state)):'',task?.activity_kind==='project'?taskName:''].filter(Boolean).join(' · '),'message-context'),element('p',event.message||'','message-body'));item.append(element('small',executionConfigLabel(event.attribution?.execution_config),'execution-config'));nextRows.push(item);
  }
  if(!rows.length)nextRows.push(element('p',phrase('没有符合筛选的记录','No matching records'),'event-empty'));
  PanelPatch.children(area,nextRows);renderConversationFilterChips();renderRequirementBookmarks(state,taskId);
  const count=cached?`${cached.offset+Math.min(1,cached.rows.length)}–${cached.offset+cached.rows.length} / ${cached.total}`:phrase('当前快照','Current snapshot');
  $('conversation-note').textContent=phrase('本页按时间顺序 · 摘要记录，非实时聊天','Chronological on this page · Recorded summaries, not live chat')+(conversationRead.error?' · '+(cached?phrase('刷新失败，保留上次读取','Refresh failed; showing last successful read'):phrase('完整记录读取失败，当前仅快照窗口','Full history unavailable; snapshot window only')):!cached&&state.timeline_window?.truncated?' · '+phrase('快照有截断，正在读取完整记录','Snapshot is truncated; loading full history'):'');
  $('conversation-page').textContent=count;$('conversation-previous').disabled=!cached||!conversationOffset;$('conversation-next').disabled=!cached||!cached.has_more;$('conversation-pagination').hidden=(!cached||cached.total<=cached.limit)&&!conversationRead.pending;
  if(taskId)readConversation(state,taskId,key);
}
function readConversation(state,taskId,key) {
  const signature=JSON.stringify([key,state.activity,state.events,state.timeline_window,state.requirement_counters]);
  if(conversationRead.key===key&&conversationRead.signature===signature)return;
  const serial=conversationRead.serial+1,old=conversationRead.key===key?conversationRead.data:null;
  conversationRead={key,signature,data:old,error:'',serial};
  const args={task_id:taskId,include_children:'true',limit:'100',offset:String(conversationOffset),agent_id:conversationFilters.agent,work_type:conversationFilters.role,child_task_id:conversationFilters.task};
  const query=Object.entries(args).filter(([,v])=>v!=='').map(([k,v])=>encodeURIComponent(k)+'='+encodeURIComponent(v)).join('&');
  fetch('/api/collaboration-timeline?'+query,{signal:AbortSignal.timeout(5000)}).then(response=>{if(!response.ok)throw Error('read');return response.json();}).then(data=>{
    if(conversationRead.serial!==serial||conversationTask!==taskId)return;
    if(!Array.isArray(data.rows)||!Number.isInteger(data.total))throw Error('shape');
    const view=captureView(taskId);
    if(old&&view.sameTask&&!view.followBottom&&view.detail>0){
      // Keep the currently read page's membership until explicit navigation; current requirement facts still come from the complete snapshot.
      conversationRead.pending=data;const latest=new Map(data.rows.map(row=>[row.key,row]));conversationRead.data={...old,rows:old.rows.map(row=>latest.get(row.key)||row)};
      $('conversation-new').hidden=false;$('conversation-new').textContent=phrase('更新当前页 ↓','Update this page ↓');$('conversation-pagination').hidden=false;
    }else{conversationRead.data=data;conversationRead.pending=null;$('conversation-new').hidden=true;}
    renderConversationStream(lastState||state,taskId);restoreView(view,taskId);
  }).catch(()=>{if(conversationRead.serial===serial){conversationRead.error='read';const note=$('conversation-note');note.textContent=conversationRead.data?phrase('刷新失败，保留上次读取；下次刷新重试','Refresh failed; showing last successful read. Retrying on refresh'):phrase('完整记录读取失败，当前仅显示快照窗口；下次刷新重试','Full history unavailable; snapshot window only. Retrying on refresh');}});
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
  const files=element('button',phrase('查看文件','View files'),'filter-chip');files.type='button';PanelPatch.listen(files,'click',()=>setDetailTab('files'));body.append(files);
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

function renderMetrics(state) {
  const m = state.metrics||{};
  textPatch('scope',t(m.scope));
  textPatch('updated',`${phrase('采样','Sampled')} ${stamp(m.sampled_at)}`);
  textPatch('cpu',m.cpu_percent == null ? t('等待采样') : `${m.cpu_percent}%`);
  $('cpu-ring').style.setProperty('--meter',`${Math.max(0,Math.min(100,m.cpu_percent || 0))}%`);
  $('cpu-bar').style.width = `${Math.max(0,Math.min(100,m.cpu_percent || 0))}%`;
  textPatch('cpu-detail',`${m.visible_cpu_count ?? t('未知')} ${phrase('个可见逻辑核 · cgroup 配额','visible cores · cgroup quota')} ${m.cpu_quota_cores == null ? phrase('未知 / 无有限值','unknown / no finite value') : m.cpu_quota_cores + phrase(' 核',' cores')}`);
  const used = m.memory_total != null && m.memory_available != null ? m.memory_total - m.memory_available : null;
  const memoryPercent=m.memory_total && used!=null ? Math.max(0,Math.min(100,used/m.memory_total*100)):null;
  textPatch('memory',memoryPercent==null?t('未知'):`${Math.round(memoryPercent)}%`);
  $('memory-ring').style.setProperty('--meter',`${memoryPercent||0}%`);
  $('memory-bar').style.width = `${m.memory_total ? Math.max(0,Math.min(100,used/m.memory_total*100)) : 0}%`;
  textPatch('memory-detail',`${phrase('可见使用','Visible used')} ${bytes(used)} / ${bytes(m.memory_total)} · ${phrase('cgroup 限额','cgroup limit')} ${bytes(m.memory_quota)}`);
  const diskPercent=m.disk_total?m.disk_used/m.disk_total*100:null;
  textPatch('disk',diskPercent==null?t('未知'):`${Math.round(diskPercent)}%`);
  $('disk-ring').style.setProperty('--meter',`${diskPercent||0}%`);
  $('disk-bar').style.width = `${m.disk_total ? m.disk_used/m.disk_total*100 : 0}%`;
  textPatch('disk-detail',`${phrase('卷使用率 · 剩余','Volume usage · free')} ${bytes(m.disk_free)} / ${bytes(m.disk_total)} ${phrase('（非账户配额）','(not account quota)')}`);
  textPatch('os',m.os);
  textPatch('system-detail',`${m.architecture} · Python ${m.python}`);
}
function renderSoftware(state) {
  $('software-cards').replaceChildren();
  const software=state.software||[];
  if(!software.length)$('software-cards').append(registryCard(t('还没有登记的软件'),t('只会检查明确登记的白名单软件，不会扫描系统。')));
  for(const item of software){
    const card=registryCard(item.name,item.version||t('未知'));card.dataset.patchKey='software:'+item.id;card.append(element('span',t(item.available?'已检测到':'未检测到'),'status '+(item.available?'succeeded':'')));
    const details=element('details','','registry-details');details.dataset.disclosureKey='software:'+item.id;details.open=expandedSoftware.has(item.id);details.append(element('summary',phrase('详情','Details')));
    PanelPatch.listen(details,'toggle',(_event,current)=>{if(current.open)expandedSoftware.add(item.id);else expandedSoftware.delete(item.id);});
    details.append(element('p',`${phrase('简介','Description')} · ${item.description}`),element('p',`${phrase('类型','Kind')} · ${item.kind}`),element('p',`${t('版本')} · ${item.version||t('未知')}`),element('small',`${t('检测时间')} ${stamp(item.verified_at)}`));
    const controls=element('div','','software-controls');for(const label of ['启动','停止']){const button=element('button',t(label));button.disabled=true;button.title=t('Web 只读；请使用本机快捷方式或管理入口');controls.append(button);}details.append(controls,element('p',t('Web 只读；请使用本机快捷方式或管理入口'),'empty-caption'));card.append(details);$('software-cards').append(card);
  }
}
function renderDetailMetadata(state,chosen,chosenRun,selected) {
  $('task-lifecycle-meta').replaceChildren();
  $('task-agent').replaceChildren();if(chosen){
    $('task-agent').append(ownerBadge(chosen.id,state));
    const progress=PanelWorkspace.workProgress(state,chosen.id,chosenRun);
    $('task-lifecycle-meta').append(element('p',PanelCollaboration.mode(chosen,language)+(chosen.project?' · '+chosen.project:''),'lifecycle-detail'));
    if(chosenRun?.stale)$('task-lifecycle-meta').append(element('p',staleLabel(chosenRun),'lifecycle-detail'));
    const origin=PanelCollaboration.automationSource(state,chosen.id);if(origin)$('task-lifecycle-meta').append(element('p',phrase('自动化来源：','Automation source: ')+origin,'lifecycle-detail'));
    if(!chosenRun?.next_step&&progress.update?.next_step)$('task-lifecycle-meta').append(element('p',phrase('下一步：','Next: ')+progress.update.next_step,'lifecycle-detail'));
    if(progress.update?.evidence)$('task-lifecycle-meta').append(element('p',phrase('进度依据：','Progress evidence: ')+progress.update.evidence,'lifecycle-detail'));
    if(progress.counts)$('task-lifecycle-meta').append(element('p',phrase('已记录实际进度：','Recorded measured progress: ')+progress.counts.completed+' / '+progress.counts.total+' '+progress.counts.unit,'lifecycle-detail'));
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
  if(!binding){$('session-binding').append(element('span',t('尚未绑定独立执行会话'),'binding-title'),element('p',t('这里是已登记任务与工作记录，不代表新建会话。')));}
  else{
    const sources={cloud_thread:'Cloud task',codex_thread:'Codex task'};
    const environments={cloud:t('云环境'),desktop:t('桌面环境'),remote:t('远程环境')};
    const observed={created:t('已创建'),running:t('运行中'),completed:t('已完成'),failed:t('失败'),interrupted:t('已中断'),unknown:t('未知')};
    $('session-binding').append(element('span',t('已登记会话绑定'),'binding-title'),element('p',`${sources[binding.source_type]||binding.source_type} · ${environments[binding.environment_kind]||binding.environment_kind}`),element('p',`${t('最近观察状态')} · ${observed[binding.observed_status]||binding.observed_status} · ${stamp(binding.observed_at)}`),element('small',`${t('手动同步摘要，非实时聊天')} · ${t('最近同步')} ${stamp(binding.synced_at)}`));
    if(binding.verified_url){try{const link=new URL(binding.verified_url);if(link.protocol==='https:'&&['chatgpt.com','chat.openai.com','codex.openai.com'].includes(link.hostname)&&!link.username&&!link.password&&(!link.port||link.port==='443')){const anchor=element('a',t('打开已核实的会话链接'),'binding-link');anchor.href=link.href;anchor.target='_blank';anchor.rel='noopener noreferrer';$('session-binding').append(anchor);}}catch(_){}}
  }
}
function renderRawEvents(state,selected) {
  $('events').replaceChildren();
  const events=PanelWorkspace.timeline({...state,activity:[]},selected).filter(event=>event.kind==='event');
  if (!events.length) $('events').append(element('p',t('还没有运行记录'),'event-empty'));
  for (const event of events) { const item = element('div','','event'); item.dataset.patchKey='raw:'+event.key;item.append(element('small',`${stamp(event.created)} · ${event.run_id}`),document.createTextNode(event.message)); $('events').append(item); }
}
function renderProgressMetadata(state,selected) {
  const activity = PanelWorkspace.timeline(state,selected).filter(row=>row.kind==='activity');
  const stageNames = {planned:'规划',implementation:'实现',testing:'测试',review:'审查',delivered:'交付'};
  const stageState = {unknown:'历史状态未保留',planned:'计划中',in_progress:'进行中',verified:'已验证'};
  $('pipeline').replaceChildren();
  for (const [stage, title] of Object.entries(stageNames)) { const recent = activity.find(e=>e.stage===stage); $('pipeline').append(element('span', `${t(title)} · ${recent ? t(stageState[recent.state]) : t('未记录')}`, recent ? recent.state : '')); }
  $('progress-summary').textContent = activity.length ? `${t('最近更新')} ${stamp(activity[0].created)}` : t('尚无此任务的阶段记录');
}
function render(state,polling=false) {
  if(polling&&lastState)return renderIncremental(state);
  state={...state,current_runs:PanelWorkspace.currentRuns(state)};
  const view=captureView($('task-filter').value);
  const focusedFilter=(document.activeElement?.id?.startsWith('filter-')||document.activeElement?.id?.startsWith('attention-'))?document.activeElement.id:null;
  lastState = state;
  $('recovery-info').hidden=!state.recovery;
  $('recovery-notice').textContent=state.recovery?.[language==='en'?'notice_en':'notice_zh']||'';
  renderRules(state.rules);

  renderAbout(state.about);
  renderBackup(state.backup);
  renderMetrics(state);renderMemory(state);renderReset(state);renderRecoveredEvidence(state);
  const selected = $('task-filter').value;
  const taskChoices=JSON.stringify([language,...state.tasks.map(task=>[task.id,task.name])]);
  if($('task-filter').dataset.choices!==taskChoices&&document.activeElement!==$('task-filter')){
    $('task-filter').replaceChildren(element('option',t('所有任务 / 进度记录')));$('task-filter').firstChild.value='';
    for(const task of state.tasks){const option=element('option',task.name);option.value=task.id;$('task-filter').append(option);}
    $('task-filter').value=selected;$('task-filter').dataset.choices=taskChoices;
  }
  const chosen=state.tasks.find(task=>task.id===selected);
  $('conversation-list').hidden=Boolean(chosen);$('conversation-detail').hidden=!chosen;
  syncDetailShell(Boolean(chosen));
  $('selected-task-title').textContent=chosen?chosen.name:'';
  const chosenRun=chosen?PanelWorkspace.rows([chosen],state.current_runs||state.latest_runs||state.runs)[0].run:null;
  renderAdvice(chosen,chosenRun);
  renderCloseout(chosenRun,state);
  renderFiles(state,selected);renderTaskParticipants(state,selected);
  renderOutputBar(state,selected);renderConversationHeader(state,chosen);
  $('detail-status').textContent=chosen?t(statuses[chosenRun?.status||chosen.latest_status||'pending']):'';
  $('detail-updated').textContent=chosen?`${t('最近更新')} ${stamp(meaningfulTaskTime(state,chosen,chosenRun))}`:'';
  renderDetailMetadata(state,chosen,chosenRun,selected);
  const filteredTaskRows = PanelWorkspace.rows(state.tasks,state.current_runs||state.latest_runs||state.runs,workspaceFilter,workspaceQuery,state).filter(({task})=>PanelCollaboration.matchesMode(task,collaborationModeFilter));
  $('task-count').textContent = filteredTaskRows.length;
  $('task-empty').hidden = filteredTaskRows.length > 0;
  $('task-list').replaceChildren();
  for (const {task,run} of filteredTaskRows) {
    $('task-list').append(taskCard(task,run,state));
  }
  $('project-activity').replaceChildren();
  renderProgressMetadata(state,selected);
  if(conversationRead.error)conversationRead.signature='';
  renderConversationStream(state,selected);
  renderRawEvents(state,selected);
  $('active-work').replaceChildren();
  $('workspace-filter').value=workspaceFilter;
  renderStatusFilters(state);
  const workspace=PanelWorkspace.rows(state.tasks,state.current_runs||state.latest_runs||state.runs,workspaceFilter,'',state);
  if(!workspace.length)$('active-work').append(element('p',t('没有符合此状态的任务'),'empty-caption'));
  for(const {task,run} of workspace)$('active-work').append(taskCard(task,run,state));
  renderSchedules(state.schedules||[]);
  renderSoftware(state);
  if(focusedFilter)$(focusedFilter)?.focus({preventScroll:true});
  restoreView(view,selected);renderRequirementPreview(state);
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
  if (busy||stateNavigationPending) return;
  const epoch=stateReadEpoch;
  const manual=arguments[0]===true;
  busy = true;if(manual)$('refresh').disabled = true;
  try { const response = await fetch('/api/state'+($('task-filter').value?'?task_id='+encodeURIComponent($('task-filter').value):''),{cache:'no-store',signal:AbortSignal.timeout(4000)}); if(!response.ok) throw new Error('offline');const input=await response.json();if(epoch!==stateReadEpoch)return;render(input,true); $('connection').textContent = phrase('本地数据','Local data')+' · '+phrase('每 5 秒','Every 5s')+' · '+headerStamp(lastState?.metrics?.sampled_at)+' · '+headerRegion(lastState?.exit_region); $('connection').title=lastState?.exit_region?'ipwho.is · '+stamp(lastState.exit_region.checked_at):''; $('indicator').classList.remove('offline'); }
  catch (_) {if(epoch!==stateReadEpoch)return; $('connection').textContent = t('连接中断 · 显示上次数据'); $('indicator').classList.add('offline'); }
  finally {busy = false;if(manual)$('refresh').disabled = false;}
}
$('workspace-search').addEventListener('input',()=>{workspaceQuery=$('workspace-search').value;if(lastState)render(lastState);});
$('workspace-filter').addEventListener('change',()=>{workspaceFilter=$('workspace-filter').value;if(lastState)render(lastState);});
window.addEventListener('hashchange',()=>{if(requirementPreview.id&&requirementPreview.pageHash!==location.hash)closeRequirementPreview(false);showPage();if(lastState)render(lastState);});
// Unread acknowledgement happens after successful navigation, never on an unverified click.
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
$('refresh').addEventListener('click',()=>refresh(true));
refresh(); setInterval(refresh,5000);

function renderFiles(state,taskId){
  const records=(state.artifacts||[]).filter(item=>item.task_id===taskId);
  $('task-files').replaceChildren();$('tab-files').textContent=`${t('文件')} · ${outputSummary(state,taskId).count}`;
  if(!records.length)$('task-files').append(element('p',t('尚无已登记产出'),'empty-caption'));
  for(const item of records){const card=element('article','','file-card');card.dataset.patchKey='artifact:'+item.id;card.append(element('h3',item.title),element('small',`${t({report:'报告',image:'图片',document:'文档',data:'数据',video:'视频',other:'其他'}[item.kind]||'其他')} · ${Number(item.size).toLocaleString()} B · ${stamp(item.created)}`),element('p',PanelWorkspace.delivery(item,language),'file-delivery'),element('p',item.relative_path,'file-path'),element('small',`SHA-256 · ${item.sha256}`));$('task-files').append(card);}
}
function setDetailTab(tab){
  $('requirement-bookmarks').hidden=tab!=='timeline'||!$('requirement-bookmarks').children.length;
  detailScrollPositions[detailTab]=$('detail-scroll').scrollTop||0;detailTab=tab;
  $('timeline-panel').hidden=tab!=='timeline';$('files-panel').hidden=tab!=='files';
  if(lastState)renderConversationHeader(lastState,lastState.tasks.find(t=>t.id===$('task-filter').value));
  $('tab-timeline').setAttribute('aria-selected',String(tab==='timeline'));$('tab-files').setAttribute('aria-selected',String(tab==='files'));
  $('detail-scroll').scrollTop=detailScrollPositions[tab];
}
$('tab-timeline').addEventListener('click',()=>setDetailTab('timeline'));
$('tab-files').addEventListener('click',()=>setDetailTab('files'));
$('advice-text').addEventListener('keydown',event=>{if(event.key==='Escape'){adviceTaskId=null;$('attention-advice').hidden=true;$('back-conversations').focus();event.preventDefault();}});

$('output-summary-files').addEventListener('click',()=>{setDetailTab('files');$('tab-files').focus();});

$('detail-scroll').addEventListener('scroll',syncConversationHeader,{passive:true});
$('detail-artifacts').addEventListener('click',()=>setDetailTab(detailTab==='files'?'timeline':'files'));
$('detail-more-toggle').addEventListener('click',()=>{$('detail-more').open=!$('detail-more').open;$('detail-more-toggle').setAttribute('aria-expanded',String($('detail-more').open));if($('detail-more').open)$('detail-more').scrollIntoView?.({block:'nearest'});});
$('detail-more').addEventListener('toggle',()=>{$('detail-more-toggle').setAttribute('aria-expanded',String($('detail-more').open));});
for(const [id,key] of [['conversation-agent','agent'],['conversation-role','role'],['conversation-task','task']])$(id).addEventListener('change',()=>{conversationFilters[key]=$(id).value;conversationOffset=0;conversationRead.signature='';renderConversationStream(lastState,conversationTask);});
for(const [id,delta] of [['conversation-previous',-100],['conversation-next',100]])$(id).addEventListener('click',()=>{conversationOffset=Math.max(0,conversationOffset+delta);conversationRead.signature='';$('detail-scroll').scrollTop=0;renderConversationStream(lastState,conversationTask);});
$('collaboration-mode-filter').addEventListener('change',()=>{collaborationModeFilter=$('collaboration-mode-filter').value;render(lastState);});


function anonymousAvatar() {
  const avatar=element('span','','unattributed-avatar anonymous-avatar');avatar.setAttribute('aria-hidden','true');
  avatar.append(element('span','','anonymous-head'),element('span','','anonymous-shoulders'));return avatar;
}
function syncDetailShell(selected) {
  const detail=selected&&location.hash==='#conversations';document.body.classList.toggle('task-detail-open',detail);
}
function renderConversationFilterChips() {
  const fresh=[];
  for(const [field,id] of [['agent','conversation-agent'],['role','conversation-role'],['task','conversation-task']])if(conversationFilters[field]){
    const select=$(id),label=[...select.options].find(o=>o.value===conversationFilters[field])?.textContent||conversationFilters[field];
    const chip=element('button',label+' ×','applied-filter');chip.type='button';chip.dataset.patchKey='filter:'+field;
    chip.setAttribute('aria-label',phrase('移除筛选：','Remove filter: ')+label);
    PanelPatch.listen(chip,'click',()=>{conversationFilters[field]='';conversationOffset=0;conversationRead.signature='';renderConversationStream(lastState,conversationTask);});fresh.push(chip);
  }
  PanelPatch.children($('conversation-filter-chips'),fresh);
  $('conversation-filters-toggle').textContent=phrase('筛选','Filters')+(fresh.length?' · '+fresh.length:'');
}
$('conversation-filters-toggle').addEventListener('click',()=>{const open=$('collaboration-filters').hidden;$('collaboration-filters').hidden=!open;$('conversation-filters-toggle').setAttribute('aria-expanded',String(open));});

const patchSignatures=new Map();
function patchRegion(ids,renderSection) {
  const targets=new Map(ids.map(id=>{const fresh=$(id).cloneNode(false);fresh.__panelPreserveActions=true;return [id,fresh];})),previous=renderTargets;renderTargets=targets;
  try {renderSection();} finally {renderTargets=previous;}
  for(const [id,fresh] of targets)PanelPatch.sync($(id),fresh);
}
function textPatch(id,value) {const node=$(id),text=String(value??'');if(node.textContent!==text)node.textContent=text;}
function changedSection(key,value,update) {const signature=JSON.stringify(value);if(patchSignatures.get(key)===signature)return false;update();patchSignatures.set(key,signature);return true;}
function patchTaskCards(id,rows,state) {
  PanelPatch.children($(id),rows.length?rows.map(({task,run})=>taskCard(task,run,state)):[element('p',t('没有符合此状态的任务'),'empty-caption')]);
}
function renderIncremental(input) {
  const state={...input,current_runs:PanelWorkspace.currentRuns(input)},previous=lastState,selected=$('task-filter').value,view=captureView(selected);
  lastState=state;
  const dataKeys=['tasks','runs','latest_runs','open_runs','current_runs','agents','agent_assignments','agent_run_assignments','assignment_episodes','activity','events','progress_updates','artifacts','output_summaries','closeouts','bindings','automation_bindings','requirements','requirement_events','requirement_stream_id','companions','current_companion_scheduler_bindings'];
  const identical=[...dataKeys,'metrics','software','schedules','rules','about','recovery','timeline_window','backup','reset_events','reset_monitor_status','recovered_evidence'].every(key=>JSON.stringify(state[key])===JSON.stringify(previous[key]));
  if(identical&&!conversationRead.error)return;
  const changed=dataKeys.some(key=>JSON.stringify(state[key])!==JSON.stringify(previous[key]));
  if(JSON.stringify(state.recovered_evidence)!==JSON.stringify(previous.recovered_evidence))renderRecoveredEvidence(state);
  if(JSON.stringify(state.backup)!==JSON.stringify(previous.backup))renderBackup(state.backup);
  if(JSON.stringify(state.metrics)!==JSON.stringify(previous.metrics)){renderMetrics(state);renderMemory(state);}
  if(JSON.stringify([state.reset_events,state.reset_monitor_status])!==JSON.stringify([previous.reset_events,previous.reset_monitor_status]))renderReset(state);
  if(JSON.stringify(state.recovery)!==JSON.stringify(previous.recovery)){textPatch('recovery-notice',state.recovery?.[language==='en'?'notice_en':'notice_zh']||'');$('recovery-info').hidden=!state.recovery;}
  if(changed){
    const rows=PanelWorkspace.rows(state.tasks,state.current_runs,workspaceFilter,workspaceQuery,state).filter(({task})=>PanelCollaboration.matchesMode(task,collaborationModeFilter));
    patchTaskCards('task-list',rows,state);textPatch('task-count',rows.length);$('task-empty').hidden=rows.length>0;
    patchTaskCards('active-work',PanelWorkspace.rows(state.tasks,state.current_runs,workspaceFilter,'',state),state);renderStatusFilters(state);
    conversationSelect('task-filter',[['',t('所有任务 / 进度记录')],...state.tasks.map(t=>[t.id,t.name])],selected);
    const task=state.tasks.find(t=>t.id===selected),run=task?PanelWorkspace.runSelection(state,selected).current:null;
    if(selected&&!task){$('task-filter').value='';$('conversation-detail').hidden=true;$('conversation-list').hidden=false;syncDetailShell(false);}
    if(task){
      textPatch('selected-task-title',task.name);textPatch('detail-status',t(statuses[run?.status||task.latest_status||'pending']));
      textPatch('detail-updated',`${t('最近更新')} ${stamp(meaningfulTaskTime(state,task,run))}`);
      renderConversationHeader(state,task);
      changedSection('files:'+selected,[state.artifacts,state.output_summaries],()=>patchRegion(['task-files'],()=>renderFiles(state,selected)));
      changedSection('participants:'+selected,[state.agents,state.assignment_episodes,state.agent_run_assignments,state.current_runs],()=>patchRegion(['task-participants'],()=>renderTaskParticipants(state,selected)));
      patchRegion(['task-agent','task-lifecycle-meta','session-binding'],()=>renderDetailMetadata(state,task,run,selected));
      renderAdvice(task,run);
      patchRegion(['closeout-summary','closeout-pinned'],()=>renderCloseout(run,state));renderOutputBar(state,selected);
      patchRegion(['events'],()=>renderRawEvents(state,selected));
      patchRegion(['pipeline','progress-summary'],()=>renderProgressMetadata(state,selected));
      if(conversationRead.error)conversationRead.signature='';renderConversationStream(state,selected);
    }
  }else if(conversationRead.error&&selected){conversationRead.signature='';renderConversationStream(state,selected);}
  if(JSON.stringify(state.software)!==JSON.stringify(previous.software))patchRegion(['software-cards'],()=>renderSoftware(state));
  if(JSON.stringify([state.schedules,state.current_companion_scheduler_bindings])!==JSON.stringify([previous.schedules,previous.current_companion_scheduler_bindings]))patchRegion(['schedule-cards','schedule-summary','automation-info-content'],()=>renderSchedules(state.schedules||[]));
  if(JSON.stringify(state.rules)!==JSON.stringify(previous.rules))patchRegion(['rules-content'],()=>renderRules(state.rules));
  if(JSON.stringify(state.about)!==JSON.stringify(previous.about))patchRegion(['about-rows','about-repository','about-notes','about-doctor'],()=>renderAbout(state.about));
  restoreView(view,selected);renderRequirementPreview(state);panelNotifications?.observe(state);
}


function bundledBadge(){return element('span',phrase('◆ Panel 配套','◆ Panel bundled'),'panel-bundled');}
function schedulerBundled(schedule,state={}){
  if(state?.current_companion_scheduler_bindings!=null)return state.current_companion_scheduler_bindings.some(row=>row.explicit_current_binding===true&&row.status==='verified'&&row.reference===schedule.platform_observation?.task_id&&Boolean(row.source_reference));
  let rows=state?.installation_observations;
  if(!rows)rows=Object.entries(state?.about?.doctor?.observations||{}).map(([component,row])=>({...row,component}));
  if(!Array.isArray(rows))rows=Object.values(rows);
  const latest=rows.filter(row=>row.component==='scheduler_configuration').sort((a,b)=>(b.observed_at||0)-(a.observed_at||0)||(b.id||0)-(a.id||0))[0];
  return Boolean(latest?.status==='verified'&&typeof latest.reference==='string'&&latest.reference.trim()&&latest.reference===schedule.platform_observation?.task_id);
}
function executionConfigLabel(config={}){
  if(!config)config={};
  const requested=config.requested_model&&config.requested_model!=='unknown'?config.requested_model+' / '+(config.requested_effort||'unknown'):phrase('未知','Unknown');
  const actual=config.config_verification==='verified'&&config.actual_model&&config.actual_model!=='unknown'?config.actual_model+' / '+(config.actual_effort||'unknown'):phrase('未知','Unknown');
  return phrase('请求：','Requested: ')+requested+' · '+phrase('实际观测：','Observed: ')+actual;
}
function meaningfulTaskTime(state,task,run){
  const work=PanelWorkspace.workProgress(state,task.id,run);
  return work.update?.created||work.latest?.created||run?.started||task.created;
}
function requirementStatus(value){return ({received:['已接收','Received'],in_progress:['进行中','In progress'],blocked:['受阻','Blocked'],pending_acceptance:['待验收','Pending acceptance'],completed:['已完成','Completed'],cancelled:['已取消','Cancelled']}[value]||[value||'未知',value||'Unknown'])[language==='en'?1:0];}
function requirementOwner(q){const owner=q.owner||{};return owner.status==='confirmed'?(language==='en'?owner.name_en||owner.name:owner.name)||phrase('未知','Unknown'):phrase('负责人待确认','Owner unconfirmed');}
function requirementWork(q){const latest=[...(q.status_history||[])].sort((a,b)=>(b.observed_at||0)-(a.observed_at||0)||(b.id||0)-(a.id||0))[0]||{};return q.current_step||latest.next_step||(['in_progress','blocked'].includes(latest.status)?latest.evidence:'')||phrase('尚未登记','Not recorded');}
function requirementCard(q,event={}){
  const card=element('article','','requirement-card');card.dataset.timelineKey='requirement:'+q.id;card.dataset.patchKey='requirement:'+q.id;card.dataset.requirementId=q.id;
  const heading=element('div','','requirement-heading');heading.append(element('strong',phrase('◆ 需求','◆ Requirement')),element('time',stamp(q.observed_at??event.created)));card.append(heading,element('h3',q.summary||event.message||''),element('p',requirementStatus(q.status)+' · '+requirementOwner(q),'requirement-facts'),element('p',phrase('当前执行：','Current work: ')+requirementWork(q),'requirement-work'),element('small',executionConfigLabel(q.owner),'execution-config'));
  const history=disclosure(element('details','','requirement-history'),expandedRequirements,'requirement:'+q.id);const summary=element('summary',phrase('状态与负责人历史','State and owner history'));summary.dataset.focusKey='requirement-history:'+q.id;history.append(summary);
  for(const row of q.history||[]){const text=row.kind==='owner'?requirementOwner({owner:row.owner})+' · '+executionConfigLabel(row.owner):row.kind==='link'?[row.link_kind,row.target_type,row.target_id].filter(Boolean).join(' · '):requirementStatus(row.status);history.append(element('p',stamp(row.observed_at)+' · '+text+' · '+(row.evidence||'')));}
  history.append(element('small',phrase('来源：','Source: ')+(q.source_event_id||phrase('未知','Unknown'))));card.append(history);return card;
}
function renderRequirementBookmarks(state,taskId){
  const ids=PanelCollaboration.scope(state,taskId);const all=(state.requirements||[]).filter(q=>ids.has(q.task_id)),open=all.filter(q=>!['completed','cancelled'].includes(q.status)),area=$('requirement-bookmarks');
  const pills=open.map((q,i)=>{const button=element('button',(i+1)+' · '+q.summary,'requirement-bookmark');button.type='button';button.dataset.patchKey=q.id;button.dataset.focusKey='bookmark:'+q.id;button.title=q.summary+' · '+requirementStatus(q.status)+' · '+requirementOwner(q);PanelPatch.listen(button,'click',()=>openRequirement(q.id).catch(()=>{}));return button;});PanelPatch.children(area,pills);area.hidden=!open.length||detailTab!=='timeline';
  $('requirement-all').hidden=!all.length;$('requirement-all-title').textContent=phrase('全部需求','All requirements')+' · '+all.length;
  const rows=all.map(q=>{const button=element('button',q.summary+' · '+requirementStatus(q.status),'requirement-list-item');button.type='button';button.dataset.patchKey=q.id;PanelPatch.listen(button,'click',()=>openRequirement(q.id).catch(()=>{}));return button;});PanelPatch.children($('requirement-all-list'),rows);
}
function renderRequirementPreview(state){
  if(!requirementPreview.id)return;
  const q=(state.requirements||[]).find(q=>q.id===requirementPreview.id);if(!q)return;
  const area=$('requirement-preview-content'),card=requirementCard(q,{created:q.observed_at});card.dataset.timelineKey='preview:'+q.id;
  PanelPatch.children(area,[card]);$('requirement-preview-title').textContent=phrase('需求详情','Requirement preview');$('requirement-preview-close').textContent=phrase('关闭 ×','Close ×');
}
function closeRequirementPreview(restoreFocus=true){
  const previous=requirementPreview.returnFocus;$('requirement-preview').hidden=true;requirementPreview={id:null,returnFocus:null};
  if(restoreFocus&&previous?.focus)previous.focus({preventScroll:true});
}
async function openRequirement(id,{preserveView=true}={}){
  const error=$('requirement-navigation-error');
  try{
    let q=lastState?.requirements?.find(q=>q.id===id);if(!q)throw Error('missing');
    if(!preserveView&&(location.hash!=='#conversations'||$('task-filter').value!==q.task_id||!lastState.tasks.some(task=>task.id===q.task_id))){
      const epoch=++stateReadEpoch;stateNavigationPending=true;
      try{
        const response=await fetch('/api/state?task_id='+encodeURIComponent(q.task_id),{cache:'no-store',signal:AbortSignal.timeout(5000)});
        if(!response.ok)throw Error('selected-read');const selected=await response.json();if(epoch!==stateReadEpoch)throw Error('superseded');
        const task=selected.tasks?.find(task=>task.id===q.task_id);q=selected.requirements?.find(item=>item.id===id);if(!task||!q)throw Error('selected-missing');
        render(selected,true);selectTask(task);
      }finally{if(epoch===stateReadEpoch)stateNavigationPending=false;}
    }
    const previous=requirementPreview.id?requirementPreview.returnFocus:document.activeElement;
    requirementPreview={id,returnFocus:previous,pageHash:location.hash};renderRequirementPreview(lastState);
    const preview=$('requirement-preview');preview.hidden=false;
    if(preview.getBoundingClientRect&&preview.getBoundingClientRect().height===0)throw Error('not-visible');
    $('requirement-preview-close').focus({preventScroll:true});error.hidden=true;panelNotifications?.markRead('conversations',q.task_id,id);
    return true;
  }catch(exc){error.textContent=phrase('需求未能显示，未读状态已保留；请重试','Requirement could not be shown; unread state retained. Please retry');error.hidden=false;throw exc;}
}
function memoryBytes(value){if(value==null)return phrase('未知','Unknown');for(const [unit,scale] of [['GiB',2**30],['MiB',2**20],['KiB',2**10]])if(value>=scale)return (value/scale).toFixed(1)+' '+unit;return value+' B';}
function renderMemory(state){
  const m=state.metrics||{},p=m.process_memory||{},en=language==='en',limit=m.memory_quota_state==='unlimited'?phrase('无限制','Unlimited'):memoryBytes(m.memory_quota);
  $('memory-boundary').textContent=phrase('系统、容器与进程独立观测；进程 RSS 不可直接相加。仅读取 /proc 数字目录 status 的 Name/VmRSS，不猜任务归属，不提供进程控制。','System, container and process scopes are separate. Process RSS is not additive. Only Name/VmRSS from numeric /proc status files; no inferred task ownership or process controls.');
  const facts=[phrase('系统总量 / 可用：','System total / available: ')+memoryBytes(m.memory_total)+' / '+memoryBytes(m.memory_available),phrase('cgroup 当前 / 上限：','cgroup current / limit: ')+memoryBytes(m.cgroup_memory_current)+' / '+limit,phrase('进程采样：','Process sample: ')+(p.status||'unavailable')+' · '+stamp(p.sampled_at),phrase('最近尝试：','Last attempted: ')+stamp(p.attempted_at),phrase('可见 / 可读 / 不可读 / 已退出：','Visible / readable / unreadable / exited: ')+['visible_count','readable_count','unreadable_count','exited_count'].map(key=>p[key]??'—').join(' / '),'Scope: sampler_visible_processes',p.error||''];
  PanelPatch.children($('memory-facts'),facts.map((text,i)=>{const node=element('p',text);node.dataset.patchKey='memory:'+i;return node;}));
  const order=$('memory-sort').value||'rss_desc',rows=[...(p.rows||[])].sort((a,b)=>order==='name'?String(a.name).localeCompare(String(b.name))||a.pid-b.pid:order==='pid'?a.pid-b.pid:((order==='rss_asc'?1:-1)*(a.rss_bytes-b.rss_bytes)||a.pid-b.pid));
  PanelPatch.children($('memory-process-rows'),rows.map(row=>{const tr=element('tr','');tr.dataset.patchKey=String(row.pid);for(const text of [row.pid,row.name,memoryBytes(row.rss_bytes),phrase('未知','Unknown')])tr.append(element('td',String(text)));return tr;}));
  $('memory-name-head').textContent=phrase('进程名','Name');$('memory-task-head').textContent=phrase('任务归属','Task attribution');$('memory-sort-label').textContent=phrase('排序','Sort');$('memory-empty').textContent=rows.length?'':phrase('当前没有可用的进程采样','No process sample is currently available');
}
function renderReset(state){
  $('reset-monitor-title').textContent=phrase('重置观察器','Reset observer');
  $('reset-monitor-title').parentElement?.querySelector('.panel-bundled')?.replaceWith(bundledBadge());
  $('reset-boundary').textContent=phrase('仅观察明确选择的固定组件。UTC 参考时间与北京时间表示同一时刻，不是 OpenAI 官方当地时间。每 60 秒本地采样不保证进程常驻，也不是平台每分钟定时任务；计划时间不等于实际观察。','Observes explicitly selected fixed components only. UTC reference time and Beijing time represent the same instant, not an official OpenAI local timezone. Local 60-second sampling does not guarantee persistence or a platform minutely schedule; planned time is not an actual observation.');
  $('reset-monitor-status').textContent=phrase('观察器状态：','Observer status: ')+(typeof state.reset_monitor_status==='string'?state.reset_monitor_status:state.reset_monitor_status?.status||'unknown');
  const eventNames={baseline_present:['基线存在','Baseline present'],initial_absent:['首次观察即缺失','Initially absent'],path_missing:['组件缺失','Component missing'],identity_changed:['组件身份变化','Identity changed'],path_reappeared:['重新出现','Component reappeared'],observation_gap:['观察缺口','Observation gap'],clock_rollback:['时钟回退','Clock rollback'],inspection_error:['检查失败','Inspection error'],historical_estimate:['历史估算','Historical estimate']};
  const fieldNames={observed_at_utc:['UTC 观察时间','Observed at · UTC'],observed_at_beijing:['北京观察时间','Observed at · Beijing'],last_present_at_utc:['最后存在 · UTC','Last present · UTC'],first_missing_at_utc:['首次缺失 · UTC','First missing · UTC'],evidence_level:['证据等级','Evidence level'],source_kind:['来源类别','Source kind']};
  const rows=(state.reset_events||[]).map(row=>{const card=element('article','','reset-event');card.dataset.patchKey='reset:'+(row.event_id||row.id);card.append(element('h3',(eventNames[row.event_type]||[row.event_type||'未知',row.event_type||'Unknown'])[language==='en'?1:0]),element('p',row.summary||''));for(const field of ['observed_at_utc','observed_at_beijing','last_present_at_utc','first_missing_at_utc','evidence_level','source_kind'])card.append(element('p',fieldNames[field][language==='en'?1:0]+': '+(field==='evidence_level'&&language==='zh'?({observed:'已观察',estimated:'估算',unknown:'未知'}[row[field]]||row[field]||'未知'):(row[field]??phrase('未知','Unknown')))));return card;});
  PanelPatch.children($('reset-events'),rows.length?rows:[element('p',phrase('尚无重置观察事件；这不证明从未发生重置','No reset observation events recorded; this does not prove that no reset occurred'),'empty-caption')]);
}

$('memory-sort').addEventListener('change',()=>{if(lastState)renderMemory(lastState);});

function renderRecoveredEvidence(state){
  const data=state.recovered_evidence||{},events=data.events||[];
  $('recovered-evidence-title').textContent=phrase('证据补录历史','Evidence-supplemented history')+' · '+events.length;
  $('recovered-evidence-note').textContent=phrase('原字节基线保留 15 个任务。后续事实是证据补录，不代表原记录完整恢复；未知 task/run 不推测归属。助手报告不等于用户验收。基线截止：','The original byte-level baseline contains 15 tasks. Later facts are evidence supplements, not complete original history. Unknown task/run mappings remain unknown. Assistant reports are not user acceptance. Baseline cutoff: ')+(data.baseline_cutoff_utc||'unknown');
  PanelPatch.children($('recovered-evidence-list'),events.map(row=>{const card=element('article','','reset-event');card.dataset.patchKey=row.evidence_id;card.append(element('h3',row.topic||''),element('p',row.fact_summary||''));for(const field of ['source_observed_at_utc','source_observed_at_beijing','evidence_level','remaining_unknown','known_original_task_id','known_original_run_id'])card.append(element('p',field+': '+(field==='evidence_level'?({user_instruction:phrase('用户指令','User instruction'),assistant_report:phrase('助手报告（非用户验收）','Assistant report (not acceptance)')}[row[field]]||row[field]||'unknown'):(row[field]??'unknown'))));return card;}));
}

$('conversation-new').addEventListener('click',()=>{if(!conversationRead.pending)return;conversationRead.data=conversationRead.pending;conversationRead.pending=null;$('conversation-new').hidden=true;const view=captureView(conversationTask);renderConversationStream(lastState,conversationTask);restoreView(view,conversationTask);});

$('requirement-preview-close').addEventListener('click',()=>closeRequirementPreview());
$('requirement-preview').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeRequirementPreview();}});
