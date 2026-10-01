"""New integration/security checks, not part of the historical test count."""
import http.client
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from dots_panel.app import Store, make_server

class RecoverySecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name)/'private')
        self.server = make_server(self.store, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()
    def request(self, method, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request(method,path,headers=headers or {})
        response = connection.getresponse()
        result = response.status,dict(response.getheaders()),response.read()
        connection.close()
        return result
    def test_loopback_binding(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
    def test_mutations_not_exposed(self):
        for method in ('POST','PUT','DELETE','PATCH'):
            self.assertEqual(self.request(method,'/api/state')[0],405)
    def test_host_rebinding_rejected(self):
        for host in ('evil.example','localhost.evil:80','127.0.0.1.evil'):
            self.assertEqual(self.request('GET','/api/state',{'Host':host})[0],403)
    def test_cross_site_rejected(self):
        self.assertEqual(self.request('GET','/api/state',{'Sec-Fetch-Site':'cross-site'})[0],403)
    def test_path_traversal_and_database_not_served(self):
        for path in ('/../src/dots_panel/app.py','/%2e%2e/src/dots_panel/app.py','/db/panel.sqlite3','/api/artifacts/../../db/panel.sqlite3','/config'):
            self.assertEqual(self.request('GET',path)[0],404,path)
    def test_headers_and_readonly_snapshot(self):
        status,headers,body=self.request('GET','/api/state')
        self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertNotIn(str(self.store.directory).encode(),body)
    def test_private_database(self):
        self.assertEqual(self.store.path.stat().st_mode & 0o077,0)
        self.assertEqual(self.store.directory.stat().st_mode & 0o077,0)
    def test_source_data_overlap_rejected(self):
        from dots_panel.app import ROOT
        with self.assertRaises(ValueError): Store(ROOT/'unsafe-test-data')
    def test_symlink_directory_rejected(self):
        link=Path(self.temp.name)/'alias';link.symlink_to(self.store.directory,target_is_directory=True)
        with self.assertRaises(ValueError): Store(link)
    def test_snapshot_is_empty_not_invented_history(self):
        state=self.store.snapshot()
        self.assertEqual(state['tasks'],[])
        self.assertEqual(state['runs'],[])

if __name__ == '__main__': unittest.main()
