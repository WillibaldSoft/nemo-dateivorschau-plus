# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only XCF composition using a private, minimal GIMP 2/3 processes."""
from pathlib import Path
import hashlib
import json
import os
import signal
import resource
import shutil
import struct
import subprocess
import tempfile
import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

MAX_SOURCE = 256 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 1920
DISK_BUDGET = 128 * 1024 * 1024


def stamp(path):
    s = path.stat()
    return (str(path), s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def cache_root():
    return Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'bilddetails' / 'xcf'


def load_pix(path):
    info, width, height = GdkPixbuf.Pixbuf.get_file_info(str(path))
    if info is None: raise ValueError('Vorschaucache nicht lesbar.')
    return GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),min(MAX_EDGE,width),min(MAX_EDGE,height),True)


def child_limits():
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024**2, 64 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (18, 18))


def cached_thumbnail(path):
    """Only use existing standard thumbnails with matching source metadata."""
    s = path.stat(); uri = path.as_uri()
    key = hashlib.md5(uri.encode(), usedforsecurity=False).hexdigest()+'.png'
    base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'thumbnails'
    for size in ('xx-large','x-large','large','normal'):
        thumb = base / size / key
        try:
            if thumb.stat().st_size > 8 * 1024 * 1024 or thumb.stat().st_mtime_ns < s.st_mtime_ns: continue
            pix = load_pix(thumb)
            if (pix.get_option('tEXt::Thumb::URI') == uri and
                pix.get_option('tEXt::Thumb::MTime') == str(int(s.st_mtime)) and
                pix.get_option('tEXt::Thumb::Size') == str(s.st_size)):
                return pix
        except Exception: pass
    return None


