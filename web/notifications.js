'use strict';
/* Session-local notification observations; no network, task writes, or replay on refresh. */
(() => {
  const categories=['conversations','agents','schedules','about'];
  const open=new Set(['running','waiting_user','waiting_external','paused','awaiting_review']);
  const remember=(map,key,value=true)=>{map.set(key,value);while(map.size>2000)map.delete(map.keys().next().value);};
  // Protect the complete current snapshot; bound only retired history after iteration.
  function pruneHistory(map,visible){const retired=[...map.keys()].filter(key=>!visible.has(key));for(const key of retired.slice(0,Math.max(0,retired.length-2000)))map.delete(key);}
  function version(value){const m=typeof value==='string'&&/^v?(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})(?:\+[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*)?$/.exec(value);return m?m.slice(1).map(Number):null;}
  function newerRelease(about={}){const r=about.release||{},a=version(about.installed_version),b=version(r.release_tag);if(r.release_status!=='published'||!a||!b)return false;for(let i=0;i<3;i++){if(b[i]!==a[i])return b[i]>a[i];}return false;}
  function scheduleIdentity(item){const latest=item.external_result?.observation?.latest;if(latest?.run_id)return JSON.stringify(['result',String(latest.run_id),String(latest.status||'')]);const last=item.platform_observation?.last_run_at;return last?JSON.stringify(['platform',String(last)]):null;}
  class State {
    constructor(){this.initialized=false;this.seenRuns=new Map();this.announcedRuns=new Map();this.agentStates=new Map();this.scheduleStates=new Map();this.releaseKey=null;this.unread=Object.fromEntries(categories.map(k=>[k,new Map()]));this.cards=[];}
    counts(){return Object.fromEntries(categories.map(k=>[k,this.unread[k].size]));}
    clear(category,taskId=null){if(!this.unread[category])return;if(category==='conversations'&&taskId){for(const [key,id] of this.unread[category])if(id===taskId)this.unread[category].delete(key);this.cards=this.cards.filter(c=>c.task_id!==taskId);}else{this.unread[category].clear();if(category==='conversations')this.cards=[];}}
    update(snapshot={}){
      const runs=new Map();for(const key of ['runs','latest_runs','open_runs','current_runs'])for(const r of snapshot[key]||[])if(r.id)runs.set(r.id,r);
      const tasks=new Map((snapshot.tasks||[]).filter(t=>t.id).map(t=>[t.id,t])),agents=new Map((snapshot.agents||[]).filter(a=>a.id).map(a=>[a.id,a]));
      const assignments=new Map();for(const a of snapshot.agent_run_assignments||[])if(agents.has(a.agent_id)&&runs.has(a.run_id)){if(!assignments.has(a.run_id))assignments.set(a.run_id,[]);assignments.get(a.run_id).push(agents.get(a.agent_id));}
      const changed=new Set(),added=[],baseline=!this.initialized;let contentChanged=false;
      for(const [key,run] of runs)if(!this.seenRuns.has(key)){this.seenRuns.set(key,true);if(!baseline){remember(this.unread.conversations,key,run.task_id);changed.add('conversations');}}
      for(const [key,people] of assignments){
        const run=runs.get(key),taskId=run.task_id,person=people[0];const card={id:key,task_id:taskId,title:String(tasks.get(taskId)?.name||taskId||'').slice(0,160),agent:String(person.name||person.id||'').slice(0,80),avatar:person.avatar||'mint',participants:people.length,agent_record:Object.fromEntries(['id','name','name_en','avatar','portrait','portrait_spec'].filter(key=>key in person).map(key=>[key,person[key]]))};
        if(this.announcedRuns.has(key)){const existing=this.cards.find(item=>item.id===key);if(existing&&JSON.stringify(existing)!==JSON.stringify(card)){Object.assign(existing,card);contentChanged=true;}continue;}
        this.announcedRuns.set(key,true);if(baseline||!open.has(run.status))continue;remember(this.unread.conversations,key,taskId);this.cards.unshift(card);this.cards=this.cards.slice(0,50);added.push(card);changed.add('conversations');
      }
      for(const [key,person] of agents){const status=person.status||'unknown';if(this.agentStates.get(key)!==status){if(!baseline){remember(this.unread.agents,key);changed.add('agents');}this.agentStates.set(key,status);}}
      for(const item of snapshot.schedules||[]){const key=item.id,identity=scheduleIdentity(item);if(key&&identity&&this.scheduleStates.get(key)!==identity){if(!baseline){remember(this.unread.schedules,key);changed.add('schedules');}this.scheduleStates.set(key,identity);}}
      pruneHistory(this.seenRuns,runs);pruneHistory(this.announcedRuns,assignments);pruneHistory(this.agentStates,agents);pruneHistory(this.scheduleStates,new Set((snapshot.schedules||[]).filter(scheduleIdentity).map(item=>item.id)));
      const about=snapshot.about||{},key=newerRelease(about)?about.release.release_tag:null;if(key!==this.releaseKey){this.releaseKey=key;this.unread.about.clear();if(key){this.unread.about.set(key,true);if(!baseline)changed.add('about');}}
      this.initialized=true;return {changed,cards:added,baseline,content_changed:contentChanged};
    }
  }
  class Deadline {
    constructor(now=()=>performance.now()){this.now=now;this.remaining=0;this.started=null;this.paused=false;}
    reset(ms=5000){this.remaining=ms;this.started=this.paused?null:this.now();}
    pause(value){if(value===this.paused)return;if(value&&this.started!==null){this.remaining=Math.max(0,this.remaining-(this.now()-this.started));this.started=null;}else if(!value)this.started=this.now();this.paused=value;}
    left(){return this.started===null?this.remaining:Math.max(0,this.remaining-(this.now()-this.started));}
  }
  class Controller {
    constructor({document:doc,language,openTask,avatar}){
      this.doc=doc;this.language=language;this.openTask=openTask;this.avatarFactory=avatar;this.state=new State();this.deadline=new Deadline();this.expanded=false;this.closing=false;this.hover=false;this.keyboard=false;this.returnFocus=null;this.timer=null;this.hideTimer=null;this.pulses=new Map();
      const el=(tag,cls,text='')=>{const e=doc.createElement(tag);e.className=cls;e.textContent=text;return e;};
      this.host=el('section','notification-layer');this.host.hidden=true;this.host.setAttribute('aria-label','Task notifications');this.host.dataset.expanded='false';this.host.dataset.inputMode='pointer';
      this.shell=el('div','notification-card');this.face=el('span','notification-avatar');this.face.setAttribute('aria-hidden','true');
      this.kicker=el('p','notification-kicker');this.title=el('strong','notification-title');this.owner=el('p','notification-owner');this.body=el('div','notification-copy');this.body.append(this.kicker,this.title,this.owner);
      this.close=el('button','notification-close','×');this.close.type='button';this.close.addEventListener('click',()=>this.collapse());
      this.action=el('button','notification-action');this.action.type='button';this.action.addEventListener('click',()=>{const card=this.state.cards[0];if(card){const keyboard=this.keyboard;this.markRead('conversations',card.task_id);openTask(card.task_id,{keyboard});if(this.state.cards.length&&this.expanded){this.deadline.reset();this.syncPause();}}});
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
    markRead(page,taskId=null){this.state.clear(page,taskId);if(!this.state.cards.length){this.expanded=false;this.closing=false;clearTimeout(this.timer);clearTimeout(this.hideTimer);this.timer=null;this.hideTimer=null;}this.badges();this.render();}
    badges(changed=new Set()){
      const counts=this.state.counts();for(const page of categories){const nav=this.doc.querySelector(`[data-nav="${page}"]`);if(!nav)continue;let badge=nav.querySelector('.notification-badge');if(!badge){badge=this.doc.createElement('span');badge.className='notification-badge';badge.dataset.kind=page;nav.append(badge);}badge.hidden=!counts[page];badge.textContent=page==='about'?'NEW':'';badge.setAttribute('aria-label',this.phrase('有未读更新','Unread updates'));if(changed.has(page)&&page!=='about'&&!this.reduced()){badge.classList.remove('notification-pulse');void badge.offsetWidth;badge.classList.add('notification-pulse');clearTimeout(this.pulses.get(page));this.pulses.set(page,setTimeout(()=>{badge.classList.remove('notification-pulse');this.pulses.delete(page);},400));}}
    }
    render(){
      const count=this.state.cards.length;this.host.hidden=!count||(!this.expanded&&!this.closing);this.host.dataset.expanded=String(this.expanded);this.shell.setAttribute('aria-hidden',String(!this.expanded));this.shell.inert=!this.expanded;if(!count||this.host.hidden)return;
      const card=this.state.cards[0],agent=card.agent_record||{avatar:card.avatar};this.host.classList.toggle('notification-stacked',count>1);
      const portraitKey=JSON.stringify([agent.id,agent.portrait,agent.portrait_spec]);if(this.portraitKey!==portraitKey){this.portraitKey=portraitKey;this.face.replaceChildren();if(this.avatarFactory)this.face.append(this.avatarFactory(agent));}
      this.host.setAttribute('aria-label',this.phrase('任务通知','Task notifications'));this.kicker.textContent=this.phrase('新的任务已分派','Task assigned');this.title.textContent=card.title;this.title.title=card.title;this.owner.textContent=this.phrase('已登记分派 · ','Assigned · ')+(this.language()==='en'&&agent.name_en?agent.name_en:card.agent)+(card.participants>1?' +'+(card.participants-1):'');this.close.setAttribute('aria-label',this.phrase('隐藏通知，保留未读','Hide notification, keep unread'));this.action.textContent=this.phrase('查看进度 →','View progress →');this.more.hidden=count<2;this.more.textContent=this.phrase(`另有 ${count-1} 条 · 下一条`,`+${count-1} more · next`);this.hint.hidden=count>1;this.hint.textContent=this.phrase('约 5 秒后隐藏 · 悬停 / 键盘焦点暂停','Hides after 5s · hover / keyboard focus to pause');
    }
    destroy(){clearTimeout(this.timer);clearTimeout(this.hideTimer);clearTimeout(this.focusTimer);for(const timer of this.pulses.values())clearTimeout(timer);this.pulses.clear();this.doc.removeEventListener('pointerdown',this.pointerInput,true);this.doc.removeEventListener('keydown',this.keyboardInput,true);this.host.remove();}
  }
  globalThis.PanelNotifications={State,Deadline,Controller,newerRelease,scheduleIdentity};
})();
