# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded private Office-to-PDF cache; never writes beside source files."""
from collections import OrderedDict
from pathlib import Path
import shutil
import signal
import os
import subprocess
import tempfile
import threading
import atexit
import json
import selectors
from preview_document import render_pdf

from formats import OFFICE_SUFFIXES, IMPRESS, DRAW, MATH, CALC
MAX_SOURCE = 64 * 1024 * 1024
LOCK = threading.Lock()
CACHE = OrderedDict()


class Converter:
    def __init__(self):
        self.process = None
        self.folder = None

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            try:
                process.stdin.close()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
            process.stdout.close()
        if self.folder is not None:
            self.folder.cleanup()
            self.folder = None

    def convert(self, source, output):
        if self.process is None or self.process.poll() is not None:
            self.close()
            self.folder = tempfile.TemporaryDirectory(prefix='bilddetails-converter-')
            self.process = subprocess.Popen(['/usr/bin/python3',
                str(Path(__file__).with_name('office_service.py')),
                str(Path(self.folder.name) / 'profil')], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            self.process.stdin.write((json.dumps({'source': str(source), 'output': str(output)}) + '\n').encode())
            self.process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=60):
                    raise ValueError('Office-Konvertierung nach 60 Sekunden abgebrochen.')
            response = json.loads(self.process.stdout.readline(65536))
        except Exception:
            self.close()
            raise
        if not response.get('ok'):
            raise ValueError(response.get('error') or 'Office-Vorschau nicht verfügbar.')

SERVICE = Converter()
atexit.register(SERVICE.close)


def fingerprint(path):
    stat = path.stat()
    return str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def render_office(path, page=1):
    path = Path(path).absolute()
    if path.suffix.lower() not in OFFICE_SUFFIXES:
        raise ValueError('Dieses Office-Format wird nicht unterstützt.')
    if path.stat().st_size > MAX_SOURCE:
        raise ValueError('Office-Datei größer als 64 MiB; bitte in LibreOffice öffnen.')
    key = fingerprint(path)
    with LOCK:
        if key in CACHE:
            folder = CACHE.pop(key)
            CACHE[key] = folder
        else:
            folder = tempfile.TemporaryDirectory(prefix='bilddetails-office-')
            root = Path(folder.name)
            source = root / ('eingabe' + path.suffix.lower())
            try:
                shutil.copyfile(path, source)
                if fingerprint(path) != key:
                    raise ValueError('Datei wurde während des Einlesens verändert. Bitte erneut auswählen.')
                SERVICE.convert(source, root / 'vorschau.pdf')
                if not (root / 'vorschau.pdf').is_file():
                    raise ValueError('Office-Vorschau nicht verfügbar.')
                if (root / 'vorschau.pdf').stat().st_size > 100 * 1024 * 1024:
                    raise ValueError('Konvertierte PDF größer als 100 MiB; Vorschau abgebrochen.')
                shutil.rmtree(root / 'profil', ignore_errors=True)
                source.unlink(missing_ok=True)
            except Exception:
                folder.cleanup()
                raise
            CACHE[key] = folder
            while len(CACHE) > 3:
                _, old = CACHE.popitem(last=False)
                old.cleanup()
        result = render_pdf(Path(folder.name) / 'vorschau.pdf', page)
        result['office'] = True
        result['office_label'] = ('Präsentation' if path.suffix.lower() in IMPRESS else
                                  'Zeichnung' if path.suffix.lower() in DRAW else
                                  'Formel' if path.suffix.lower() in MATH else
                                  'Tabellen-Druckvorschau' if path.suffix.lower() in CALC else 'Office-Druckvorschau')
        result['unit'] = 'Folie' if path.suffix.lower() in IMPRESS else 'Seite'
        return result
