# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only bounded text previews and single-page Poppler rendering."""
import os
import codecs
from pathlib import Path
import re
import subprocess
import tempfile
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gio, GdkPixbuf

from formats import OFFICE_SUFFIXES, ARCHIVES, AUDIO, VIDEO

TEXT_LIMIT = 1024 * 1024
TEXT_SUFFIXES = {'.txt', '.text', '.md', '.markdown', '.tsx', '.jsx', '.rst', '.log', '.csv', '.tsv', '.json', '.jsonl',
                 '.yaml', '.yml', '.xml', '.html', '.htm', '.css', '.js', '.ts', '.py',
                 '.sh', '.bash', '.ini', '.conf', '.cfg', '.toml', '.desktop', '.nemo_action',
                 '.c', '.h', '.cpp', '.hpp', '.rs', '.go', '.java', '.sql', '.tex', '.svg'}


def kind(path):
    from preview_image import RAW
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.run': return 'run'
    if suffix == '.xcf': return 'xcf'
    if suffix == '.ts':
        # MPEG transport stream and TypeScript share this suffix. Inspect only
        # a small header, preserving normal source-code previews.
        try:
            with path.open('rb') as stream: head = stream.read(8192)
            for stride in (188, 192, 204):
                if any(all(head[start + stride*i] == 0x47 for i in range(4))
                       for start in range(min(stride, max(0, len(head)-3*stride)))):
                    return 'video'
            if b'\x00' in head: return 'video'
        except OSError: pass
        return 'text'
    if suffix == '.pdf': return 'pdf'
    if suffix == '.epub': return 'epub'
    if suffix in ARCHIVES: return 'archive'
    if suffix in AUDIO: return 'audio'
    if suffix in VIDEO: return 'video'
    if suffix == '.pot' and path.exists():
        with path.open('rb') as stream:
            if stream.read(32).lstrip().startswith((b'#', b'msgid')): return 'text'
    if suffix in OFFICE_SUFFIXES: return 'office'
    if suffix in RAW | {'.jpg', '.jpeg', '.jpe', '.png', '.tif', '.tiff', '.webp', '.gif', '.bmp', '.heic', '.heif', '.avif', '.jxl', '.svg'}:
        return 'image'
    if suffix in TEXT_SUFFIXES: return 'text'
    content_type, _ = Gio.content_type_guess(str(path), None)
    mime = Gio.content_type_get_mime_type(content_type) if content_type else ''
    if mime == 'application/pdf': return 'pdf'
    if mime and mime.startswith('image/'): return 'image'
    if mime and mime.startswith('text/'): return 'text'
    try:
        with path.open('rb') as stream: head = stream.read(512)
        if head.startswith(b'%PDF-'): return 'pdf'
        if head.startswith((b'\xff\xfe', b'\xfe\xff', b'\xef\xbb\xbf')): return 'text'
        text = head.decode('utf-8')
        if '\x00' not in text and all(c.isprintable() or c in '\n\r\t' for c in text): return 'text'
    except (OSError, UnicodeError): pass
    return 'info'


def read_text(path):
    with Path(path).open('rb') as stream: raw = stream.read(TEXT_LIMIT + 1)
    truncated = len(raw) > TEXT_LIMIT
    raw = raw[:TEXT_LIMIT]
    encoding = 'utf-8-sig'
    if raw.startswith((b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')): encoding = 'utf-32'
    elif raw.startswith((b'\xff\xfe', b'\xfe\xff')): encoding = 'utf-16'
    elif b'\x00' in raw: raise ValueError('Binärdatei: keine Textvorschau.')
    try:
        text = codecs.getincrementaldecoder(encoding)().decode(raw, final=not truncated)
    except UnicodeDecodeError:
        if encoding == 'utf-8-sig':
            try: text = raw.decode('utf-8-sig', errors='strict')
            except UnicodeDecodeError:
                # Common older Windows/German text files. Report the encoding.
                encoding = 'Windows-1252'; text = raw.decode('cp1252', errors='replace')
        else: text = raw.decode(encoding, errors='replace')
    controls = sum(not c.isprintable() and c not in '\r\n\t' for c in text)
    if controls > max(2, len(text) // 100): raise ValueError('Binärdatei: keine Textvorschau.')
    text = ''.join(c if c.isprintable() or c in '\r\n\t' else '\ufffd' for c in text)
    shortened = any(len(line) > 4096 for line in text.splitlines())
    if shortened: text = '\n'.join(line[:4096] + (' … [Zeile gekürzt]' if len(line) > 4096 else '') for line in text.splitlines())
    note = encoding + (' · erste 1 MiB' if truncated else '') + (' · lange Zeilen gekürzt' if shortened else '')
    from text_format import format_text
    return format_text(path, {'kind': 'text', 'text': text, 'note': note})


def render_pdf(path, page=1):
    path = Path(path).absolute()
    env = dict(os.environ, LC_ALL='C')
    info = subprocess.run(['/usr/bin/pdfinfo', str(path)], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15, env=env)
    if info.returncode:
        raise ValueError('PDF kann nicht geöffnet werden (beschädigt oder passwortgeschützt).')
    match = re.search(rb'^Pages:\s+(\d+)\s*$', info.stdout, re.M)
    if not match or int(match[1]) < 1: raise ValueError('Keine PDF-Seiten gefunden.')
    pages = int(match[1]); page = max(1, min(pages, int(page)))
    with tempfile.TemporaryDirectory(prefix='bilddetails-pdf-') as folder:
        output = Path(folder) / 'page'
        rendered = subprocess.run(['/usr/bin/pdftoppm', '-f', str(page), '-l', str(page),
            '-singlefile', '-scale-to', '1600', '-png', str(path), str(output)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=25, env=env)
        if rendered.returncode: raise ValueError('PDF-Seite konnte nicht dargestellt werden.')
        pix = GdkPixbuf.Pixbuf.new_from_file(str(output) + '.png')
    return {'kind': 'pdf', 'pixbuf': pix, 'pages': pages, 'page': page}
