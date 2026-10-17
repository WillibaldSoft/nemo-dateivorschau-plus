# SPDX-License-Identifier: GPL-3.0-or-later
"""Read the first Fotoshow Studio image without ever executing its launcher."""
import gzip
import io
from pathlib import Path, PurePosixPath
import re
import tarfile

IMAGE_SUFFIXES = {'.png','.jpg','.jpeg','.jpe','.webp','.gif','.bmp','.tif','.tiff'}

def image_name(member):
    path = PurePosixPath(member.name)
    if path.is_absolute() or '..' in path.parts or not member.isfile(): return None
    if any(part.startswith('.') for part in path.parts): return None
    if path.suffix.lower() not in IMAGE_SUFFIXES: return None
    return str(path)


def image_order(name):
    return [(1,int(part)) if part.isdigit() else (0,part.casefold()) for part in re.split(r'(\d+)',name)]

MAX_READ = 64 * 1024 * 1024

class Bounded:
    def __init__(self, stream): self.stream, self.remaining = stream, MAX_READ
    def read(self, size=-1):
        if self.remaining <= 0: raise ValueError('Fotoshow-Vorschau: Leselimit erreicht.')
        data = self.stream.read(min(self.remaining, size if size >= 0 else self.remaining))
        self.remaining -= len(data)
        return data


def first_image(path):
    with Path(path).open('rb') as stream:
        header = stream.read(256 * 1024)
        if not header.startswith(b'#!/bin/sh') or b'generated using Makeself' not in header[:2048]:
            raise ValueError('Keine unterstützte Fotoshow-Studio-/Makeself-Datei.')
        match = re.search(rb'^skip="([0-9]{1,5})"\r?$',header,re.M)
        if not match: raise ValueError('Archivbeginn nicht erkennbar.')
        lines = header.splitlines(keepends=True); skip = int(match[1])
        if skip < 1 or skip >= len(lines): raise ValueError('Fotoshow-Header zu groß oder beschädigt.')
        stream.seek(sum(map(len,lines[:skip])))
        if stream.read(2) != b'\x1f\x8b': raise ValueError('Nur gzip-gepackte Fotoshow-Archive werden unterstützt.')
        stream.seek(-2,1)
        with gzip.GzipFile(fileobj=stream) as zipped:
            with tarfile.open(fileobj=Bounded(zipped),mode='r|') as archive:
                for index,member in enumerate(archive):
                    if index >= 500: break
                    name = image_name(member)
                    if name is None: continue
                    if not member.isfile() or member.size > 32 * 1024 * 1024: continue
                    with archive.extractfile(member) as image:
                        data = image.read(32 * 1024 * 1024 + 1)
                    if len(data) > 32 * 1024 * 1024: raise ValueError('Show-Bild zu groß.')
                    return data
    raise ValueError('Kein passendes Bild am Anfang der Fotoshow gefunden.')


def render_run(path):
    from preview_image import decode
    return decode(first_image(path))

# Navigation cache: decompress each show once into an opaque private tar spool.
# No member path is ever extracted or executed.
import atexit
from collections import OrderedDict
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
from run_stream import Client, needs_stream

MAX_ARCHIVE = 512 * 1024 * 1024
MAX_IMAGES = 5000
CACHE = OrderedDict()
LOCK = threading.Lock()


def fingerprint(path):
    s = path.stat()
    return str(path), s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def build_index(path, root):
    with path.open('rb') as source:
        header = source.read(256 * 1024)
        if not header.startswith(b'#!/bin/sh') or b'generated using Makeself' not in header[:2048]:
            raise ValueError('Keine unterstützte Fotoshow-Studio-/Makeself-Datei.')
        match = re.search(rb'^skip="([0-9]{1,5})"\r?$',header,re.M)
        lines = header.splitlines(keepends=True)
        skip = int(match[1]) if match else 0
        if skip < 1 or skip >= len(lines): raise ValueError('Fotoshow-Header nicht lesbar.')
        source.seek(sum(map(len,lines[:skip])))
        if source.read(2) != b'\x1f\x8b': raise ValueError('Nur gzip-Fotoshows werden unterstützt.')
        source.seek(-2,1)
        size = 0
        with gzip.GzipFile(fileobj=source) as zipped, (root/'archive.tar').open('wb') as spool:
            while True:
                chunk = zipped.read(min(1024 * 1024, MAX_ARCHIVE - size + 1))
                if not chunk: break
                size += len(chunk)
                if size > MAX_ARCHIVE: raise ValueError('Fotoshow über 512 MiB entpackte Archivdaten; bitte extern öffnen.')
                spool.write(chunk)
    images = {}
    with tarfile.open(root/'archive.tar',mode='r:') as archive:
        for number, member in enumerate(archive):
            if number >= 10000: raise ValueError('Zu viele Archiveinträge (maximal 10000).')
            name = image_name(member)
            if name is None: continue
            if not member.isfile(): continue
            if not 0 < member.size <= 32 * 1024 * 1024:
                raise ValueError('Ein Fotoshow-Bild überschreitet 32 MiB.')
            if name in images: raise ValueError('Doppelte Bildnamen im Fotoshow-Archiv.')
            if member.offset_data < 0 or member.offset_data + member.size > size:
                raise ValueError('Beschädigter Archivinhalt.')
            images[name] = [member.offset_data,member.size]
            if len(images) > MAX_IMAGES: raise ValueError('Maximal 5000 Bilder pro Fotoshow.')
    if not images: raise ValueError('Keine Bilder im Fotoshow-Studio-Format gefunden.')
    data = {'images': [images[name] for name in sorted(images,key=image_order)], 'bytes': size}
    (root/'index.json').write_text(json.dumps(data))


