import hashlib
import os
from pathlib import Path
import tempfile
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch, Mock
from dots_panel.app import Store
from dots_panel.outputs import output_summary_text, TaskFolderOpener, validate_mp4_header


def mp4():
    return (24).to_bytes(4,'big')+b'ftypisom'+b'\0\0\2\0'+b'isommp42'+(12).to_bytes(4,'big')+b'mdatDATA'

class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=Store(self.root/'private');self.store.register('task','Task','Synthetic')
    def tearDown(self):self.temp.cleanup()
    def add(self, name='output.txt',kind='report'):
        source=self.root/name;source.write_bytes(mp4() if name.endswith('.mp4') else b'Synthetic output')
        return self.store.artifact_add('task',source,name,kind=kind)
    def test_empty_summary_and_label(self):
        self.assertEqual(self.store.snapshot()['output_summaries'],{})
        self.assertEqual(output_summary_text({},'en'),'No registered outputs')
    def test_counts_all_and_main_prefers_latest_final(self):
        first=self.add();self.store.artifact_designate(first['id'],'final','Synthetic final record')
        second=self.add('later.md');self.store.artifact_designate(second['id'],'draft','Synthetic draft record')
        summary=self.store.snapshot()['output_summaries']['task'];self.assertEqual(summary['count'],2);self.assertEqual(summary['main']['id'],first['id']);self.assertEqual(summary['main']['delivery'],[])
        self.store.artifact_designate(second['id'],'final','Synthetic updated designation')
        self.assertEqual(self.store.snapshot()['output_summaries']['task']['main']['id'],second['id'])
    def test_large_registry_counts_not_snapshot_window(self):
        with self.store.connect() as db:
            db.executemany('INSERT INTO artifacts VALUES(?,?,?,?,?,?,?,?,?)',[(f'a{i}','task',f'tasks/task/outputs/a{i}.txt',f'Output{i}','report',1,'a'*64,i,None) for i in range(1200)])
        summary=self.store.snapshot()['output_summaries']['task'];self.assertEqual(summary['count'],1200);self.assertEqual(summary['main']['title'],'Output1199')
    def test_delivery_is_separate_from_archive(self):
        a=self.add();self.store.artifact_delivery(a['id'],'sent','Synthetic delivery observation',time.time())
        summary=self.store.snapshot()['output_summaries']['task'];self.assertEqual(summary['main']['delivery'],['sent']);self.assertNotIn('accepted',summary['main']['delivery'])
    def test_mp4_metadata_archive_and_hash(self):
        a=self.add('example.mp4','video');s=self.store.snapshot()['output_summaries']['task'];self.assertEqual(s['kinds'],[{'kind':'video','count':1}]);self.assertEqual(s['main']['designation'],'unclassified')
        self.assertEqual(a['sha256'],hashlib.sha256(mp4()).hexdigest())
        with self.assertRaises(ValueError):self.store.artifact_text(a['id'])
        with self.assertRaises(ValueError):self.store.artifact_png(a['id'])
    def test_mp4_kind_and_extension_strict(self):
        with self.assertRaises(ValueError):self.add('example.mp4','other')
        with self.assertRaises(ValueError):self.add('example.txt','video')
        self.assertEqual(self.store.snapshot()['artifacts'],[])
    def test_mp4_bad_headers_rejected(self):
        for content in (b'#!/bin/sh\necho unsafe',b'\0'*36,mp4().replace(b'ftyp',b'junk'),mp4().replace(b'isom',b'xxxx').replace(b'mp42',b'xxxx'),(9999).to_bytes(4,'big')+mp4()[4:],mp4()[:12]):
            with self.subTest(content=content),self.assertRaises(ValueError):validate_mp4_header(content,len(content))
    def test_summary_bilingual_types_and_no_path(self):
        self.add('example.mp4','video');summary=self.store.snapshot()['output_summaries']['task']
        self.assertIn('视频',output_summary_text(summary));self.assertIn('videos',output_summary_text(summary,'en'));self.assertNotIn(str(self.root),str(summary))

class OutputFolderTests(unittest.TestCase):
    setUp=OutputTests.setUp
    tearDown=OutputTests.tearDown
    add=OutputTests.add
    def test_registered_directory_only_and_argv_no_shell(self):
        self.add();opener=TaskFolderOpener()
        with patch('dots_panel.outputs.subprocess.Popen') as launch:
            launch.return_value.poll.return_value=0
            opener.open(self.store,'task');args=launch.call_args
            self.assertEqual(args.args[0],['/usr/bin/xdg-open',str(self.store.directory/'tasks/task/outputs')]);self.assertFalse(args.kwargs['shell'])
            opener.open(self.store,'task');self.assertEqual(len(opener._processes),1)
        opener.close()
    def test_unknown_empty_and_malicious_ids_never_launch(self):
        opener=TaskFolderOpener()
        with patch('dots_panel.outputs.subprocess.Popen') as launch:
            for key in ('task','unknown','../task','task;touch x','/tmp',None):
                with self.assertRaises(ValueError):opener.open(self.store,key)
            launch.assert_not_called()
    def test_symlink_directory_never_launches(self):
        self.add();folder=self.store.directory/'tasks/task/outputs';folder.rename(folder.with_name('saved'));folder.symlink_to(folder.with_name('saved'))
        with patch('dots_panel.outputs.subprocess.Popen') as launch:
            with self.assertRaises((OSError,ValueError)):TaskFolderOpener().open(self.store,'task')
            launch.assert_not_called()
    def test_changed_directory_never_launches(self):
        self.add();original=self.store.task_directory;calls=[]
        @contextmanager
        def change(*args,**kwargs):
            calls.append(True)
            if len(calls)==2:
                folder=self.store.directory/'tasks/task/outputs';folder.rename(folder.with_name('saved'));folder.mkdir(mode=0o700)
            with original(*args,**kwargs) as fd:yield fd
        with patch.object(self.store,'task_directory',change),patch('dots_panel.outputs.subprocess.Popen') as launch:
            with self.assertRaises(ValueError):TaskFolderOpener().open(self.store,'task')
            launch.assert_not_called()
    def test_opener_failure_releases_handle(self):
        self.add();opener=TaskFolderOpener()
        with patch('dots_panel.outputs.subprocess.Popen',side_effect=OSError('Missing desktop opener')):
            with self.assertRaises(OSError):opener.open(self.store,'task')
        self.assertEqual(opener._processes,[])
