# SPDX-License-Identifier: GPL-3.0-or-later
import os
import sys
import tempfile
import time
from pathlib import Path
import subprocess
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from quick_details import QuickDetails, stamp
from editor import load, read


def pump(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('GTK-Zeitlimit')


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.a, self.b = self.folder / 'a.jpg', self.folder / 'b.jpg'
        for path in (self.a, self.b):
            subprocess.run(['convert', '-size', '120x80', 'xc:blue', str(path)], check=True)
        self.window = Gtk.OffscreenWindow()
        self.editor = QuickDetails()
        self.window.add(self.editor); self.window.show_all()
    def tearDown(self):
        self.window.destroy(); self.tmp.cleanup()
    def select(self, path):
        self.editor.set_path(path)
        pump(lambda: self.editor.original is not None and self.editor.path == path)
    def test_inline_save_drafts_and_target_isolation(self):
        self.select(self.a)
        self.editor.entries[1].set_text('Kamera A')
        self.editor.entries[2].set_text('Objektiv 50 mm')
        self.editor.entries[3].set_text('2026:10:17 12:34:56')
        self.select(self.b)
        self.assertEqual(self.editor.entries[1].get_text(), '')
        self.editor.entries[1].set_text('Kamera B')
        self.select(self.a)
        self.assertEqual(self.editor.entries[1].get_text(), 'Kamera A')
        original = self.a.read_bytes()
        self.editor.store()
        self.editor.set_path(self.b)
        pump(lambda: not self.editor.saving and self.editor.original is not None and self.editor.path == self.b)
        self.assertEqual(load(self.a)[2][1], 'Kamera A')
        self.assertEqual(load(self.a)[2][2], 'Objektiv 50 mm')
        self.assertEqual(load(self.b)[2][1], '')
        self.assertEqual(self.editor.entries[1].get_text(), 'Kamera B')
        self.assertEqual(Path(str(self.a) + '_original').read_bytes(), original)
        self.editor.reset()
        pump(lambda: self.editor.original is not None)
        self.assertEqual(self.editor.entries[1].get_text(), '')
    def test_invalid_date_and_external_change(self):
        self.select(self.a)
        self.editor.entries[3].set_text('2026:02:30 12:00:00')
        self.editor.store()
        self.assertFalse(self.editor.saving)
        self.assertFalse(Path(str(self.a) + '_original').exists())
        self.editor.entries[3].set_text('2026:10:17 12:00:00')
        subprocess.run(['exiftool', '-Model=Extern', str(self.a)], check=True, stdout=subprocess.DEVNULL)
        self.editor.store()
        self.assertIn('zwischenzeitlich', self.editor.note.get_text())
        self.assertEqual(load(self.a)[2][1], 'Extern')
    def test_raw_saves_only_xmp(self):
        path = self.folder / 'test.dng'
        subprocess.run(['convert', str(self.a), 'tiff:' + str(path)], check=True)
        subprocess.run(['exiftool', '-DNGVersion=1.4.0.0', str(path)], check=True, stdout=subprocess.DEVNULL)
        original = path.read_bytes()
        self.select(path)
        self.editor.entries[1].set_text('RAW Kamera')
        self.editor.store()
        pump(lambda: not self.editor.saving and self.editor.original is not None)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(load(path)[2][1], 'RAW Kamera')

if __name__ == '__main__': unittest.main(verbosity=2)
