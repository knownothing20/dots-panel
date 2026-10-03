import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from dots_panel.notifications import NotificationState, NotificationStorage


def snapshot(stream='synthetic-stream'):
    return {'requirement_stream_id':stream,'requirement_events':[],'requirement_counters':{'receipt':0,'state':0,'owner':0,'link':0},'requirements':[]}


def add(s, key='q', kind='receipt', status='received', agent=None):
    seq=len(s['requirement_events'])+1
    event={'id':seq,'kind':kind,'requirement_id':key,'task_id':'t','source_event_id':'source-'+str(seq)}
    s['requirement_events'].append(event);s['requirement_counters'][kind]=seq
    r=next((r for r in s['requirements'] if r['id']==key),None)
    if r is None:
        r={'id':key,'task_id':'t','summary':'Original '+key,'source_event_id':'request-'+key,'current_event_id':seq,'current_owner_event_id':0,'status':status,'owner':{},'run_ids':['r']};s['requirements'].append(r)
    if kind=='owner':r['current_owner_event_id']=seq;r['owner']={'name':agent or 'Example','actual_model':None}
    else:r['current_event_id']=seq;r['status']=status
    return r


class RequirementNotificationTests(unittest.TestCase):
    def test_first_stream_baseline_then_receipt_owner_state_dedup(self):
        s=snapshot();add(s);m=NotificationState();self.assertTrue(m.update(s)['baseline']);self.assertFalse(m.cards)
        add(s,'q2');self.assertEqual(len(m.update(s)['cards']),1);self.assertEqual(m.counts()['conversations'],1)
        add(s,'q2','owner',agent='Fern');self.assertEqual(len(m.update(s)['cards']),1);self.assertEqual(len(m.cards),1);self.assertEqual(m.cards[0]['agent'],'Fern')
        add(s,'q2','state','pending_acceptance');self.assertEqual(len(m.update(s)['cards']),1);self.assertEqual(m.cards[0]['status'],'pending_acceptance')
        self.assertFalse(m.update(s)['changed']);m.clear('conversations','t','q2');self.assertFalse(m.update(s)['cards']);self.assertFalse(m.cards)

    def test_same_run_requirements_have_independent_notifications(self):
        s=snapshot();m=NotificationState();m.update(s);add(s,'q1');add(s,'q2');m.update(s)
        self.assertEqual(m.counts()['conversations'],2);self.assertEqual({c['requirement_id'] for c in m.cards},{'q1','q2'})

    def test_restart_preserves_unread_and_acknowledgement(self):
        with tempfile.TemporaryDirectory() as temp:
            s=snapshot();storage=NotificationStorage(temp);m=NotificationState(storage);m.update(s);add(s);m.update(s)
            self.assertEqual(storage.persistence,'persistent');self.assertEqual((Path(temp)/'config/notifications.json').stat().st_mode & 0o777,0o600)
            restarted=NotificationState(NotificationStorage(temp));self.assertEqual(restarted.counts()['conversations'],1);self.assertEqual(len(restarted.cards),1);self.assertFalse(restarted.update(s)['changed'])
            restarted.clear('conversations','t','q');again=NotificationState(NotificationStorage(temp));self.assertFalse(again.update(s)['changed']);self.assertFalse(again.cards)

    def test_new_changes_while_viewer_closed_are_unread(self):
        with tempfile.TemporaryDirectory() as temp:
            s=snapshot();m=NotificationState(NotificationStorage(temp));m.update(s);add(s);m.update(s);m.clear('conversations', requirement_id='q')
            add(s,'q','owner');n=NotificationState(NotificationStorage(temp));self.assertEqual(len(n.update(s)['cards']),1)

    def test_different_or_rewound_stream_is_fresh_baseline(self):
        for replacement in (True,False):
            s=snapshot();m=NotificationState();m.update(s);original=copy.deepcopy(s);add(s);m.update(s);self.assertEqual(m.counts()['conversations'],1)
            rewind=copy.deepcopy(s) if replacement else original
            if replacement:rewind['requirement_stream_id']='replacement'
            result=m.update(rewind);self.assertTrue(result['baseline']);self.assertFalse(result['cards']);self.assertFalse(m.cards);self.assertEqual(m.counts()['conversations'],0)
            add(rewind,'new');self.assertEqual(len(m.update(rewind)['cards']),1)

    def test_rewritten_same_sequence_is_new_baseline(self):
        s=snapshot();m=NotificationState();m.update(s);add(s);m.update(s);s['requirement_events'][0]['source_event_id']='replacement-source'
        self.assertTrue(m.update(s)['baseline']);self.assertFalse(m.cards)

    def test_storage_write_failure_is_session_only_not_loss_of_unread(self):
        with tempfile.TemporaryDirectory() as temp:
            storage=NotificationStorage(temp);m=NotificationState(storage);s=snapshot()
            with patch('dots_panel.notifications.os.replace',side_effect=PermissionError('Denied')):m.update(s)
            self.assertEqual(m.persistence,'session_only');self.assertIn('session-only',m.storage_error);add(s);m.update(s);self.assertEqual(m.counts()['conversations'],1)

    def test_storage_symlink_and_public_files_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'config').mkdir(mode=0o700);target=root/'outside';target.write_text('unchanged');(root/'config/notifications.json').symlink_to(target)
            storage=NotificationStorage(temp);self.assertIsNone(storage.load());self.assertEqual(storage.persistence,'session_only');self.assertFalse(storage.save({'version':1}));self.assertEqual(target.read_text(),'unchanged')
            (root/'config/notifications.json').unlink();(root/'config/notifications.json').write_text('{"version":1}');os.chmod(root/'config/notifications.json',0o644)
            self.assertIsNone(NotificationStorage(temp).load())

    def test_malformed_saved_state_has_no_acknowledgement_effect(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'config';p.mkdir(mode=0o700);f=p/'notifications.json';f.write_text('{bad');os.chmod(f,0o600)
            m=NotificationState(NotificationStorage(temp));self.assertEqual(m.persistence,'session_only');s=snapshot();self.assertTrue(m.update(s)['baseline'])

class LargeRequirementNotificationTests(unittest.TestCase):
    def test_2001_unread_cards_survive_legacy_arrival_restart_and_first_read(self):
        with tempfile.TemporaryDirectory() as temp:
            s=snapshot();m=NotificationState(NotificationStorage(temp));m.update(s)
            for i in range(2001):add(s,'q'+str(i))
            result=m.update(s)
            self.assertEqual(len(result['cards']),2001);self.assertEqual(m.counts()['conversations'],2001);self.assertEqual(len(m.cards),2001)
            s['runs']=[{'id':'legacy','task_id':'legacy-task','status':'running'}];m.update(s)
            self.assertIn('requirement:q0',m.unread['conversations']);self.assertEqual(m.counts()['conversations'],2002)
            n=NotificationState(NotificationStorage(temp));self.assertEqual(n.persistence,'persistent');self.assertEqual(n.counts()['conversations'],2002);self.assertEqual(len(n.cards),2001)
            self.assertFalse(n.update(s)['changed']);self.assertIn('requirement:q0',{c['id'] for c in n.cards})
            n.clear('conversations','t','q0');again=NotificationState(NotificationStorage(temp));self.assertNotIn('requirement:q0',again.unread['conversations']);self.assertEqual(again.counts()['conversations'],2001)
    def test_failed_write_retry_preserves_all_unread_after_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            s=snapshot();m=NotificationState(NotificationStorage(temp));m.update(s)
            for i in range(2001):add(s,'q'+str(i))
            with patch('dots_panel.notifications.os.replace',side_effect=PermissionError('Temporary write failure')):m.update(s)
            self.assertEqual(m.persistence,'session_only');self.assertEqual(m.counts()['conversations'],2001)
            self.assertFalse(m.update(s)['changed']);self.assertEqual(m.persistence,'persistent');self.assertIsNone(m.storage_error)
            n=NotificationState(NotificationStorage(temp));self.assertEqual(n.counts()['conversations'],2001);self.assertEqual(len(n.cards),2001);self.assertIn('requirement:q0',n.unread['conversations'])
    def test_failed_initial_read_never_overwrites_unloaded_unreads(self):
        with tempfile.TemporaryDirectory() as temp:
            s=snapshot();m=NotificationState(NotificationStorage(temp));m.update(s);add(s,'existing');m.update(s)
            path=Path(temp)/'config/notifications.json';original=path.read_bytes()
            with patch('dots_panel.notifications.Path.read_text',side_effect=PermissionError('Temporary read failure')):
                fresh=NotificationState(NotificationStorage(temp))
            fresh.update(s);add(s,'new');fresh.update(s)
            self.assertEqual(fresh.persistence,'session_only');self.assertEqual(path.read_bytes(),original)
            reopened=NotificationState(NotificationStorage(temp));self.assertIn('requirement:existing',reopened.unread['conversations']);reopened.update(s);self.assertEqual(reopened.counts()['conversations'],2)
