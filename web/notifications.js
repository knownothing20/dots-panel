'use strict';
/* Persisted viewer observations; no network, task writes, or replay on refresh. */
(() => {
  const categories=['conversations','agents','schedules','about'];
  const open=new Set(['running','waiting_user','waiting_external','paused','awaiting_review']);
  const remember=(map,key,value=true)=>{map.set(key,value);const legacy=[...map.keys()].filter(k=>!String(k).startsWith('requirement:'));for(const retired of legacy.slice(0,Math.max(0,legacy.length-2000)))map.delete(retired);};
  function normalizeCards(cards){if(!Array.isArray(cards)||cards.some(card=>!card||typeof card!=='object'||typeof card.id!=='string'))throw Error('Invalid saved notification cards');let legacy=0;return cards.filter(card=>card.kind==='requirement'||card.id.startsWith('requirement:')||legacy++<50);}
  // Protect the complete current snapshot; bound only retired history after iteration.
  function pruneHistory(map,visible){const retired=[...map.keys()].filter(key=>!visible.has(key));for(const key of retired.slice(0,Math.max(0,retired.length-2000)))map.delete(key);}
  function version(value){const m=typeof value==='string'&&/^v?(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})(?:\+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?$/.exec(value);return m?m.slice(1).map(Number):null;}
  function newerRelease(about={}){const r=about.release||{},a=version(about.installed_version),b=version(r.release_tag);if(r.release_status!=='published'||!a||!b)return false;for(let i=0;i<3;i++){if(b[i]!==a[i])return b[i]>a[i];}return false;}
  function scheduleIdentity(item){const latest=item.external_result?.observation?.latest;if(latest?.run_id)return JSON.stringify(['result',String(latest.run_id),String(latest.status||'')]);const last=item.platform_observation?.last_run_at;return last?JSON.stringify(['platform',String(last)]):null;}
  class Storage {
    constructor(storage=null,key='dots-panel.notifications.v1'){this.storage=storage;this.key=key;this.persistence='persistent';this.error=null;this.invalidSavedState=false;if(!this.storage){try{this.storage=globalThis.localStorage;if(!this.storage)throw Error('Local storage unavailable');}catch(error){this.fail(error);}}}
    fail(error){this.persistence='session_only';this.error='Notification storage unavailable; session-only unread state: '+String(error?.message||error);}
    load(){if(this.persistence==='session_only')return null;try{const raw=this.storage.getItem(this.key);if(!raw)return null;let value;try{value=JSON.parse(raw);if(!value||value.version!==1)throw Error('Invalid notification state');}catch(error){this.invalidSavedState=true;throw error;}return value;}catch(error){this.invalidSavedState=true;this.fail(error);return null;}}
    save(value){if(this.invalidSavedState||!this.storage)return false;try{this.storage.setItem(this.key,JSON.stringify(value));this.persistence='persistent';this.error=null;return true;}catch(error){this.fail(error);return false;}}
  }
  class State {
    constructor(storage=null){this.storage=storage;this.initialized=false;this.seenRuns=new Map();this.announcedRuns=new Map();this.agentStates=new Map();this.scheduleStates=new Map();this.releaseKey=null;this.unread=Object.fromEntries(categories.map(k=>[k,new Map()]));this.cards=[];this.requirementStreamId=null;this.requirementStates=new Map();this.requirementCounters={};this.requirementEventSignatures={};const saved=storage?.load();if(saved){try{for(const field of ['seenRuns','announcedRuns','agentStates','scheduleStates','requirementStates'])this[field]=new Map(saved[field]||[]);this.unread=Object.fromEntries(categories.map(k=>[k,new Map(saved.unread?.[k]||[])]));this.cards=normalizeCards(saved.cards||[]);this.initialized=!!saved.initialized;this.releaseKey=saved.releaseKey||null;this.requirementStreamId=saved.requirementStreamId;this.requirementCounters=saved.requirementCounters||{};this.requirementEventSignatures=saved.requirementEventSignatures||{};}catch(error){storage.invalidSavedState=true;storage.fail(error);Object.assign(this,new State());this.storage=storage;}}}
    get persistence(){return this.storage?.persistence||'session_only';}
    get storage_error(){return this.storage?.error||null;}
    save(){if(!this.storage)return;this.storage.save({version:1,initialized:this.initialized,releaseKey:this.releaseKey,cards:this.cards,requirementStreamId:this.requirementStreamId,requirementCounters:this.requirementCounters,requirementEventSignatures:this.requirementEventSignatures,...Object.fromEntries(['seenRuns','announcedRuns','agentStates','scheduleStates','requirementStates'].map(field=>[field,[...this[field]]])),unread:Object.fromEntries(categories.map(k=>[k,[...this.unread[k]]]))});}
    requirements(snapshot){
      const stream=snapshot.requirement_stream_id;if(stream==null)return {baseline:false,cards:[],content_changed:false};const events=snapshot.requirement_events||[],signatures=Object.fromEntries(events.filter(e=>e.id!=null).map(e=>[String(e.id),JSON.stringify(e)])),counters=snapshot.requirement_counters||Object.fromEntries(['receipt','state','owner','link'].map(kind=>[kind,Math.max(0,...events.filter(e=>e.kind===kind).map(e=>Number(e.id)))]));
      const reset=stream!==this.requirementStreamId||Object.entries(this.requirementCounters).some(([k,v])=>(counters[k]||0)<v)||Object.entries(this.requirementEventSignatures).some(([k,v])=>signatures[k]!==v),baseline=reset||!this.initialized,added=[];let contentChanged=false;
      if(reset){this.requirementStates.clear();this.cards=this.cards.filter(c=>c.kind!=='requirement');for(const key of this.unread.conversations.keys())if(key.startsWith('requirement:'))this.unread.conversations.delete(key);}
      for(const req of snapshot.requirements||[]){const key='requirement:'+req.id,identity=JSON.stringify([req.source_event_id,req.current_event_id||0,req.current_owner_event_id||0]),owner=req.owner||{},card={id:key,kind:'requirement',requirement_id:req.id,task_id:req.task_id,title:String(req.summary||'').slice(0,160),status:req.status||'received',agent:owner.name||'Unknown',avatar:'mint',participants:1,owner,agent_record:Object.fromEntries(['name','name_en','portrait'].filter(k=>owner[k]).map(k=>[k,owner[k]]))};const existing=this.cards.find(c=>c.id===key);if(existing&&JSON.stringify(existing)!==JSON.stringify(card)){Object.assign(existing,card);contentChanged=true;}if(!baseline&&this.requirementStates.get(key)!==identity){this.unread.conversations.set(key,req.task_id);this.cards=this.cards.filter(c=>c.id!==key);this.cards.unshift(card);this.cards=normalizeCards(this.cards);added.push(card);}this.requirementStates.set(key,identity);}
      this.requirementStreamId=stream;this.requirementCounters=counters;this.requirementEventSignatures=signatures;return {baseline,cards:added,content_changed:contentChanged};
    }
    counts(){return Object.fromEntries(categories.map(k=>[k,this.unread[k].size]));}
    clear(category,taskId=null,requirementId=null){if(!this.unread[category])return;if(category==='conversations'){const keys=requirementId!=null?['requirement:'+requirementId]:[...this.unread.conversations].filter(([key,id])=>!key.startsWith('requirement:')&&(taskId==null||id===taskId)).map(([key])=>key);for(const key of keys)this.unread.conversations.delete(key);this.cards=this.cards.filter(c=>!keys.includes(c.id));}else this.unread[category].clear();this.save();}
    update(snapshot={}){
      const requirementResult=this.requirements(snapshot),linkedRuns=new Set((snapshot.requirements||[]).flatMap(r=>r.run_ids||[]));
      const runs=new Map();for(const key of ['runs','latest_runs','open_runs','current_runs'])for(const r of snapshot[key]||[])if(r.id)runs.set(r.id,r);
      const tasks=new Map((snapshot.tasks||[]).filter(t=>t.id).map(t=>[t.id,t])),agents=new Map((snapshot.agents||[]).filter(a=>a.id).map(a=>[a.id,a]));
      const assignments=new Map();for(const a of snapshot.agent_run_assignments||[])if(agents.has(a.agent_id)&&runs.has(a.run_id)){if(!assignments.has(a.run_id))assignments.set(a.run_id,[]);assignments.get(a.run_id).push(agents.get(a.agent_id));}
      const changed=new Set(),added=[...requirementResult.cards],baseline=!this.initialized||requirementResult.baseline;let contentChanged=requirementResult.content_changed;if(added.length)changed.add('conversations');
      for(const [key,run] of runs)if(!this.seenRuns.has(key)){this.seenRuns.set(key,true);if(!baseline&&!linkedRuns.has(key)){remember(this.unread.conversations,key,run.task_id);changed.add('conversations');}}
      for(const [key,people] of assignments){
        const run=runs.get(key),taskId=run.task_id,person=people[0];const card={id:key,task_id:taskId,title:String(tasks.get(taskId)?.name||taskId||'').slice(0,160),agent:String(person.name||person.id||'').slice(0,80),avatar:person.avatar||'mint',participants:people.length,agent_record:Object.fromEntries(['id','name','name_en','avatar','portrait','portrait_spec'].filter(key=>key in person).map(key=>[key,person[key]]))};
        if(this.announcedRuns.has(key)){const existing=this.cards.find(item=>item.id===key);if(existing&&JSON.stringify(existing)!==JSON.stringify(card)){Object.assign(existing,card);contentChanged=true;}continue;}
        this.announcedRuns.set(key,true);if(baseline||linkedRuns.has(key)||!open.has(run.status))continue;remember(this.unread.conversations,key,taskId);this.cards.unshift(card);this.cards=normalizeCards(this.cards);added.push(card);changed.add('conversations');
      }
      for(const [key,person] of agents){const status=person.status||'unknown';if(this.agentStates.get(key)!==status){if(!baseline){remember(this.unread.agents,key);changed.add('agents');}this.agentStates.set(key,status);}}
      for(const item of snapshot.schedules||[]){const key=item.id,identity=scheduleIdentity(item);if(key&&identity&&this.scheduleStates.get(key)!==identity){if(!baseline){remember(this.unread.schedules,key);changed.add('schedules');}this.scheduleStates.set(key,identity);}}
      pruneHistory(this.seenRuns,runs);pruneHistory(this.announcedRuns,assignments);pruneHistory(this.agentStates,agents);pruneHistory(this.scheduleStates,new Set((snapshot.schedules||[]).filter(scheduleIdentity).map(item=>item.id)));
      const about=snapshot.about||{},key=newerRelease(about)?about.release.release_tag:null;if(key!==this.releaseKey){this.releaseKey=key;this.unread.about.clear();if(key){this.unread.about.set(key,true);if(!baseline)changed.add('about');}}
      this.initialized=true;this.save();return {changed,cards:added,baseline,content_changed:contentChanged};
    }
  }
  class Deadline {
    constructor(now=()=>performance.now()){this.now=now;this.remaining=0;this.started=null;this.paused=false;}
    reset(ms=5000){this.remaining=ms;this.started=this.paused?null:this.now();}
    pause(value){if(value===this.paused)return;if(value&&this.started!==null){this.remaining=Math.max(0,this.remaining-(this.now()-this.started));this.started=null;}else if(!value)this.started=this.now();this.paused=value;}
    left(){return this.started===null?this.remaining:Math.max(0,this.remaining-(this.now()-this.started));}
  }
  class Controller {
    constructor({document:doc,language,openTask,avatar,storage}){
      this.doc=doc;this.language=language;this.openTask=openTask;this.avatarFactory=avatar;this.state=new State(storage===undefined?new Storage():storage);this.deadline=new Deadline();this.expanded=false;this.closing=false;this.hover=false;this.keyboard=false;this.returnFocus=null;this.timer=null;this.hideTimer=null;this.pulses=new Map();
      const el=(tag,cls,text='')=>{const e=doc.createElement(tag);e.className=cls;e.textContent=text;return e;};
      this.host=el('section','notification-layer');this.host.hidden=true;this.host.setAttribute('aria-label','Task notifications');this.host.dataset.expanded='false';this.host.dataset.inputMode='pointer';
      this.shell=el('div','notification-card');this.face=el('span','notification-avatar');this.face.setAttribute('aria-hidden','true');
      this.kicker=el('p','notification-kicker');this.title=el('strong','notification-title');this.owner=el('p','notification-owner');this.body=el('div','notification-copy');this.body.append(this.kicker,this.title,this.owner);
      this.close=el('button','notification-close','×');this.close.type='button';this.close.addEventListener('click',()=>this.collapse());
      this.action=el('button','notification-action');this.action.type='button';this.action.addEventListener('click',()=>{const card=this.state.cards[0];if(card){const keyboard=this.keyboard;try{const result=this.openTask(card.task_id,{keyboard,requirementId:card.requirement_id});const finish=visible=>{if(visible!==true)return;this.markRead('conversations',card.task_id,card.requirement_id);if(this.state.cards.length&&this.expanded){this.deadline.reset();this.syncPause();}};if(result&&typeof result.then==='function')result.then(finish).catch(error=>{this.live.textContent=this.phrase('无法打开需求，保留未读','Unable to open requirement; kept unread');this.hint.hidden=false;this.hint.textContent=this.live.textContent;});else finish(result);}catch(error){this.live.textContent=this.phrase('无法打开需求，保留未读','Unable to open requirement; kept unread');this.hint.hidden=false;this.hint.textContent=this.live.textContent;}}});
      this.more=el('button','notification-more');this.more.type='button';this.more.addEventListener('click',()=>{if(this.state.cards.length>1){this.state.cards.push(this.state.cards.shift());this.deadline.reset();this.render();this.syncPause();}});
      this.hint=el('p','notification-hint');this.shell.append(this.face,this.body,this.close,this.action,this.more,this.hint);
      this.live=el('span','visually-hidden');this.live.setAttribute('role','status');this.live.setAttribute('aria-live','polite');this.live.setAttribute('aria-atomic','true');this.host.append(this.shell,this.live);doc.body.append(this.host);
      this.pointerInput=()=>{this.keyboard=false;this.host.dataset.inputMode='pointer';this.syncPause();};
      this.keyboardInput=()=>{this.keyboard=true;this.host.dataset.inputMode='keyboard';this.syncPause();};
      doc.addEventListener('pointerdown',this.pointerInput,true);doc.addEventListener('keydown',this.keyboardInput,true);
      this.host.addEventListener('mouseenter',()=>{this.hover=true;this.syncPause();});this.host.addEventListener('mouseleave',()=>{this.hover=false;this.syncPause();});
      this.host.addEventListener('focusin',()=>this.syncPause());this.host.addEventListener('focusout',()=>{clearTimeout(this.focusTimer);this.focusTimer=setTimeout(()=>this.syncPause(),0);});
      this.host.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();this.keyboardInput();this.collapse();}});
    }
    phrase(zh,en){return this.language()==='en'?en:zh;}
    reduced(){return this.doc.documentElement.dataset.reducedMotion==='true'||globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches;}
    arm(){clearTimeout(this.timer);this.timer=null;if(this.expanded&&!this.deadline.paused)this.timer=setTimeout(()=>this.collapse(),Math.max(1,this.deadline.left()));}
    syncPause(){if(!this.expanded)return;this.deadline.pause(this.hover||(this.keyboard&&this.host.contains(this.doc.activeElement)));this.arm();}
    expand(){if(!this.state.cards.length)return;clearTimeout(this.hideTimer);this.hideTimer=null;if(!this.host.contains(this.doc.activeElement))this.returnFocus=this.doc.activeElement;this.closing=false;this.expanded=true;this.deadline.reset();this.render();this.syncPause();}
    collapse(){
      if(!this.expanded)return;const restore=this.keyboard&&this.host.contains(this.doc.activeElement);this.expanded=false;this.closing=!this.reduced();clearTimeout(this.timer);this.timer=null;this.render();
      if(restore){const target=this.returnFocus?.isConnected!==false?this.returnFocus:null;(target||this.doc.querySelector('[data-nav="conversations"]'))?.focus({preventScroll:true});}
      clearTimeout(this.hideTimer);this.hideTimer=null;if(this.closing)this.hideTimer=setTimeout(()=>{this.hideTimer=null;this.closing=false;this.render();},280);
    }
    observe(snapshot){const result=this.state.update(snapshot);this.badges(result.changed);if(result.cards.length){this.live.textContent=this.phrase(`新分派 ${result.cards.length} 项任务，${result.cards[0].title}`,`${result.cards.length} newly assigned tasks. ${result.cards[0].title}`);this.expand();}else this.render();return result;}
    markRead(page,taskId=null,requirementId=null){this.state.clear(page,taskId,requirementId);if(!this.state.cards.length){this.expanded=false;this.closing=false;clearTimeout(this.timer);clearTimeout(this.hideTimer);this.timer=null;this.hideTimer=null;}this.badges();this.render();}
    badges(changed=new Set()){
      const counts=this.state.counts();for(const page of categories){const nav=this.doc.querySelector(`[data-nav="${page}"]`);if(!nav)continue;let badge=nav.querySelector('.notification-badge');if(!badge){badge=this.doc.createElement('span');badge.className='notification-badge';badge.dataset.kind=page;nav.append(badge);}badge.hidden=!counts[page];badge.textContent=page==='about'?'NEW':'';badge.setAttribute('aria-label',this.phrase('有未读更新','Unread updates'));if(changed.has(page)&&page!=='about'&&!this.reduced()){badge.classList.remove('notification-pulse');void badge.offsetWidth;badge.classList.add('notification-pulse');clearTimeout(this.pulses.get(page));this.pulses.set(page,setTimeout(()=>{badge.classList.remove('notification-pulse');this.pulses.delete(page);},400));}}
    }
    render(){
      const count=this.state.cards.length;this.host.hidden=!count||(!this.expanded&&!this.closing);this.host.dataset.expanded=String(this.expanded);this.shell.setAttribute('aria-hidden',String(!this.expanded));this.shell.inert=!this.expanded;if(!count||this.host.hidden)return;
      const card=this.state.cards[0],agent=card.agent_record||{avatar:card.avatar};this.host.classList.toggle('notification-stacked',count>1);
      const portraitKey=JSON.stringify([agent.id,agent.portrait,agent.portrait_spec]);if(this.portraitKey!==portraitKey){this.portraitKey=portraitKey;this.face.replaceChildren();if(this.avatarFactory)this.face.append(this.avatarFactory(agent));}
      this.host.setAttribute('aria-label',this.phrase('任务通知','Task notifications'));this.kicker.textContent=card.kind==='requirement'?this.phrase('需求更新 · ','Requirement update · ')+card.status:this.phrase('新的任务已分派','Task assigned');this.title.textContent=card.title;this.title.title=card.title;this.owner.textContent=(card.kind==='requirement'?this.phrase('负责人 · ','Owner · '):this.phrase('已登记分派 · ','Assigned · '))+(this.language()==='en'&&agent.name_en?agent.name_en:card.agent)+(card.participants>1?' +'+(card.participants-1):'');this.close.setAttribute('aria-label',this.phrase('隐藏通知，保留未读','Hide notification, keep unread'));this.action.textContent=this.phrase('查看进度 →','View progress →');this.more.hidden=count<2;this.more.textContent=this.phrase(`另有 ${count-1} 条 · 下一条`,`+${count-1} more · next`);this.hint.hidden=count>1;this.hint.textContent=this.state.storage_error||this.phrase('约 5 秒后隐藏 · 悬停 / 键盘焦点暂停','Hides after 5s · hover / keyboard focus to pause');if(this.state.storage_error)this.hint.hidden=false;
    }
    destroy(){clearTimeout(this.timer);clearTimeout(this.hideTimer);clearTimeout(this.focusTimer);for(const timer of this.pulses.values())clearTimeout(timer);this.pulses.clear();this.doc.removeEventListener('pointerdown',this.pointerInput,true);this.doc.removeEventListener('keydown',this.keyboardInput,true);this.host.remove();}
  }
  globalThis.PanelNotifications={State,Storage,Deadline,Controller,newerRelease,scheduleIdentity};
})();
