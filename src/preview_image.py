# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, read-only image decoding outside Nemo's UI process."""
from pathlib import Path
import subprocess
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf, GLib

MAX_BYTES = 48 * 1024 * 1024
MAX_EDGE = 1920
RAW = {'.cr2', '.cr3', '.crw', '.dng', '.nef', '.nrw', '.arw', '.srf', '.sr2',
       '.orf', '.rw2', '.raf', '.pef', '.ptx', '.srw', '.3fr', '.fff', '.iiq',
       '.kdc', '.dcr', '.mrw', '.mos', '.raw', '.rwl', '.x3f'}

def decode(data):
    loader = GdkPixbuf.PixbufLoader.new()
    def size(loader, width, height):
        scale = min(1.0, MAX_EDGE / max(width, height))
        loader.set_size(max(1, int(width * scale)), max(1, int(height * scale)))
    loader.connect('size-prepared', size)
    try:
        loader.write(data)
        loader.close()
        pix = loader.get_pixbuf()
        if pix is None:
            raise ValueError('Kein dekodierbares Vorschaubild vorhanden.')
        return pix.apply_embedded_orientation()
    except GLib.Error as exc:
        raise ValueError('Bildformat nicht lesbar: ' + exc.message) from exc

def embedded_preview(path):
    # Never expand a full RAW; read embedded JPEG, capped on stdout.
    for tag in ('PreviewImage', 'JpgFromRaw', 'ThumbnailImage'):
        with subprocess.Popen(['exiftool', '-config', '', '-b', '-' + tag, str(path)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            # The outer worker has a wall-clock timeout enforced by its caller.
            data = process.stdout.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                process.kill()
                raise ValueError('Eingebettete Vorschau überschreitet 48 MiB.')
            if process.wait() == 0 and data:
                return decode(data)
    raise ValueError('Kein eingebettetes JPEG verfügbar. RAW-Datei bleibt unverändert.')

def render(path, destination):
    path = Path(path).absolute()
    if not path.is_file():
        raise ValueError('Keine lokale Bilddatei ausgewählt.')
    if path.suffix.lower() == '.run':
        from preview_run import render_run
        pix = render_run(path)
    elif path.suffix.lower() == '.xcf':
        from preview_xcf import render_xcf
        pix, note = render_xcf(path)
    elif path.suffix.lower() in RAW:
        pix = embedded_preview(path)
    else:
        # Stream compressed data and downsample at decode time.
        loader = GdkPixbuf.PixbufLoader.new()
        loader.connect('size-prepared', lambda loader, w, h: loader.set_size(
            max(1, int(w * min(1.0, MAX_EDGE / max(w, h)))),
            max(1, int(h * min(1.0, MAX_EDGE / max(w, h))))))
        try:
            with path.open('rb') as stream:
                for chunk in iter(lambda: stream.read(131072), b''):
                    loader.write(chunk)
            loader.close()
            pix = loader.get_pixbuf().apply_embedded_orientation()
        except (GLib.Error, AttributeError) as exc:
            raise ValueError('Keine Vorschau mit den installierten Bildladern möglich.') from exc
    pix.savev(str(destination), 'png', [], [])

if __name__ == '__main__':
    import sys
    try:
        render(sys.argv[1], sys.argv[2])
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
