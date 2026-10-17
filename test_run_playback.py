# SPDX-License-Identifier: GPL-3.0-or-later
import os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).parent/'src'),str(Path(__file__).parent)]
import test_run_navigation as navigation_fixtures
from preview_run import render_run_page,clear_cache
from preview_widget import Preview,Gtk,settings

class Tests(unittest.TestCase):
    def test_original_names_subfolders_jpeg_and_natural_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);payload=root/'payload';images=payload/'Fotos/Urlaub';images.mkdir(parents=True)
            from gi.repository import GdkPixbuf
            for number,color in [(10,0x0000ffff),(2,0x00ff00ff),(1,0xff0000ff)]:
                pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,80,60);pix.fill(color)
                pix.savev(str(images/('Bild '+str(number)+'.JPG')),'jpeg',['quality'],['100'])
            sentinel=root/'executed'
            (payload/'start-diashow.sh').write_text('#!/bin/sh\ntouch '+str(sentinel)+'\n')
            (images/'alias.jpg').symlink_to('/etc/passwd')
            show=root/'alt.run'
            subprocess.run(['makeself','--quiet','--nox11',str(payload),str(show),'Fotoshow','./start-diashow.sh'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            for page,channel in [(1,0),(2,1),(3,2)]:
                result=render_run_page(show,page)
                self.assertEqual(result['pages'],3)
                self.assertGreater(result['pixbuf'].get_pixels()[channel],240)
            self.assertFalse(sentinel.exists());clear_cache()
    def test_background_total_updates_while_paused(self):
        from unittest.mock import patch
        import preview_run
        fixture=navigation_fixtures.Tests('test_gtk_image_controls_zoom_and_format_switch');fixture.setUp()
        window=Gtk.OffscreenWindow();pane=Preview(sidebar=True);window.add(pane);window.show_all()
        try:
            with patch.object(preview_run,'needs_stream',return_value=True):
                pane.set_selection(fixture.path);until=time.monotonic()+8
                while time.monotonic()<until:
                    while Gtk.events_pending():Gtk.main_iteration_do(False)
                    if pane.page_label.get_text()=='/ 3':break
                    time.sleep(.01)
                self.assertEqual(pane.page_label.get_text(),'/ 3')
                self.assertEqual(pane.page,1);self.assertFalse(pane.playing)
                self.assertIn('Bild 1 von 3',pane.status.get_text())
        finally:window.destroy();fixture.tearDown()

    def test_streaming_playback_unknown_total_and_cached_return(self):
        from unittest.mock import patch
        import preview_run
        fixture=navigation_fixtures.Tests('test_gtk_image_controls_zoom_and_format_switch');fixture.setUp()
        window=Gtk.OffscreenWindow();pane=Preview(sidebar=True);window.add(pane);window.show_all()
        def pump(predicate):
            until=time.monotonic()+8
            while time.monotonic()<until:
                while Gtk.events_pending():Gtk.main_iteration_do(False)
                if predicate():return
                time.sleep(.01)
            self.fail(pane.status.get_text())
        try:
            with patch.object(preview_run,'needs_stream',return_value=True):
                pane.set_selection(fixture.path);pump(lambda:pane.pixbuf is not None)
                self.assertEqual(pane.page_label.get_text(),'/ ?')
                pane.duration.set_value(.5);pane.play_button.clicked()
                pump(lambda:pane.page==3 and pane.future is None and not pane.timer)
                pump(lambda:pane.page_label.get_text()=='/ 3')
                pump(lambda:pane.page==1 and pane.future is None and not pane.timer)
                pane.pause_playback()
                pane.page_spin.set_value(3)
                pump(lambda:pane.page==3 and pane.future is None and not pane.timer)
                self.assertEqual(pane.page_label.get_text(),'/ 3')
                self.assertFalse(pane.next.get_sensitive())
        finally:window.destroy();fixture.tearDown()

    def test_play_pause_duration_wrap_selection_and_hide(self):
        fixture=navigation_fixtures.Tests('test_gtk_image_controls_zoom_and_format_switch');fixture.setUp()
        window=Gtk.OffscreenWindow();pane=Preview(sidebar=True);window.add(pane);window.show_all()
        def pump(predicate,timeout=8):
            until=time.monotonic()+timeout
            while time.monotonic()<until:
                while Gtk.events_pending():Gtk.main_iteration_do(False)
                if predicate():return
                time.sleep(.01)
            self.fail(pane.status.get_text())
        try:
            pane.set_selection(fixture.path);pump(lambda:pane.pixbuf is not None)
            self.assertTrue(pane.playback_bar.get_visible());self.assertFalse(pane.playing)
            pane.duration.set_value(.5);self.assertEqual(settings()['slide_seconds'],.5)
            pane.play_button.clicked();self.assertTrue(pane.playing)
            pump(lambda:pane.page==2 and pane.future is None and not pane.timer)
            pane.play_button.clicked();self.assertFalse(pane.playing);self.assertEqual(pane.play_timer,0)
            pane.change_page(3);pump(lambda:pane.page==3 and pane.future is None and not pane.timer)
            pane.play_button.clicked();pump(lambda:pane.page==1 and pane.future is None and not pane.timer)
            pane.hide();self.assertFalse(pane.playing);self.assertEqual(pane.play_timer,0)
            pane.show();pane.play_button.clicked();self.assertTrue(pane.playing)
            text=fixture.root/'text.txt';text.write_text('Stop')
            pane.set_selection(text);self.assertFalse(pane.playing);self.assertFalse(pane.playback_bar.get_visible())
        finally:window.destroy();fixture.tearDown()
