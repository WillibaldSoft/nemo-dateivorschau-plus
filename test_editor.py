# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from editor import FIELDS, argument_path, load, read, save, validate
from details import report

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'Bild ä $(test) " name.jpg'
        subprocess.run(['convert', '-size', '12x8', 'xc:blue', str(self.path)], check=True)
    def tearDown(self):
        self.tmp.cleanup()
    def digest(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()
    def test_embedded_backup_and_pixels(self):
        original = self.path.read_bytes()
        pixels = subprocess.check_output(['convert', str(self.path), 'rgb:-'])
        kind, companion, before = load(self.path)
        self.assertEqual(kind, 'JPEG')
        after = ['Hersteller', 'Kamera 42', 'Objektiv 50', '2026:10:17 20:00:00',
                 'André', '© Test', 'Grüße & <Test>', 'Titel', 'Urlaub; Natur',
                 '200', '2.8', '1/125', '50']
        save(self.path, kind, companion, before, after, False)
        self.assertEqual(Path(str(self.path) + '_original').read_bytes(), original)
        data = read(self.path)
        self.assertEqual(data['IFD0:Model'], 'Kamera 42')
        self.assertEqual(data['XMP-tiff:Model'], 'Kamera 42')
        self.assertEqual(data['XMP-dc:Subject'], ['Urlaub', 'Natur'])
        self.assertEqual(data['XMP-dc:Description'], 'Grüße & <Test>')
        self.assertEqual(subprocess.check_output(['convert', str(self.path), 'rgb:-']), pixels)
        kind, companion, before = load(self.path)
        after = before[:]; after[1] = 'Kamera 43'
        save(self.path, kind, companion, before, after, False)
        self.assertEqual(Path(str(self.path) + '_original').read_bytes(), original)
        self.assertIn('Kamera 43', report(self.path))
        before = load(self.path)[2]; after = before[:]; after[1] = ''
        save(self.path, kind, companion, before, after, False)
        self.assertNotIn('IFD0:Model', read(self.path))
        self.assertNotIn('XMP-tiff:Model', read(self.path))
    def test_sidecar_and_existing_history(self):
        digest = self.digest(self.path)
        kind, companion, before = load(self.path)
        after = before[:]; after[1] = 'XMP Kamera'; after[8] = 'eins; zwei'
        save(self.path, kind, companion, before, after, True)
        self.assertEqual(self.digest(self.path), digest)
        self.assertEqual(load(self.path, True)[2][1], 'XMP Kamera')
        self.assertEqual(load(self.path, False)[2][1], '')
        subprocess.run(['exiftool', '-XMP-xmp:Label=Erhalten', str(companion)], check=True, stdout=subprocess.DEVNULL)
        before = load(self.path, True)[2]; after = before[:]; after[1] = 'Neu'
        save(self.path, kind, companion, before, after, True)
        self.assertEqual(read(companion)['XMP-xmp:Label'], 'Erhalten')
        with self.assertRaises(ValueError):
            save(self.path, 'NEF', companion, before, after, False)
    def test_formats(self):
        for suffix in ('png', 'tif', 'webp'):
            path = self.path.with_suffix('.' + suffix)
            subprocess.run(['convert', str(self.path), str(path)], check=True)
            kind, companion, before = load(path)
            after = before[:]; after[1] = 'Format Test'
            save(path, kind, companion, before, after, False)
            self.assertEqual(load(path)[2][1], 'Format Test')
    def test_dng_sidecar_default(self):
        path = self.path.with_suffix('.dng')
        subprocess.run(['convert', str(self.path), 'tiff:' + str(path)], check=True)
        subprocess.run(['exiftool', '-DNGVersion=1.4.0.0', str(path)], check=True, stdout=subprocess.DEVNULL)
        kind, companion, before = load(path)
        self.assertEqual(kind, 'DNG')
        digest = self.digest(path)
        after = before[:]; after[1] = 'RAW Kamera'
        save(path, kind, companion, before, after, True)
        self.assertEqual(load(path)[2][1], 'RAW Kamera')
        self.assertEqual(self.digest(path), digest)

    def test_validation_and_uri(self):
        self.assertEqual(argument_path(self.path.as_uri()), self.path)
        for value, kind in [('2026:02:30 12:00:00', 'date'), ('nan', 'positive'), ('1/0', 'fraction'), ('0', 'iso'), ('a\n-tag=x', 'text')]:
            with self.assertRaises(ValueError): validate(value, kind)
        validate('2026:10:17 12:00:00+02:00', 'date')
        validate('1/125', 'fraction')

if __name__ == '__main__': unittest.main(verbosity=2)
