#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run an actual Thunar instance on an isolated Broadway display and D-Bus.

No installation, user settings or existing Thunar processes are changed.
Needs thunar, broadwayd, cc, ImageMagick and Debian/Ubuntu amd64 library paths.
"""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sysconfig
import tempfile

ROOT = Path(__file__).resolve().parent.parent
LIB = Path('/usr/lib/x86_64-linux-gnu/libthunarx-3.so.0')
with tempfile.TemporaryDirectory(prefix='ndvp-') as folder:
    tmp = Path(folder)
    plugins = tmp/'plugins'; plugins.mkdir()
    # Mint's Thunar ignores THUNARX_DIRS. Redirect only a private test copy of
    # the extension factory's default path; the system library is read-only.
    binary = LIB.read_bytes()
    old = b'/usr/lib/x86_64-linux-gnu/thunarx-3:/usr/lib/thunarx-3'
    new = str(plugins).encode()
    if old not in binary or len(new) > len(old):
        raise SystemExit('Isolierter Test-Ladepfad für diese Thunar-Version unbekannt.')
    (tmp/'libthunarx-3.so.0').write_bytes(binary.replace(old, new+b'\0'*(len(old)-len(new))))
    native = plugins/'dateivorschau-plus.so'
    subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
        '-DPYTHON_SONAME="'+sysconfig.get_config_var('INSTSONAME')+'"',
        '-DPREVIEW_PYTHON_PATH="'+str(ROOT/'src')+'"', '-DPREVIEW_INTEGRATION_TEST',
        str(ROOT/'thunar/loader.c'), '-o', str(native), '-ldl'], check=True)
    shutil.copy(ROOT/'thunar/integration_driver.py', tmp/'driver.py')
    files = tmp/'files'; files.mkdir()
    subprocess.run(['convert', '-size', '64x48', 'xc:red', str(files/'a.png')], check=True)
    (files/'b.txt').write_text('Textvorschau-Test\n')
    import cairo
    surface = cairo.PDFSurface(str(files/'c.pdf'), 300, 300)
    context = cairo.Context(surface)
    for text in ('Seite eins', 'Seite zwei'):
        context.move_to(20, 40); context.show_text(text); context.show_page()
    surface.finish()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env = dict(os.environ, GDK_BACKEND='broadway', BROADWAY_DISPLAY=':47',
        LD_LIBRARY_PATH=str(tmp), PREVIEW_NATIVE_MODULE=str(native),
        PREVIEW_TEST_DIR=str(tmp), PREVIEW_TEST_RESULT=str(tmp/'result'),
        XDG_DATA_HOME=str(tmp/'data'), XDG_CONFIG_HOME=str(tmp/'config'),
        XDG_CACHE_HOME=str(tmp/'cache'))
    display = subprocess.Popen(['broadwayd','-a','127.0.0.1','-p',str(port),':47'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Broadway binds its local display socket before this bounded wait ends.
        import time
        time.sleep(.4)
        subprocess.run(['dbus-run-session','--','thunar',str(files)], env=env, timeout=45, check=True)
        if not (tmp/'result').exists() or (tmp/'result').read_text().strip() != 'PASS':
            raise SystemExit('Thunar-Integrationstest fehlgeschlagen.')
        print('PASS: Thunar integration')
    finally:
        display.terminate(); display.wait(timeout=5)
