import os,subprocess,sys,tempfile,unittest,sqlite3
from pathlib import Path
from dots_panel.app import Store

class ReadonlyCLIBoundaryTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def invoke(self,data,args):return subprocess.run([sys.executable,'-m','dots_panel','--data-dir',str(data),*args],capture_output=True,timeout=10,env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')})
 def commands(self):return [('status',),('timeline','goal'),('serve','--port','0'),('reset-list',),('requirement-list','goal'),('requirement-diagnose','goal'),('requirement-sync-status','goal'),('followup-audit','--task-id','goal'),('dispatch-check','goal','actor')]
 def test_absent_directory_never_initialized(self):
  for i,args in enumerate(self.commands()):
   data=self.root/str(i);r=self.invoke(data,args);self.assertNotEqual(r.returncode,0,args);self.assertFalse(data.exists(),args)
 def test_missing_database_never_recreated(self):
  data=self.root/'data';s=Store(data);s.path.unlink()
  before={str(p.relative_to(data)) for p in data.rglob('*')}
  for args in self.commands():
   r=self.invoke(data,args);self.assertNotEqual(r.returncode,0,args);self.assertFalse(s.path.exists(),args)
  self.assertEqual(before,{str(p.relative_to(data)) for p in data.rglob('*')})
 def test_unknown_schema_not_migrated(self):
  data=self.root/'data';(data/'db').mkdir(parents=True,mode=0o700);p=data/'db/panel.sqlite3';db=sqlite3.connect(p);db.execute('CREATE TABLE sentinel(value TEXT)');db.commit();db.close();p.chmod(0o600);before=p.read_bytes()
  for args in [('status',),('timeline','goal'),('serve','--port','0')]:
   r=self.invoke(data,args);self.assertNotEqual(r.returncode,0,args);self.assertEqual(before,p.read_bytes(),args)
 def test_readonly_alias_does_not_follow_symlink(self):
  data=self.root/'data';Store(data);alias=self.root/'alias';alias.symlink_to(data,target_is_directory=True)
  result=self.invoke(alias,['status']);self.assertNotEqual(result.returncode,0)
 def test_explicit_init_still_supported(self):
  data=self.root/'data';r=self.invoke(data,['init']);self.assertEqual(r.returncode,0,r.stderr);self.assertTrue((data/'db/panel.sqlite3').is_file());self.assertEqual(self.invoke(data,['status']).returncode,0)

if __name__=='__main__':unittest.main()

class DesktopReadBoundaryTests(unittest.TestCase):
 def test_desktop_health_does_not_initialize(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp)/'absent';script=Path(__file__).resolve().parents[1]/'scripts/desktop.py'
   result=subprocess.run([sys.executable,str(script),'health','--data-dir',str(data),'--port','1'],capture_output=True,timeout=5)
   self.assertEqual(result.returncode,0,result.stderr);self.assertFalse(data.exists())
 def test_desktop_open_missing_data_does_not_initialize(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp)/'absent';script=Path(__file__).resolve().parents[1]/'scripts/desktop.py'
   result=subprocess.run([sys.executable,str(script),'open','--data-dir',str(data)],capture_output=True,timeout=5)
   self.assertNotEqual(result.returncode,0);self.assertFalse(data.exists())

class DesktopUnknownSchemaTests(unittest.TestCase):
 def test_unknown_schema_fails_before_logs_or_viewer(self):
  with tempfile.TemporaryDirectory() as tmp:
   data=Path(tmp)/'unknown';data.mkdir(mode=0o700)
   for name in ('db','logs','run','config'):(data/name).mkdir(mode=0o700)
   path=data/'db/panel.sqlite3';db=sqlite3.connect(path);db.execute('CREATE TABLE sentinel(value TEXT)');db.commit();db.close();path.chmod(0o600)
   before={str(p.relative_to(data)) for p in data.rglob('*')};raw=path.read_bytes();script=Path(__file__).resolve().parents[1]/'scripts/desktop.py'
   result=subprocess.run([sys.executable,str(script),'open','--data-dir',str(data)],capture_output=True,timeout=5)
   self.assertNotEqual(result.returncode,0);self.assertEqual(before,{str(p.relative_to(data)) for p in data.rglob('*')});self.assertEqual(raw,path.read_bytes())
