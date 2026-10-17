#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only metadata viewer. URIs avoid shell quoting ambiguities in Nemo."""
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, unquote_to_bytes


def visible(value):
    # Keep metadata and unusual names from introducing fake lines/control sequences.
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return ''.join(c if c.isprintable() else repr(c)[1:-1] for c in str(value))


def local_path(uri):
    parts = urlsplit(uri)
    if parts.scheme != 'file' or parts.netloc not in ('', 'localhost'):
        raise ValueError('Nur lokale Dateien werden unterstützt; Netzwerkdatei zuerst lokal kopieren.')
    return Path(os.fsdecode(unquote_to_bytes(parts.path)))


def metadata(path):
    # Absolute paths, argument array, no shell; no write options or user config.
    result = subprocess.run(
        ['exiftool', '-config', '', '-json', '-G0:1', '-a', '-s',
         '-charset', 'filename=UTF8', str(path.absolute())],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45)
    try:
        data = json.loads(result.stdout)[0]
    except (ValueError, IndexError, TypeError):
        raise ValueError(result.stderr.decode('utf-8', 'replace').strip() or 'Keine lesbaren Metadaten.')
    if result.returncode and not any(k.endswith(':Error') for k in data):
        data['Viewer:Error'] = result.stderr.decode('utf-8', 'replace').strip() or 'ExifTool meldet einen Fehler.'
    return data


def report(path):
    lines = [visible(path.name), '═' * 64]
    def row(label, value):
        lines.append(f'{label:22} {visible(value)}')
    def section(title):
        lines.extend(['', title, '─' * 64])
    try:
        stat = path.stat()
        if not path.is_file():
            raise ValueError('Keine reguläre Datei.')
        section('DATEI')
        row('Name:', path.name)
        row('Speicherort:', path.parent)
        row('Größe:', f'{stat.st_size:,} Bytes ({stat.st_size / 1048576:.2f} MiB)')
        row('Geändert (lokal):', datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(' ', timespec='seconds'))
        data = metadata(path)
        def get(*names):
            for name in names:
                for key, value in data.items():
                    if key.split(':')[-1] == name and value is not None and value != '':
                        return value
            return 'Nicht vorhanden'
        row('Format:', get('FileType'))
        row('MIME-Typ:', get('MIMEType'))
        row('Breite (Pixel):', get('ExifImageWidth', 'ImageWidth', 'RawImageWidth'))
        row('Höhe (Pixel):', get('ExifImageHeight', 'ImageHeight', 'RawImageHeight'))
        row('Ausrichtung:', get('Orientation'))
        section('AUFNAHME')
        for label, names in [
            ('Aufnahmedatum:', ('SubSecDateTimeOriginal', 'DateTimeOriginal', 'CreateDate')),
            ('Hersteller:', ('Make',)), ('Kamera:', ('Model',)),
            ('Objektiv:', ('LensID', 'LensModel', 'Lens', 'LensInfo')),
            ('Brennweite:', ('FocalLength',)), ('Belichtungszeit (s):', ('ExposureTime',)),
            ('Blende (f/):', ('FNumber', 'Aperture')), ('ISO:', ('ISO', 'PhotographicSensitivity'))]:
            row(label, get(*names))
        section('GPS')
        row('Breitengrad:', get('GPSLatitude'))
        row('Breitenrichtung:', get('GPSLatitudeRef'))
        row('Längengrad:', get('GPSLongitude'))
        row('Längenrichtung:', get('GPSLongitudeRef'))
        row('Höhe:', get('GPSAltitude'))
        section('METADATEN / BEGLEITDATEIEN')
        for group in ('EXIF', 'XMP'):
            row(group + ' im Bild:', 'Vorhanden' if any(k.startswith(group + ':') for k in data) else 'Nicht gefunden')
        candidates = {Path(str(path) + '.xmp'), path.with_suffix('.xmp')}
        # Include uppercase sidecars and Darktable duplicate versions (_01 etc.).
        import re
        pattern = re.compile(re.escape(path.stem) + r'_\d+' + re.escape(path.suffix) + r'\.xmp$', re.I)
        try:
            for entry in path.parent.iterdir():
                if entry.name.lower() in {p.name.lower() for p in candidates} or pattern.fullmatch(entry.name):
                    candidates.add(entry)
            found = sorted((p for p in candidates if p.is_file()), key=str)
            if not found:
                row('XMP-Begleitdateien:', 'Keine gefunden')
            for sidecar in found:
                row('XMP-Begleitdatei:', sidecar.name)
                try:
                    side = metadata(sidecar)
                    dark = any('XMP-darktable' in key for key in side)
                    row('Darktable:', 'Namespace erkannt' if dark else 'Nicht nachgewiesen (Dateiname allein ist kein Nachweis)')
                    for key, value in side.items():
                        if key.endswith(':Error'):
                            row('XMP-Lesefehler:', value)
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    row('XMP-Lesefehler:', str(exc))
        except OSError as exc:
            row('Begleitdateien:', str(exc))
        for key, value in data.items():
            if key.split(':')[-1] in ('Error', 'Warning'):
                row('ExifTool-Hinweis:', value)
        lines.extend(['', 'Fehlende Angaben sind normal und hängen vom Dateiformat ab.',
                      'Aufnahmezeit: Zeitzone nur, soweit in Metadaten enthalten.'])
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        row('Lesefehler:', str(exc))
    return '\n'.join(lines)

