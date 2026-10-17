# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable Makeself fixtures matching Fotoshow Studio's numbered PNG layout."""
from pathlib import Path
import subprocess
import tempfile
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf


def build(folder,recursive,target,delay,randomize,fit,cancel,report,selected=None):
    folder,target=Path(folder),Path(target)
    files=sorted(selected if selected is not None else (folder.rglob('*') if recursive else folder.iterdir()))
    files=[path for path in files if path.is_file() and path.suffix.lower() in {'.png','.jpg','.jpeg','.webp','.tiff','.bmp'}]
    with tempfile.TemporaryDirectory() as temp:
        payload=Path(temp)/'payload';images=payload/'Bilder';images.mkdir(parents=True)
        for n,path in enumerate(files,1):
            if cancel.is_set():raise ValueError('Testfixture abgebrochen.')
            GdkPixbuf.Pixbuf.new_from_file(str(path)).savev(str(images/(str(n).zfill(9)+'.png')),'png',[],[])
        launcher=payload/'start-diashow.sh';launcher.write_text('#!/bin/sh\nexit 0\n');launcher.chmod(0o755)
        subprocess.run(['makeself','--quiet','--nox11',str(payload),str(target),'Fotoshow','./start-diashow.sh'],
            check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)
    return target


def fixture_api():return {'build':build}
