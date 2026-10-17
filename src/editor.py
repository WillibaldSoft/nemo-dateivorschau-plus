# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit tag allowlist; no shell, user config, or RAW writes."""
import datetime
import json
import math
from pathlib import Path
import subprocess
from urllib.parse import urlsplit
from details import local_path

# label, embedded tag, sidecar tag, input kind
FIELDS = [
    ('Kamerahersteller', 'EXIF:Make', 'XMP-tiff:Make', 'text'),
    ('Kameramodell', 'EXIF:Model', 'XMP-tiff:Model', 'text'),
    ('Objektivmodell', 'EXIF:LensModel', 'XMP-exifEX:LensModel', 'text'),
    ('Aufnahmedatum', 'EXIF:DateTimeOriginal', 'XMP-exif:DateTimeOriginal', 'date'),
    ('Fotograf / Urheber', 'EXIF:Artist', 'XMP-dc:Creator', 'text'),
    ('Copyright', 'EXIF:Copyright', 'XMP-dc:Rights', 'text'),
    ('Beschreibung', 'EXIF:ImageDescription', 'XMP-dc:Description', 'text'),
    ('Titel', 'XMP-dc:Title', 'XMP-dc:Title', 'text'),
    ('Stichwörter (; getrennt)', 'XMP-dc:Subject', 'XMP-dc:Subject', 'list'),
    ('ISO', 'EXIF:ISO', 'XMP-exif:ISO', 'iso'),
    ('Blende (z. B. 2.8)', 'EXIF:FNumber', 'XMP-exif:FNumber', 'positive'),
    ('Belichtungszeit (z. B. 1/125)', 'EXIF:ExposureTime', 'XMP-exif:ExposureTime', 'fraction'),
    ('Brennweite (mm)', 'EXIF:FocalLength', 'XMP-exif:FocalLength', 'positive'),
]
DIRECT = {'JPEG', 'PNG', 'TIFF', 'WEBP'}

def run(args):
    p = subprocess.run(['exiftool', '-config', '', '-charset', 'filename=UTF8', *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if p.returncode:
        raise ValueError(p.stderr.decode('utf-8', 'replace').strip() or p.stdout.decode('utf-8', 'replace').strip() or 'ExifTool-Fehler')
    return p

def read(path):
    return json.loads(run(['-j', '-G1', '-s', str(path.absolute())]).stdout)[0]

def argument_path(value):
    if urlsplit(value).scheme == 'file':
        return local_path(value)
    return Path(value).absolute()

def sidecar(path):
    # Follow Darktable's complete-filename convention; also honor an existing stem.xmp.
    full = Path(str(path) + '.xmp')
    stem = path.with_suffix('.xmp')
    for candidate in (full, stem):
        if candidate.is_file():
            return candidate
    # Honor uppercase spellings without picking numbered Darktable duplicates.
    for candidate in sorted(path.parent.iterdir()):
        if candidate.name.lower() in {full.name.lower(), stem.name.lower()} and candidate.is_file():
            return candidate
    return full

def find(data, tag):
    group, name = tag.split(':', 1)
    if tag in data:
        value = data[tag]
    else:
        keys = [k for k in data if k.endswith(':' + name)]
        if group == 'EXIF':
            keys = [k for k in keys if not k.startswith('XMP-')]
        else:
            keys = [k for k in keys if k.startswith('XMP-')]
        value = data[keys[0]] if keys else ''
    if isinstance(value, list):
        return '; '.join(str(v) for v in value)
    return str(value)

def load(path, use_sidecar=None):
    if not path.is_file():
        raise ValueError('Keine reguläre Datei: ' + str(path))
    data = read(path)
    filetype = data.get('File:FileType', '')
    companion = sidecar(path)
    extra = read(companion) if companion.exists() else {}
    values = []
    for _, embedded, xmp, _ in FIELDS:
        # For RAW, sidecar values override the embedded original, including empty values.
        if (use_sidecar is True or (use_sidecar is None and filetype not in DIRECT)) and any(k.endswith(':' + xmp.split(':')[1]) for k in extra):
            value = find(extra, xmp)
        else:
            value = find(data, embedded) or find(data, xmp)
            if embedded == 'EXIF:LensModel' and not value:
                value = find(data, 'EXIF:LensID') or find(data, 'EXIF:Lens') or find(data, 'EXIF:LensInfo')
        values.append(value)
    return filetype, companion, values

def validate(value, kind):
    if '\x00' in value or '\r' in value or '\n' in value:
        raise ValueError('Bitte nur einzeilige Werte ohne Steuerzeichen eingeben.')
    if not value:
        return
    if kind == 'date':
        # Keep timezone/subseconds from existing metadata; validate date/time strictly.
        import re
        m = re.fullmatch(r'(\d{4})[:-](\d{2})[:-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?', value)
        if not m:
            raise ValueError('Datumsformat: JJJJ:MM:TT HH:MM:SS (optional Zeitzone).')
        datetime.datetime(*map(int, m.groups()))
    elif kind in ('iso', 'positive', 'fraction'):
        try:
            parts = value.split('/') if kind == 'fraction' else [value]
            number = float(parts[0]) / float(parts[1]) if len(parts) == 2 else float(value)
        except (ValueError, ZeroDivisionError):
            raise ValueError('Bitte eine gültige positive Zahl eingeben.') from None
        if not math.isfinite(number) or number <= 0 or (kind == 'iso' and (not value.isdigit() or number > 65535)):
            raise ValueError('Positive Zahl erforderlich; ISO als ganze Zahl zwischen 1 und 65535.')

def save(path, filetype, companion, old, new, use_sidecar):
    changes = []
    for field, before, after in zip(FIELDS, old, new):
        if before != after:
            validate(after, field[3])
            changes.append((field, after))
    if not changes:
        return 'Keine Änderungen.'
    if not use_sidecar and filetype not in DIRECT:
        raise ValueError('Dieses Format wird ausschließlich über XMP-Begleitdateien bearbeitet.')
    target = companion if use_sidecar else path
    if target.is_symlink():
        raise ValueError('Symbolische Verknüpfungen bitte über die tatsächliche Datei bearbeiten.')
    args = ['-P']  # Preserve file modification time; default ExifTool backup remains enabled.
    for (_, embedded, xmp, kind), value in changes:
        tags = [xmp] if use_sidecar or embedded == xmp else [embedded, xmp]
        for tag in tags:
            if kind == 'list':
                args.append('-' + tag + '=')
                args.extend('-' + tag + '+=' + item.strip() for item in value.split(';') if item.strip())
            else:
                args.append('-' + tag + '=' + value)
    result = run([*args, str(target.absolute())])
    warning = result.stderr.decode('utf-8', 'replace').strip()
    return ('Gespeichert: ' + str(target) + '\n'
            + ('Sicherung: ' + str(target) + '_original' if Path(str(target) + '_original').exists()
               else 'Neue XMP-Begleitdatei angelegt; das Bild bleibt unverändert.')
            + ('\nExifTool-Hinweis: ' + warning if warning else ''))
