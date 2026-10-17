# SPDX-License-Identifier: GPL-3.0-or-later
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'src'))
from preview_xcf import gimp3_backend,render_xcf
from preview_widget import worker

class Tests(unittest.TestCase):
    def test_modern_xcf_effects_and_cache(self):
        fixture=Path(__file__).parent/'fixtures/modern-gimp3.xcf'
        if gimp3_backend() is None or not fixture.exists():self.skipTest('GIMP-3-Testfixture fehlt')
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_CACHE_HOME=folder):
            before=fixture.read_bytes()
            self.assertGreaterEqual(int(before[10:13]),22)
            pix,_=render_xcf(fixture)
            self.assertEqual(tuple(pix.get_pixels()[:3]),(0,255,255))
            with patch('preview_xcf.subprocess.Popen',side_effect=AssertionError('Use cache')):
                self.assertIn('gespeicherte',render_xcf(fixture)[1])
            self.assertEqual(worker(fixture).get_width(),64)
            self.assertEqual(fixture.read_bytes(),before)
