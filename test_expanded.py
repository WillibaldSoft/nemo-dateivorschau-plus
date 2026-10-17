# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
import gzip
import tarfile
import io
sys.path[:0] = [str(Path(__file__).parent / 'src'), str(Path(__file__).parent)]
from preview_document import kind
from preview_extra import archive_info, epub_text, media_preview, file_info
from preview_office import render_office
from formats import OFFICE_SUFFIXES
from preview_widget import Preview, Gtk
import time
from office_test_fixtures import make_suite


class Tests(unittest.TestCase):
    def setUp(self): self.temp = tempfile.TemporaryDirectory(); self.folder = Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()
    def test_presentations_drawings_formula_and_templates(self):
        fixtures = make_suite(self.folder)
        self.assertTrue({'.ppt', '.pptx', '.odp'} <= {p.suffix for p in fixtures})
        for path in fixtures:
            with self.subTest(format=path.suffix):
                self.assertIn(path.suffix, OFFICE_SUFFIXES)
                self.assertEqual(kind(path), 'office')
                original = path.read_bytes()
                first = render_office(path, 1)
                self.assertGreater(first['pixbuf'].get_width(), 0)
                if path.suffix in ('.ppt', '.pptx', '.odp', '.ppsx', '.potx', '.otp', '.fodp', '.pptm', '.odg', '.otg', '.fodg'):
                    self.assertEqual(first['pages'], 2)
                    self.assertEqual(render_office(path, 2)['page'], 2)
                self.assertEqual(path.read_bytes(), original)
    def test_archives_and_compressed_text(self):
        path = self.folder / 'test.zip'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('bericht.txt', 'Hallo'); z.writestr('../keine-extraktion.txt', 'Inhalt')
        original = path.read_bytes(); text = archive_info(path)['text']
        self.assertIn('bericht.txt', text)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.folder.parent / 'keine-extraktion.txt').exists())
        tar = self.folder / 'test.tar.gz'
        with tarfile.open(tar, 'w:gz') as archive:
            info = tarfile.TarInfo('daten.csv'); data = b'a,b\n1,2'; info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        self.assertIn('daten.csv', archive_info(tar)['text'])
        raw = self.folder / 'test.txt.gz'
        with gzip.open(raw, 'wb') as stream: stream.write('Komprimierte Grüße'.encode())
        self.assertIn('Grüße', archive_info(raw)['text'])
        seven = self.folder / 'test.7z'
        subprocess.run(['7z', 'a', str(seven), str(raw)], check=True, stdout=subprocess.DEVNULL)
        self.assertIn('test.txt.gz', archive_info(seven)['text'])
    def test_epub_spine_and_no_script_execution(self):
        path = self.folder / 'test.epub'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="OEBPS/book.opf"/></rootfiles></container>')
            z.writestr('OEBPS/book.opf', '<package><metadata><title>Testbuch</title></metadata><manifest><item id="a" href="a.xhtml"/><item id="b" href="b.xhtml"/></manifest><spine><itemref idref="b"/><itemref idref="a"/></spine></package>')
            z.writestr('OEBPS/a.xhtml', '<html><p>Kapitel A</p><script>Nicht anzeigen</script></html>')
            z.writestr('OEBPS/b.xhtml', '<html><h1>Kapitel B</h1></html>')
        value = epub_text(path)['text']
        self.assertLess(value.index('Kapitel B'), value.index('Kapitel A'))
        self.assertNotIn('Nicht anzeigen', value)
        self.assertEqual(kind(path), 'epub')
    def test_media_and_unknown_file_info(self):
        audio = self.folder / 'test.wav'
        subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', str(audio)], check=True)
        self.assertEqual(kind(audio), 'audio')
        self.assertIn('Dauer:', media_preview(audio)['text'])
        video = self.folder / 'test.mp4'
        subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:d=1', '-c:v', 'mpeg4', str(video)], check=True)
        self.assertEqual(kind(video), 'video')
        self.assertEqual(media_preview(video, True)['kind'], 'video')
        unknown = self.folder / 'test.bin'; unknown.write_bytes(b'\0\xff\0')
        self.assertEqual(kind(unknown), 'info'); self.assertIn('Bytes', file_info(unknown)['text'])

    def test_gtk_archive_video_audio_info_transitions(self):
        archive = self.folder / 'test.zip'
        with zipfile.ZipFile(archive, 'w') as z: z.writestr('text.txt', 'Test')
        audio = self.folder / 'test.wav'
        subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1', str(audio)], check=True)
        video = self.folder / 'test.mp4'
        subprocess.run(['/usr/bin/ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=160x90:d=1', '-c:v', 'mpeg4', str(video)], check=True)
        unknown = self.folder / 'test.bin'; unknown.write_bytes(b'\0\xff')
        window = Gtk.OffscreenWindow(); pane = Preview(sidebar=True)
        window.add(pane); window.show_all()
        for path, expected_stack in [(archive, 'text'), (video, 'image'), (audio, 'text'), (unknown, 'text')]:
            pane.set_selection(path)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                ready = pane.pixbuf is not None if expected_stack == 'image' else pane.text_view.get_buffer().get_char_count() > 0
                if ready and pane.future is None and not pane.timer: break
                time.sleep(.02)
            else: self.fail(pane.status.get_text())
            self.assertEqual(pane.stack.get_visible_child_name(), expected_stack)
            self.assertFalse(pane.detail_scroll.get_visible())
            self.assertFalse(pane.edit.get_visible())
            self.assertFalse(pane.pdf_bar.get_visible())
            self.assertTrue(pane.open_button.get_sensitive())
        window.destroy()

if __name__ == '__main__': unittest.main(verbosity=2)
