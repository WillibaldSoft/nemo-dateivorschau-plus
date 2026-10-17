# SPDX-License-Identifier: GPL-3.0-or-later
import os,runpy,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'src'))
import preview_run
from preview_run import render_run_page,clear_cache
from preview_widget import Preview,Gtk
from speed_cache import PreviewCache
from gi.repository import GdkPixbuf

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        images=self.root/'images';images.mkdir()
        for number,color in enumerate((0xff0000ff,0x00ff00ff,0x0000ffff),1):
            pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,80,60);pix.fill(color)
            pix.savev(str(images/(str(number)+'.png')),'png',[],[])
        self.path=self.root/'Fotoshow.run'
        app=__import__('show_test_fixtures').fixture_api()
        app['build'](images,False,self.path,3,False,True,threading.Event(),lambda *args:None)
    def tearDown(self):clear_cache();self.tmp.cleanup()
    def test_navigation_index_once_ram_cache_and_source_invalidation(self):
        original=self.path.read_bytes();cache=PreviewCache()
        with patch('preview_run.call_helper',wraps=preview_run.call_helper) as helper:
            for page,color in [(1,(255,0,0)),(3,(0,0,255)),(2,(0,255,0))]:
                result=cache.get(self.path,'run',page,lambda:render_run_page(self.path,page))
                self.assertEqual(result['pages'],3);self.assertEqual(result['page'],page)
                self.assertEqual(tuple(result['pixbuf'].get_pixels()[:3]),color)
            self.assertEqual(sum(call.args[0][0]=='index' for call in helper.call_args_list),1)
            count=helper.call_count
            cache.get(self.path,'run',1,lambda:render_run_page(self.path,1))
            self.assertEqual(helper.call_count,count)
            self.assertEqual(render_run_page(self.path,999)['page'],3)
            self.assertEqual(render_run_page(self.path,0)['page'],1)
            stamp=self.path.stat();os.utime(self.path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000000))
            render_run_page(self.path,2)
            self.assertEqual(sum(call.args[0][0]=='index' for call in helper.call_args_list),2)
        self.assertEqual(self.path.read_bytes(),original)
        roots=[Path(folder.name) for folder,_ in preview_run.CACHE.values()]
        self.assertTrue(roots);clear_cache();self.assertTrue(all(not root.exists() for root in roots))
    def test_spool_limit_and_failed_archive_cleanup(self):
        with patch.object(preview_run,'MAX_ARCHIVE',512):
            with self.assertRaises(ValueError):preview_run.build_index(self.path,self.root)
        bad=self.root/'unknown.run';bad.write_text('#!/bin/sh\ntouch should-not-run\n')
        with self.assertRaises(ValueError):render_run_page(bad)
        self.assertFalse(preview_run.CACHE)
        self.assertFalse((self.root/'should-not-run').exists())
    def test_archive_cache_eviction_and_total_budget(self):
        render_run_page(self.path,1)
        first_root=Path(next(iter(preview_run.CACHE.values()))[0].name)
        size=next(iter(preview_run.CACHE.values()))[1]['bytes']
        clone=self.root/'clone.run';clone.write_bytes(self.path.read_bytes())
        with patch.object(preview_run,'MAX_ARCHIVE',size+1):
            render_run_page(clone,2)
            self.assertEqual(len(preview_run.CACHE),1)
            self.assertFalse(first_root.exists())
        for n in range(3):
            path=self.root/(str(n)+'.run');path.write_bytes(self.path.read_bytes())
            render_run_page(path,1)
        self.assertEqual(len(preview_run.CACHE),2)

    def test_gtk_image_controls_zoom_and_format_switch(self):
        window=Gtk.OffscreenWindow();pane=Preview(sidebar=True);window.add(pane);window.show_all()
        def pump(predicate):
            end=time.monotonic()+10
            while time.monotonic()<end:
                while Gtk.events_pending():Gtk.main_iteration_do(False)
                if predicate():return
                time.sleep(.01)
            self.fail(pane.status.get_text())
        pane.set_selection(self.path);pump(lambda:pane.pixbuf is not None)
        self.assertTrue(pane.pdf_bar.get_visible());self.assertEqual(pane.pages,3)
        self.assertIn('Bild 1 von 3',pane.status.get_text());self.assertTrue(pane.next.get_sensitive())
        pane.next.clicked();pump(lambda:pane.page==2 and pane.future is None and not pane.timer)
        self.assertEqual(tuple(pane.pixbuf.get_pixels()[:3]),(0,255,0))
        pane.page_spin.set_value(3);pump(lambda:pane.page==3 and pane.future is None and not pane.timer)
        self.assertFalse(pane.next.get_sensitive());self.assertTrue(pane.previous.get_sensitive())
        pane.set_zoom(2);self.assertEqual(pane.zoom,2)
        pane.previous.clicked();pump(lambda:pane.page==2 and pane.future is None and not pane.timer)
        self.assertEqual(pane.zoom,2)
        self.assertFalse(pane.edit.get_visible());self.assertFalse(pane.detail_scroll.get_visible())
        text=self.root/'text.txt';text.write_text('Nach Fotoshow')
        pane.set_selection(text);pump(lambda:pane.text_view.get_buffer().get_char_count()>0)
        self.assertFalse(pane.pdf_bar.get_visible());window.destroy()