def prune(root):
    files = sorted(root.glob('*.png'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
    total = 0
    for n, path in enumerate(files):
        total += path.stat().st_size
        if n >= 24 or total > DISK_BUDGET: path.unlink(missing_ok=True)


def gimp3_backend():
    override = os.environ.get('BILDDETAILS_GIMP3_RUNTIME')
    roots = [Path(override)] if override else []
    roots += [Path(__file__).resolve().parent / 'gimp3']
    for root in roots:
        console = root / 'bilddetails-console'
        if console.is_file():
            return console, root / 'usr/lib/x86_64-linux-gnu/gimp/3.0/plug-ins'
    for name in ('gimp-console-3.2', 'gimp-console-3.0', 'gimp-console-3'):
        binary = shutil.which(name)
        if binary:
            for plugins in (Path('/usr/lib/gimp/3.0/plug-ins'),Path('/usr/lib/x86_64-linux-gnu/gimp/3.0/plug-ins')):
                if (plugins / 'python-eval').exists(): return Path(binary), plugins
    return None


def convert3(path, destination, temp, backend):
    binary, system = backend
    plugins = temp/'plugins3'; plugins.mkdir()
    for name in ('python-eval', 'file-png'):
        if not (system/name).exists(): raise ValueError('GIMP-3-Systemmodul fehlt: '+name)
        (plugins/name).symlink_to(system/name, target_is_directory=True)
    config = temp/'gimprc3'
    config.write_text('(plug-in-path '+json.dumps(str(plugins))+')\n(tile-cache-size 128M)\n(check-updates no)\n')
    env = dict(os.environ,GIMP3_DIRECTORY=str(temp/'profile3'),GEGL_THREADS='1',
        GEGL_USE_OPENCL='no',OMP_NUM_THREADS='1',BILDDETAILS_SOURCE=str(path),
        BILDDETAILS_DESTINATION=str(destination),
        BILDDETAILS_BATCH=str(Path(__file__).with_name('gimp3_render.py').absolute()))
    if binary.name == 'bilddetails-console':
        env['APPDIR'] = str(binary.parent)
    batch = "import os; exec(compile(open(os.environ['BILDDETAILS_BATCH'], encoding='utf-8').read(), os.environ['BILDDETAILS_BATCH'], 'exec'))"
    process = subprocess.Popen([str(binary),'-n','-i','-d','-f','-s','--console-messages',
        '--gimprc='+str(config),'--batch-interpreter=python-fu-eval','-b',batch,'--quit'],
        env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        start_new_session=True,preexec_fn=child_limits)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        raise ValueError('GIMP-3-Vorschau nach 20 Sekunden abgebrochen.') from None
    finally:
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait()
    if process.returncode or not destination.exists():
        raise ValueError('GIMP 3 konnte diese XCF-Datei nicht rendern.')


def render_xcf(path):
    path = Path(path).absolute(); before = stamp(path)
    root = cache_root()
    key = hashlib.sha256(('renderer3:'+repr(before)).encode()).hexdigest()+'.png'
    cached = root / key
    try:
        pix = load_pix(cached)
        return pix, 'XCF · gespeicherte Vorschau'
    except Exception: pass
    pix = cached_thumbnail(path)
    if pix is not None: return pix, 'XCF · vorhandenes Thumbnail (begrenzte Auflösung)'
    if before[2] > MAX_SOURCE: raise ValueError('XCF größer als 256 MiB; bitte in GIMP öffnen.')
    with path.open('rb') as stream: header = stream.read(26)
    if not header.startswith(b'gimp xcf ') or len(header) < 26:
        raise ValueError('Keine gültige XCF-Datei.')
    width,height = struct.unpack('>II',header[14:22])
    if not width or not height or width*height > MAX_PIXELS:
        raise ValueError('XCF über 40 Megapixel; bitte in GIMP öffnen.')
    backend3 = gimp3_backend()
    binary = shutil.which('gimp-console-2.10')
    if binary is None and backend3 is None:
        raise ValueError('XCF-Konvertierung benötigt den GIMP-Decoder.')
    with tempfile.TemporaryDirectory(prefix='bilddetails-xcf-') as folder:
        temp = Path(folder)
        destination = temp/'preview.png'
        if backend3 is not None:
            convert3(path,destination,temp,backend3)
        else:
            plugins = temp/'plugins'; plugins.mkdir()
            system = Path('/usr/lib/gimp/2.0/plug-ins')
            for name in ('script-fu','file-png'):
                target = system/name
                if not target.exists(): raise ValueError('GIMP-Systemmodule fehlen: '+name)
                (plugins/name).symlink_to(target, target_is_directory=target.is_dir())
            empty = temp/'scripts';empty.mkdir()
            for init in Path('/usr/share/gimp/2.0/scripts').glob('*.init'):
                (empty/init.name).symlink_to(init)
            config = temp/'gimprc'
            quote = lambda value: json.dumps(str(value),ensure_ascii=False)
            config.write_text('(plug-in-path '+quote(plugins)+')\n(script-fu-path '+quote(empty)+')\n(tile-cache-size 128M)\n')
            destination = temp/'preview.png'
            script = '''(let* ((img (car (gimp-file-load RUN-NONINTERACTIVE %s %s)))
                (w (car (gimp-image-width img))) (h (car (gimp-image-height img)))
                (factor (min 1.0 (/ 1920.0 (max w h)))))
                (if (< factor 1.0) (gimp-image-scale img (max 1 (inexact->exact (round (* w factor)))) (max 1 (inexact->exact (round (* h factor))))))
                (let ((layer (car (gimp-image-merge-visible-layers img CLIP-TO-IMAGE))))
                (file-png-save RUN-NONINTERACTIVE img layer %s %s 0 1 0 0 0 0 0))
                (gimp-image-delete img))''' % (quote(path),quote(path),quote(destination),quote(destination))
            env = dict(os.environ,GIMP2_DIRECTORY=str(temp/'profile'),GEGL_THREADS='1')
            process = subprocess.Popen([binary,'-n','-i','-d','-f','-s','--console-messages',
                '--gimprc='+str(config),'--batch-interpreter=plug-in-script-fu-eval',
                '-b',script,'-b','(gimp-quit 0)'],env=env,stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,start_new_session=True,preexec_fn=child_limits)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                raise ValueError('XCF-Vorschau nach 20 Sekunden abgebrochen.') from None
            finally:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass
                process.wait()
            if process.returncode or not destination.exists():
                raise ValueError('XCF konnte nicht gerendert werden; möglicherweise nicht mit GIMP 2.10 kompatibel. ')
        pix = load_pix(destination)
        if stamp(path) != before: raise ValueError('XCF wurde beim Laden verändert; bitte erneut auswählen.')
        try:
            root.mkdir(parents=True,exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=root,suffix='.tmp',delete=False) as stream:
                staging=Path(stream.name)
            try:
                pix.savev(str(staging),'png',['compression'],['1'])
                os.replace(staging,cached)
            finally: staging.unlink(missing_ok=True)
            prune(root)
        except OSError: pass  # Unwritable cache must not prevent a preview.
        return pix, 'XCF · sichtbare Ebenen · Vorschau bis 1920 Pixel'
