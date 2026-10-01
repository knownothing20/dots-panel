import copy
import unittest
from dots_panel.notifications import NotificationState, newer_release, schedule_identity


def state():
    return {'tasks':[{'id':'t','name':'Synthetic task'}], 'runs':[], 'agents':[], 'agent_run_assignments':[], 'schedules':[], 'about':{}}

class NotificationTests(unittest.TestCase):
    def test_baseline_refresh_and_heartbeat_do_not_replay(self):
        s=state();s['runs']=[{'id':'r','task_id':'t','status':'running','updated':1}];s['agents']=[{'id':'a','name':'Agent','status':'running','observed_at':1}];s['agent_run_assignments']=[{'run_id':'r','agent_id':'a'}]
        model=NotificationState();self.assertTrue(model.update(s)['baseline']);self.assertEqual(model.counts()['conversations'],0)
        s['runs'][0]['updated']=999;s['agents'][0]['observed_at']=999
        self.assertFalse(model.update(s)['changed']);self.assertFalse(model.cards)
    def test_registration_then_assignment_is_one_unread_and_one_card(self):
        s=state();m=NotificationState();m.update(s)
        s['runs']=[{'id':'r','task_id':'t','status':'waiting_external'}];m.update(s)
        self.assertEqual(m.counts()['conversations'],1);self.assertFalse(m.cards)
        s['agents']=[{'id':'a','name':'Agent','status':'running'}];s['agent_run_assignments']=[{'run_id':'r','agent_id':'a'}]
        self.assertEqual(len(m.update(s)['cards']),1);self.assertEqual(m.counts()['conversations'],1)
        s['agents'].append({'id':'b','name':'Other','status':'running'});s['agent_run_assignments'].append({'run_id':'r','agent_id':'b'})
        result=m.update(s);self.assertFalse(result['cards']);self.assertTrue(result['content_changed']);self.assertEqual(len(m.cards),1);self.assertEqual(m.cards[0]['participants'],2)
        m.clear('agents');self.assertEqual(m.counts()['agents'],0);self.assertEqual(len(m.cards),1)
        m.clear('conversations','t');self.assertFalse(m.cards);self.assertFalse(m.update(s)['cards'])
    def test_agent_status_not_note_or_timestamp(self):
        s=state();s['agents']=[{'id':'a','status':'running'}];m=NotificationState();m.update(s)
        s['agents'][0].update(note='Updated',observed_at=20);self.assertFalse(m.update(s)['changed'])
        s['agents'][0]['status']='idle';self.assertIn('agents',m.update(s)['changed'])
    def test_result_retry_check_time_and_actual_status(self):
        s=state();s['schedules']=[{'id':'s','external_result':{'checked_at':1,'observation':{'latest':{'run_id':'run','status':'partial'}}}}]
        m=NotificationState();m.update(s);s['schedules'][0]['external_result']['checked_at']=4;self.assertFalse(m.update(s)['changed'])
        s['schedules'][0]['external_result']['observation']['latest']['status']='succeeded';self.assertIn('schedules',m.update(s)['changed'])
    def test_newer_manual_release_and_read_once(self):
        about={'installed_version':'0.2.0','release':{'release_status':'published','release_tag':'v0.3.0','checked_at':1}}
        m=NotificationState();m.update({'about':about});self.assertEqual(m.counts()['about'],1)
        m.clear('about');about['release']['checked_at']=20;m.update({'about':about});self.assertEqual(m.counts()['about'],0)
        for tag in ['v0.1.0','v0.2.0','main','v0.3.0-rc1','v00.3.0','v0.3.0+..','v١.2.3',None]:
            a=copy.deepcopy(about);a['release']['release_tag']=tag;self.assertFalse(newer_release(a))
        about['release']['release_status']='unknown';self.assertFalse(newer_release(about))
    def test_historical_completed_assignment_never_toasts(self):
        m=NotificationState();m.update(state());s=state();s['runs']=[{'id':'r','task_id':'t','status':'succeeded'}];s['agents']=[{'id':'a'}];s['agent_run_assignments']=[{'run_id':'r','agent_id':'a'}]
        self.assertFalse(m.update(s)['cards'])
    def test_bound_and_category_clearing(self):
        m=NotificationState();m.update(state())
        s=state();s['runs']=[{'id':str(n),'task_id':'t','status':'running'} for n in range(2100)];m.update(s)
        self.assertEqual(len(m.seen_runs),len(s['runs']));self.assertLessEqual(m.counts()['conversations'],m.limit)
        m.clear('conversations');self.assertEqual(m.counts()['conversations'],0)
        m.update(state());self.assertLessEqual(len(m.seen_runs),m.limit)

    def test_large_current_snapshots_never_evict_each_other_or_replay(self):
        for count in (2001, 5007):
            with self.subTest(count=count):
                s=state();s['runs']=[{'id':f'r{n}','task_id':'t','status':'running'} for n in range(count)]
                s['agents']=[{'id':'a','status':'running'}]
                s['agent_run_assignments']=[{'run_id':r['id'],'agent_id':'a'} for r in s['runs']]
                baseline=NotificationState();baseline.update(s)
                for _ in range(3):
                    result=baseline.update(s);self.assertFalse(result['cards']);self.assertFalse(result['changed']);self.assertFalse(baseline.cards)
                new=NotificationState();new.update(state());self.assertEqual(len(new.update(s)['cards']),count)
                self.assertLessEqual(len(new.cards),50);self.assertLessEqual(new.counts()['conversations'],new.limit)
                for _ in range(3):
                    result=new.update(s);self.assertFalse(result['cards']);self.assertFalse(result['changed'])
                s['runs'].append({'id':'one-more','task_id':'t','status':'running'});s['agent_run_assignments'].append({'run_id':'one-more','agent_id':'a'})
                self.assertEqual(len(new.update(s)['cards']),1);self.assertFalse(new.update(s)['changed'])
                self.assertEqual(len(new.seen_runs),count+1);self.assertEqual(len(new.announced_runs),count+1)

    def test_large_agent_and_schedule_observations_stay_stable(self):
        s=state();s['agents']=[{'id':f'a{n}','status':'running'} for n in range(2200)]
        s['schedules']=[{'id':f's{n}','platform_observation':{'last_run_at':'2026-10-01T00:00:00Z'}} for n in range(2200)]
        m=NotificationState();m.update(s);self.assertFalse(m.update(s)['changed'])
        s['agents'][0]['status']='idle';self.assertEqual(m.update(s)['changed'],{'agents'});self.assertFalse(m.update(s)['changed'])

    def test_notification_keeps_shared_profile_portrait_fields(self):
        s=state();m=NotificationState();m.update(s);s['runs']=[{'id':'r','task_id':'t','status':'running'}]
        person={'id':'a','name':'Example','name_en':'Example EN','avatar':'mint','portrait':'bloom-mint','portrait_spec':{'key':'bloom-mint','shapes':[]},'note':'Not needed in a notification'}
        s['agents']=[person];s['agent_run_assignments']=[{'run_id':'r','agent_id':'a'}];m.update(s)
        self.assertEqual(m.cards[0]['agent_record']['portrait'],person['portrait']);self.assertEqual(m.cards[0]['agent_record']['portrait_spec'],person['portrait_spec']);self.assertNotIn('note',m.cards[0]['agent_record'])
