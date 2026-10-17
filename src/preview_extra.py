# SPDX-License-Identifier: GPL-3.0-or-later
"""Useful read-only previews without extracting or launching file contents."""
from pathlib import Path
import datetime
import json
import os
import signal
import subprocess
import tempfile
from html.parser import HTMLParser
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gio, GdkPixbuf


def result(text, note):
    return {'kind': 'text', 'text': text, 'note': note}


def file_info(path):
    path = Path(path)
    stat = path.stat()
    content_type, _ = Gio.content_type_guess(str(path), None)
    mime = Gio.content_type_get_mime_type(content_type) if content_type else 'unbekannt'
    return result(f'{path.name}\n\nDateityp: {mime}\nGröße: {stat.st_size:,} Bytes\nGeändert: {datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(" ", timespec="seconds")}\n\nFür dieses Format steht eine Dateiinformation zur Verfügung. Über das Öffnen-Symbol lässt sich die zuständige Anwendung starten.', 'Dateiinformation')


def archive_info(path):
    # bsdtar/libarchive reads headers only. A separate helper bounds output and
    # wall time even for corrupt or deeply compressed input; never extracts.
    helper = Path(__file__).with_name('archive_list.py')
    p = subprocess.Popen(['/usr/bin/python3', str(helper), str(Path(path).absolute())],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try: output, _ = p.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        try: os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        p.communicate()
        raise ValueError('Zeitlimit beim Lesen des Archiv-Inhalts.') from None
    if p.returncode:
        suffix = Path(path).suffix.lower()
        if suffix in ('.gz', '.bz2', '.xz'):
            import gzip, bz2, lzma
            opener = {'.gz': gzip.open, '.bz2': bz2.open, '.xz': lzma.open}[suffix]
            from preview_document import read_text, TEXT_LIMIT
            with opener(path, 'rb') as stream: data = stream.read(TEXT_LIMIT + 1)
            with tempfile.TemporaryDirectory(prefix='bilddetails-text-') as folder:
                target = Path(folder) / 'text.txt'; target.write_bytes(data)
                preview = read_text(target)
            preview['note'] = 'Komprimierter Text · ' + preview['note']
            return preview
        raise ValueError('Archivinhalt nicht lesbar (verschlüsselt, beschädigt oder nicht unterstützt).')
    return result(output.decode('utf-8', 'replace'), 'Archiv-Inhalt · nur Auflistung, keine Dateien entpackt')


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.output = []; self.skip = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.skip += 1
        if tag in ('p', 'div', 'br', 'h1', 'h2', 'h3', 'li', 'tr'): self.output.append('\n')
    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.skip = max(0, self.skip - 1)
        if tag in ('p', 'div', 'h1', 'h2', 'h3', 'li'): self.output.append('\n')
    def handle_data(self, text):
        if not self.skip: self.output.append(text)


def epub_text(path):
    def bounded(z, name, limit=2 * 1024 * 1024):
        with z.open(name) as stream: data = stream.read(limit + 1)
        if len(data) > limit: raise ValueError('EPUB-Kapitel zu groß für die Lesevorschau.')
        return data
    with ZipFile(path) as z:
        container = ET.fromstring(bounded(z, 'META-INF/container.xml', 65536))
        opf_name = container.find('.//{*}rootfile').attrib['full-path']
        opf = ET.fromstring(bounded(z, opf_name))
        from posixpath import normpath, join, dirname
        manifest = {item.attrib['id']: item.attrib.get('href', '') for item in opf.findall('.//{*}manifest/{*}item')}
        title = opf.find('.//{*}title')
        parts = [title.text if title is not None and title.text else Path(path).name, '\n']
        size = 0; shortened = False
        for item in opf.findall('.//{*}spine/{*}itemref')[:200]:
            href = manifest.get(item.attrib.get('idref'), '').split('#')[0]
            if not href: continue
            from urllib.parse import unquote
            name = normpath(join(dirname(opf_name), unquote(href)))
            if name.startswith('../') or name.startswith('/'): continue
            data = bounded(z, name)
            parser = PlainText(); parser.feed(data.decode('utf-8', 'replace'))
            chapter = ''.join(parser.output)
            remaining = 1024 * 1024 - size
            parts.append(chapter[:remaining]); size += min(len(chapter), remaining)
            if len(chapter) > remaining or size >= 1024 * 1024:
                shortened = True; break
    return result('\n'.join(parts), 'EPUB-Lesevorschau' + (' · gekürzt' if shortened else ''))


def media_preview(path, video=False):
    path = Path(path).absolute()
    p = subprocess.run(['/usr/bin/ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-show_entries', 'format=duration,format_name:format_tags=title,artist,album:stream=codec_type,codec_name,width,height,sample_rate,channels',
        '-of', 'json', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    if p.returncode: raise ValueError('Mediendatei nicht lesbar.')
    info = json.loads(p.stdout); fmt = info.get('format', {})
    duration = float(fmt.get('duration', 0) or 0)
    text = [path.name, '', 'Format: ' + fmt.get('format_name', '?'), f'Dauer: {duration:.1f} Sekunden']
    for key, value in fmt.get('tags', {}).items(): text.append(key + ': ' + str(value))
    for stream in info.get('streams', [])[:12]:
        text.append(stream.get('codec_type', '?') + ': ' + stream.get('codec_name', '?'))
        if 'width' in stream: text.append(f'{stream["width"]} × {stream["height"]} Pixel')
        if 'sample_rate' in stream: text.append(str(stream['sample_rate']) + ' Hz · ' + str(stream.get('channels', '?')) + ' Kanäle')
    if not video: return result('\n'.join(text), 'Audio-Informationen · Öffnen für Wiedergabe')
    with tempfile.TemporaryDirectory(prefix='bilddetails-video-') as folder:
        output = Path(folder) / 'frame.png'
        p = subprocess.run(['/usr/bin/ffmpeg', '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
            '-ss', str(min(10.0, duration * .1)), '-i', str(path), '-frames:v', '1',
            '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease', '-threads', '1', str(output)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        if p.returncode or not output.exists(): return result('\n'.join(text), 'Video-Informationen · kein Standbild verfügbar')
        pix = GdkPixbuf.Pixbuf.new_from_file(str(output))
    return {'kind': 'video', 'pixbuf': pix, 'note': f'Video-Standbild · {duration:.1f} s · Öffnen für Wiedergabe'}
