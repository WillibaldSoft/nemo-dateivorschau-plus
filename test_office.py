# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from preview_document import kind
from preview_office import render_office, CACHE, MAX_SOURCE
from preview_widget import Preview, Gtk
from xml.sax.saxutils import escape


def make_docx(path, title='Office Vorschau'):
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + escape(title) + '</w:t></w:r></w:p><w:p><w:r><w:br w:type="page"/><w:t>Seite zwei mit Text</w:t></w:r></w:p><w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>')


def make_odt(path):
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        z.writestr('mimetype', 'application/vnd.oasis.opendocument.text', compress_type=ZIP_STORED)
        z.writestr('META-INF/manifest.xml', '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2"><manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/><manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>')
        z.writestr('content.xml', '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" office:version="1.2"><office:automatic-styles><style:style style:name="Break" style:family="paragraph"><style:paragraph-properties fo:break-before="page"/></style:style></office:automatic-styles><office:body><office:text><text:p>ODT Vorschau erste Seite</text:p><text:p text:style-name="Break">ODT zweite Seite</text:p></office:text></office:body></office:document-content>')


def make_xlsx(path):
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' + ''.join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i for i in (1, 2)) + '</Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Tabelle 1" sheetId="1" r:id="r1"/><sheet name="Tabelle 2" sheetId="2" r:id="r2"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join('<Relationship Id="r%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i) for i in (1, 2)) + '</Relationships>')
        for i in (1, 2):
            z.writestr('xl/worksheets/sheet%d.xml' % i, '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="1" width="28" customWidth="1"/></cols><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Tabelle %d</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>Betrag</t></is></c><c r="B2"><v>%d</v></c></row></sheetData></worksheet>' % (i, 100 * i))


def pump(predicate, timeout=45):
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
    def test_docx_odt_xlsx_conversion_pages_readonly_and_cache(self):
        for suffix, maker in [('.docx', make_docx), ('.odt', make_odt), ('.xlsx', make_xlsx)]:
            path = self.folder / ('Test ä $(x)' + suffix); maker(path)
            self.assertEqual(kind(path), 'office')
            before = path.read_bytes(); listing = set(self.folder.iterdir())
            one = render_office(path, 1); two = render_office(path, 2)
            self.assertEqual(one['pages'], 2)
            self.assertEqual(two['page'], 2)
            self.assertNotEqual(one['pixbuf'].get_pixels(), two['pixbuf'].get_pixels())
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(set(self.folder.iterdir()), listing)
            entries = [key for key in CACHE if key[0] == str(path)]
            self.assertEqual(len(entries), 1)
        self.assertLessEqual(len(CACHE), 3)
    def test_cache_invalidation_limits_and_invalid_file(self):
        path = self.folder / 'version.docx'; make_docx(path, 'Version eins')
        first = render_office(path)['pixbuf'].get_pixels()
        make_docx(path, 'VERSION ZWEI')
        self.assertNotEqual(render_office(path)['pixbuf'].get_pixels(), first)
        bad = self.folder / 'defekt.docx'; bad.write_bytes(b'\0kein Office')
        with self.assertRaises(ValueError): render_office(bad)
        big = self.folder / 'gross.xlsx'
        with big.open('wb') as stream: stream.truncate(MAX_SOURCE + 1)
        with self.assertRaises(ValueError): render_office(big)
    def test_legacy_doc_and_xls(self):
        # Export genuine OLE/CFB Word 97 and Excel 97 fixtures, not renamed XML.
        for suffix, maker, legacy, export_filter in [
            ('.docx', make_docx, '.doc', 'doc:MS Word 97'),
            ('.xlsx', make_xlsx, '.xls', 'xls:MS Excel 97')]:
            source = self.folder / ('alt' + suffix); maker(source)
            profile = self.folder / ('profil-' + legacy[1:])
            converted = subprocess.run(['/usr/bin/libreoffice', '-env:UserInstallation=' + profile.as_uri(),
                '--headless', '--convert-to', export_filter, '--outdir', str(self.folder), str(source)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                env=dict(os.environ, SAL_USE_VCLPLUGIN='svp', GSETTINGS_BACKEND='memory'))
            path = source.with_suffix(legacy)
            self.assertEqual(converted.returncode, 0, converted.stderr.decode(errors='replace'))
            self.assertTrue(path.exists(), converted.stdout.decode(errors='replace'))
            original = path.read_bytes()
            self.assertTrue(original.startswith(bytes.fromhex('d0cf11e0a1b11ae1')))
            self.assertEqual(kind(path), 'office')
            result = render_office(path, 1)
            self.assertEqual(result['pages'], 2)
            self.assertEqual(render_office(path, 2)['page'], 2)
            self.assertEqual(path.read_bytes(), original)

    def test_gtk_office_pages_and_hidden_camera_fields(self):
        path = self.folder / 'test.docx'; make_docx(path)
        text = self.folder / 'test.txt'; text.write_text('Text nach Office')
        window = Gtk.OffscreenWindow(); pane = Preview(sidebar=True)
        window.add(pane); window.show_all(); pane.set_selection(path)
        pump(lambda: pane.pixbuf is not None and pane.pages == 2)
        self.assertTrue(pane.pdf_bar.get_visible())
        self.assertFalse(pane.detail_scroll.get_visible())
        self.assertFalse(pane.edit.get_visible())
        pane.change_page(2)
        pump(lambda: pane.future is None and not pane.timer and pane.page == 2)
        self.assertIn('Office', pane.status.get_text())
        pane.set_zoom(2); self.assertGreater(pane.canvas.get_size_request()[0], 1000)
        pane.set_selection(text)
        pump(lambda: pane.text_view.get_buffer().get_char_count() > 0)
        self.assertEqual(pane.stack.get_visible_child_name(), 'text')
        self.assertFalse(pane.pdf_bar.get_visible())
        window.destroy()

if __name__ == '__main__': unittest.main(verbosity=2)
