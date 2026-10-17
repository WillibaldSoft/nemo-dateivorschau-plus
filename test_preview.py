# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME'] = CONFIG_DIR.name
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'nemo')]
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
from preview_image import MAX_EDGE, render
from preview_widget import Preview, settings, worker
from bilddetails_preview import BilddetailsPreview

class File:
    def __init__(self, path, mime='image/jpeg'): self.path, self.mime = path, mime
    def get_uri(self): return self.path.as_uri()
    def is_directory(self): return self.path.is_dir()
    def get_mime_type(self): return self.mime

def pump(predicate, timeout=12):
    stop = time.monotonic() + timeout
    while time.monotonic() < stop:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('GTK timeout')

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.a = self.folder / 'Bild ä $(test).jpg'
        self.b = self.folder / 'blau.png'
        subprocess.run(['convert', '-size', '100x60', 'xc:red', str(self.a)], check=True)
        subprocess.run(['convert', '-size', '120x80', 'xc:blue', str(self.b)], check=True)
    def tearDown(self):
        self.tmp.cleanup()
    def test_decode_orientation_scale_and_readonly(self):
        subprocess.run(['exiftool', '-Orientation#=6', str(self.a)], check=True, stdout=subprocess.DEVNULL)
        digest = hashlib.sha256(self.a.read_bytes()).digest()
        pix = worker(self.a)
        self.assertEqual((pix.get_width(), pix.get_height()), (60, 100))
        self.assertEqual(hashlib.sha256(self.a.read_bytes()).digest(), digest)
        big = self.folder / 'gross.jpg'
        subprocess.run(['convert', '-size', '4000x1000', 'xc:red', str(big)], check=True)
        self.assertEqual(worker(big).get_width(), MAX_EDGE)
    def test_sidebar_resize_toggle_navigation_and_selection(self):
        from gi.repository import GObject
        from nemo_sidebar import WindowState
        import nemo_sidebar
        class Slot(Gtk.Box):
            __gtype_name__ = 'NemoWindowSlot'
        class Toolbar(Gtk.Box):
            __gtype_name__ = 'NemoToolbar'
        current = [self.a, 1]
        original_selection = nemo_sidebar.selection
        nemo_sidebar.selection = lambda *_: tuple(current)
        self.addCleanup(setattr, nemo_sidebar, 'selection', original_selection)
        window = Gtk.OffscreenWindow()
        window.set_default_size(1100, 700)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        window.add(outer)
        toolbar_container = Toolbar()
        toolbar = Gtk.Toolbar(); toolbar_container.add(toolbar)
        outer.pack_start(toolbar_container, False, False, 0)
        slot = Slot(orientation=Gtk.Orientation.VERTICAL)
        outer.pack_start(slot, True, True, 0)
        overlay = Gtk.Overlay(); overlay.add(Gtk.Label(label='Dateiliste'))
        slot.pack_start(overlay, True, True, 0)
        provider = BilddetailsPreview()
        marker = provider.get_widget(self.folder.as_uri(), window)
        slot.pack_start(marker, False, False, 0)
        window.show_all()
        pump(lambda: hasattr(marker, 'controller') and marker.controller.preview.pixbuf is not None)
        controller = marker.controller; pane = controller.preview
        state = controller.state
        self.assertEqual(controller.paned.get_child1(), overlay)
        self.assertEqual(controller.paned.get_child2(), pane)
        self.assertEqual(len(state.buttons), 1)
        total = controller.paned.get_allocated_width()
        controller.paned.set_position(total - 440)
        pump(lambda: settings()['width'] == 440)
        button = state.buttons[0]
        button.set_active(False)
        pump(lambda: not pane.get_mapped())
        self.assertFalse(settings()['visible'])
        button.set_active(True)
        pump(lambda: pane.get_mapped())
        self.assertEqual(controller.width, 440)
        current[0] = self.b
        pump(lambda: pane.pixbuf is not None and pane.path == self.b)
        pane.set_zoom(2)
        self.assertEqual(pane.canvas.get_size_request(), (240, 160))
        controller.detach()
        detached = state.detached
        pump(lambda: detached.preview.pixbuf is not None)
        # Changing the location marker must reuse the same sidebar/splitter.
        slot.remove(marker); marker.destroy()
        marker2 = provider.get_widget(self.folder.as_uri(), window)
        slot.pack_start(marker2, False, False, 0); marker2.show()
        pump(lambda: hasattr(marker2, 'controller'))
        self.assertIs(marker2.controller, controller)
        self.assertEqual(len(state.buttons), 1)
        current[0] = self.a
        pump(lambda: pane.path == self.a and detached.preview.path == self.a)
        current[:] = [None, 0]
        pump(lambda: pane.path is None)
        self.assertIsNone(detached.preview.path)
        window.destroy()
        self.assertTrue(controller.closed)
        self.assertEqual(len(state.slots), 0)
        self.assertTrue(pane.closed)

    def test_preview_background_uses_theme_colors(self):
        import cairo
        pane = Preview(sidebar=True)
        window = Gtk.OffscreenWindow(); window.add(pane); window.show_all()
        context = pane.canvas.get_style_context()
        provider = Gtk.CssProvider()
        context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        for color, expected in [('#224466', (102, 68, 34, 255)), ('#101820', (32, 24, 16, 255))]:
            provider.load_from_data(('@define-color theme_base_color ' + color + '; .view { background-color: ' + color + '; }').encode())
            while Gtk.events_pending(): Gtk.main_iteration_do(False)
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 32, 32)
            pane.draw(pane.canvas, cairo.Context(surface))
            surface.flush()
            self.assertEqual(tuple(surface.get_data()[:4]), expected)
        window.destroy()

    def test_invalid_file(self):
        bad = self.folder / 'bad.jpg'; bad.write_text('kein Bild')
        with self.assertRaises(ValueError): worker(bad)

if __name__ == '__main__': unittest.main(verbosity=2)
