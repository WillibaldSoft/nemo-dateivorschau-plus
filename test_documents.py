# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from preview_document import kind, read_text, render_pdf, TEXT_LIMIT
from preview_widget import Preview, Gtk


def make_pdf(path):
    """Two real, standalone PDF pages without optional test dependencies."""
    streams = [b'BT /F1 20 Tf 35 350 Td (PDF Seite 1) Tj ET',
               b'0.2 0.5 0.8 rg 20 20 260 260 re f BT /F1 20 Tf 35 350 Td (PDF Seite 2) Tj ET']
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    objects += [b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream' for stream in streams]
    document = b'%PDF-1.4\n'; offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(document)); document += str(index).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(document)
    document += b'xref\n0 8\n0000000000 65535 f \n'
    document += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    document += b'trailer\n<< /Size 8 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'
    path.write_bytes(document)


def pump(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('GTK-Zeitlimit')


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.folder = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_text_encodings_limits_and_binary_rejection(self):
        path = self.folder / 'Text ä.txt'
        for encoding in ('utf-8', 'utf-16', 'utf-32', 'cp1252'):
            path.write_bytes('Grüße\nTesttext'.encode(encoding))
            self.assertEqual(read_text(path)['text'], 'Grüße\nTesttext')
        path.write_bytes(b'a' * (TEXT_LIMIT + 10))
        result = read_text(path)
        self.assertIn('erste 1 MiB', result['note']); self.assertLess(len(result['text']), 5000)
        path.write_bytes(b'\0binary')
        with self.assertRaises(ValueError): read_text(path)
        path.write_bytes(b''); self.assertEqual(read_text(path)['text'], '')
    def test_pdf_pages_limits_and_readonly(self):
        path = self.folder / 'Test ä.pdf'; make_pdf(path)
        digest = hashlib.sha256(path.read_bytes()).digest()
        first, second = render_pdf(path, 1), render_pdf(path, 2)
        self.assertEqual((first['page'], second['page'], second['pages']), (1, 2, 2))
        self.assertLessEqual(max(first['pixbuf'].get_width(), first['pixbuf'].get_height()), 2560)
        self.assertNotEqual(first['pixbuf'].get_pixels(), second['pixbuf'].get_pixels())
        self.assertEqual(render_pdf(path, 999)['page'], 2)
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest)
        path.write_bytes(b'kein PDF')
        with self.assertRaises(ValueError): render_pdf(path)
    def test_file_type_recognition(self):
        for name, expected in [('bild.JPG', 'image'), ('dokument.PDF', 'pdf'), ('log.txt', 'text'), ('daten.json', 'text')]:
            self.assertEqual(kind(self.folder / name), expected)
        path = self.folder / 'README'; path.write_text('Text ohne Dateiendung')
        self.assertEqual(kind(path), 'text')
        path = self.folder / 'unbekannt.bin'; path.write_bytes(b'\0\xff\0\x01')
        self.assertEqual(kind(path), 'info')
    def test_gtk_pdf_navigation_text_zoom_and_image_only_metadata(self):
        image, pdf, text = self.folder / 'bild.jpg', self.folder / 'test.pdf', self.folder / 'test.txt'
        subprocess.run(['convert', '-size', '120x80', 'xc:blue', str(image)], check=True)
        make_pdf(pdf); text.write_text('<html>Nur Text – kein HTML-Rendering</html>\nZeile 2')
        window = Gtk.OffscreenWindow(); window.set_default_size(500, 800)
        pane = Preview(sidebar=True); window.add(pane); window.show_all()
        pane.set_selection(image)
        pump(lambda: pane.pixbuf is not None and pane.quick_details.original is not None)
        self.assertTrue(pane.detail_scroll.get_visible())
        pane.set_selection(pdf)
        pump(lambda: pane.pages == 2 and pane.pixbuf is not None)
        self.assertFalse(pane.detail_scroll.get_visible()); self.assertFalse(pane.edit.get_visible())
        self.assertTrue(pane.pdf_bar.get_visible())
        first = pane.pixbuf.get_pixels()
        pane.change_page(2)
        pump(lambda: pane.future is None and not pane.timer and pane.page == 2 and pane.pixbuf.get_pixels() != first)
        pane.set_zoom(2); self.assertGreater(pane.canvas.get_size_request()[0], 1000)
        pane.change_page(1)
        pump(lambda: pane.future is None and not pane.timer and pane.page == 1)
        # A pending PDF render must never replace a newly selected text file.
        pane.change_page(2); pane.set_selection(text)
        pump(lambda: 'Nur Text' in pane.text_view.get_buffer().get_text(pane.text_view.get_buffer().get_start_iter(), pane.text_view.get_buffer().get_end_iter(), True))
        self.assertEqual(pane.stack.get_visible_child_name(), 'text')
        self.assertFalse(pane.pdf_bar.get_visible()); self.assertFalse(pane.detail_scroll.get_visible())
        pane.zoom_by(1.25); self.assertGreater(pane.text_points, 11)
        pane.set_zoom(0); self.assertEqual(pane.text_points, 11)
        pane.set_selection(image)
        pump(lambda: pane.pixbuf is not None and pane.quick_details.original is not None)
        self.assertTrue(pane.detail_scroll.get_visible()); self.assertTrue(pane.edit.get_visible())
        window.destroy()

if __name__ == '__main__': unittest.main(verbosity=2)
