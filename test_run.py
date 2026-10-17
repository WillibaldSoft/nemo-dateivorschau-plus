# SPDX-License-Identifier: GPL-3.0-or-later
import io,os,runpy,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'src'))
from preview_run import first_image,render_run
from preview_document import kind
from preview_widget import worker
from gi.repository import GdkPixbuf

class Tests(unittest.TestCase):
    def test_real_fotoshow_studio_archive_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);images=root/'input';images.mkdir()
            pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,80,60);pix.fill(0xff0000ff)
            pix.savev(str(images/'first.png'),'png',[],[])
            app=(runpy.run_path('/usr/bin/fotoshow',run_name='test') if Path('/usr/bin/fotoshow').exists() else __import__('show_test_fixtures').fixture_api())
            target=root/'Show ü.run'
            app['build'](images,False,target,3,False,True,threading.Event(),lambda *args:None)
            original=target.read_bytes()
            self.assertEqual(kind(target),'run')
            with patch('subprocess.Popen',side_effect=AssertionError('The archive must never run')):
                data=first_image(target);self.assertTrue(data.startswith(b'\x89PNG'))
                result=render_run(target)
                self.assertEqual(tuple(result.get_pixels()[:3]),(255,0,0))
            self.assertEqual(worker(target).get_width(),80)
            self.assertEqual(target.read_bytes(),original)
            self.assertFalse((root/'Bilder').exists())
    def test_unknown_run_rejected_without_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'unknown.run';sentinel=root/'executed'
            path.write_text('#!/bin/sh\ntouch '+str(sentinel)+'\n')
            with self.assertRaises(ValueError):first_image(path)
            self.assertFalse(sentinel.exists())
