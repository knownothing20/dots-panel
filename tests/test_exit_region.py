import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from dots_panel import exit_region as region

class ExitRegionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); (self.root/'config').mkdir(mode=0o700)
    def reply(self, **extra):
        return io.BytesIO(json.dumps(dict(success=True,country='Example country',country_code='ZZ',region='Example region',city='Example city',ip='203.0.113.1',**extra)).encode())
    def test_explicit_lookup_allowlists_cache(self):
        calls=[]
        def opener(url, timeout): calls.append((url,timeout)); return self.reply()
        value=region.lookup(self.root,opener)
        self.assertEqual(len(calls),1); self.assertEqual(calls[0][1],8)
        self.assertNotIn('ip',value); self.assertEqual(region.load(self.root),value)
        self.assertEqual((self.root/'config'/region.FILE).stat().st_mode&0o777,0o600)
    def test_failure_preserves_cache(self):
        previous=region.lookup(self.root,lambda *a,**k:self.reply())
        def fail(*a,**k): raise TimeoutError('timed out')
        with self.assertRaises(TimeoutError):region.lookup(self.root,fail)
        self.assertEqual(region.load(self.root),previous)
    def test_unknown_invalid_cache(self):
        self.assertIsNone(region.load(self.root))
        (self.root/'config'/region.FILE).write_text('{invalid')
        self.assertIsNone(region.load(self.root)); self.assertIn('未核验',region.label(None))
    def test_untrusted_time_and_text(self):
        value=dict(provider='ipwho.is',scope='panel_backend_exit',country='Example',checked_at=float('nan'))
        with self.assertRaises(ValueError):region.validate(value)
        value.update(checked_at=time.time(),country='bad\ntext')
        with self.assertRaises(ValueError):region.validate(value)
    def test_old_observation_label(self):
        value=region.lookup(self.root,lambda *a,**k:self.reply())
        self.assertIn('旧观察',region.label(value,now=value['checked_at']+86401))
    def test_symlink_rejected(self):
        target=self.root/'elsewhere'; target.write_text('unchanged')
        (self.root/'config'/region.FILE).symlink_to(target)
        self.assertIsNone(region.load(self.root))
        with self.assertRaises(ValueError):region.lookup(self.root,lambda *a,**k:self.reply())
        self.assertEqual(target.read_text(),'unchanged')
    def test_no_network_during_load(self):
        from unittest.mock import patch
        with patch('urllib.request.urlopen',side_effect=AssertionError('network')):
            self.assertIsNone(region.load(self.root))