def call_helper(arguments):
    process = subprocess.Popen(['/usr/bin/python3',str(Path(__file__).absolute()),*map(str,arguments)],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
    try:
        _, error = process.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.communicate()
        raise ValueError('Fotoshow-Vorschau nach 20 Sekunden abgebrochen.') from None
    if process.returncode:
        raise ValueError(error.decode('utf-8','replace').strip()[-1000:] or 'Fotoshow nicht lesbar.')


def clear_cache():
    with LOCK:
        for folder, index in CACHE.values():
            if 'client' in index: index['client'].close()
            folder.cleanup()
        CACHE.clear()


atexit.register(clear_cache)


def render_run_page(path, page=1):
    from gi.repository import GdkPixbuf
    path = Path(path).absolute();key = fingerprint(path)
    with LOCK:
        entry = CACHE.pop(key,None)
        if entry is None:
            folder = tempfile.TemporaryDirectory(prefix='bilddetails-show-')
            root = Path(folder.name)
            try:
                if needs_stream(path):
                    index={'bytes':0,'client':Client(path,root,key)}
                else:
                    try:
                        call_helper(['index',path,root])
                        index = json.loads((root/'index.json').read_text())
                    except ValueError:
                        (root/'archive.tar').unlink(missing_ok=True)
                        index={'bytes':0,'client':Client(path,root,key)}
                if fingerprint(path) != key: raise ValueError('Fotoshow wurde beim Laden verändert.')
            except Exception:
                folder.cleanup();raise
            entry = folder,index
        CACHE[key] = entry
        # At most two shows and 512 MiB of uncompressed archive spools in total.
        while len(CACHE)>2 or sum(item[1]['bytes'] for item in CACHE.values())>MAX_ARCHIVE:
            _, old = CACHE.popitem(last=False)
            if 'client' in old[1]: old[1]['client'].close()
            old[0].cleanup()
        folder,index = entry
        if 'client' in index:
            try:
                result=index['client'].get(page)
                if fingerprint(path)!=key:raise ValueError('Fotoshow wurde beim Lesen verändert.')
                pix=GdkPixbuf.Pixbuf.new_from_file(result.pop('output'))
                return dict(result,kind='run',pixbuf=pix,unit='Bild',label='Fotoshow Studio')
            except Exception:
                CACHE.pop(key,None);index['client'].close();folder.cleanup();raise
        pages = len(index['images']);page = max(1,min(pages,int(page)))
        offset,size = index['images'][page-1]
        root = Path(folder.name);output = root/'page.png'
        call_helper(['render',root/'archive.tar',offset,size,output])
        pix = GdkPixbuf.Pixbuf.new_from_file(str(output))
        output.unlink(missing_ok=True)
        return {'kind':'run','pixbuf':pix,'page':page,'pages':pages,
                'unit':'Bild','label':'Fotoshow Studio'}


if __name__ == '__main__':
    try:
        if sys.argv[1] == 'index':
            build_index(Path(sys.argv[2]),Path(sys.argv[3]))
        elif sys.argv[1] == 'render':
            from preview_image import decode
            with Path(sys.argv[2]).open('rb') as stream:
                stream.seek(int(sys.argv[3]));data = stream.read(int(sys.argv[4]))
            decode(data).savev(sys.argv[5],'png',['compression'],['1'])
        else: raise ValueError('Unbekannter Vorschauauftrag.')
    except Exception as exc:
        print(str(exc),file=sys.stderr);sys.exit(1)
