# SPDX-License-Identifier: GPL-3.0-or-later
import sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'src'))
from quick_details import QuickDetails
from editor import load
from gi.repository import Gtk,GdkPixbuf

class Tests(unittest.TestCase):
    def test_keywords_inline_save_and_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bild.jpg'
            pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,20,20);pix.fill(0xff0000ff);pix.savev(str(path),'jpeg',[],[])
            window=Gtk.OffscreenWindow();editor=QuickDetails();window.add(editor);window.show_all();editor.set_path(path)
            def pump(predicate):
                until=time.monotonic()+8
                while time.monotonic()<until:
                    while Gtk.events_pending():Gtk.main_iteration_do(False)
                    if predicate():return
                    time.sleep(.01)
                self.fail(editor.note.get_text())
            pump(lambda:editor.original is not None)
            self.assertIs(editor.entries[8].get_parent(),editor.form)
            editor.entries[8].set_text('Urlaub; Familie; Küste');editor.store()
            pump(lambda:not editor.saving and editor.original is not None and editor.original[8]=='Urlaub; Familie; Küste')
            self.assertEqual(load(path)[2][8],'Urlaub; Familie; Küste')
            self.assertTrue(Path(str(path)+'_original').exists())
            editor.entries[8].set_text('');editor.store()
            pump(lambda:not editor.saving and editor.original is not None and editor.original[8]=='')
            self.assertEqual(load(path)[2][8],'');window.destroy()
