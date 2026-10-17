# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate local representative fixtures through the installed UNO exporters."""
from pathlib import Path
import os
import subprocess
import time
import uuid
import uno


def make_suite(folder):
    folder = Path(folder).absolute(); folder.mkdir(parents=True, exist_ok=True)
    import sys
    sys.path.insert(0, str(Path(__file__).parent / 'src'))
    from office_convert import props
    profile = folder / 'fixture-profile'
    pipe = 'fixtures_' + uuid.uuid4().hex
    process = subprocess.Popen(['/usr/bin/libreoffice', '-env:UserInstallation=' + profile.as_uri(),
        '--headless', '--nologo', '--nodefault', '--norestore',
        '--accept=pipe,name=' + pipe + ';urp;StarOffice.ComponentContext'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=dict(os.environ, SAL_USE_VCLPLUGIN='svp', GSETTINGS_BACKEND='memory'))
    desktop = None
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
        deadline = time.monotonic() + 20
        while True:
            try:
                ctx = resolver.resolve('uno:pipe,name=' + pipe + ';urp;StarOffice.ComponentContext'); break
            except Exception:
                if process.poll() is not None or time.monotonic() > deadline: raise RuntimeError('Fixture-UNO nicht gestartet')
                time.sleep(.1)
        desktop = ctx.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', ctx)
        filters = ctx.ServiceManager.createInstanceWithContext('com.sun.star.document.FilterFactory', ctx)
        types = ctx.ServiceManager.createInstanceWithContext('com.sun.star.document.TypeDetection', ctx)
        outputs = []
        groups = [
            ('simpress', ['.ppt', '.pptx', '.odp', '.ppsx', '.potx', '.otp', '.fodp', '.pptm']),
            ('sdraw', ['.odg', '.otg', '.fodg']),
            ('smath', ['.odf']),
            ('swriter', ['.ott', '.fodt', '.dotx', '.rtf']),
            ('scalc', ['.ods', '.ots', '.fods', '.xltx'])]
        for factory, extensions in groups:
            doc = desktop.loadComponentFromURL('private:factory/' + factory, '_blank', 0, props(Hidden=True))
            try:
                if factory in ('simpress', 'sdraw'):
                    pages = doc.getDrawPages()
                    if pages.getCount() < 2: pages.insertNewByIndex(1)
                    for i in range(2):
                        page = pages.getByIndex(i); page.Width = 28000; page.Height = 15750
                        shape = doc.createInstance('com.sun.star.drawing.TextShape')
                        position = uno.createUnoStruct('com.sun.star.awt.Point'); position.X = 1500; position.Y = 1000
                        size = uno.createUnoStruct('com.sun.star.awt.Size'); size.Width = 24000; size.Height = 3500
                        shape.Position = position; shape.Size = size; page.add(shape)
                        shape.String = ('Folie ' if factory == 'simpress' else 'Zeichnung ') + str(i + 1)
                        shape.CharHeight = 36
                        rectangle = doc.createInstance('com.sun.star.drawing.RectangleShape')
                        position = uno.createUnoStruct('com.sun.star.awt.Point'); position.X = 1500; position.Y = 6000
                        size = uno.createUnoStruct('com.sun.star.awt.Size'); size.Width = 18000; size.Height = 5500
                        rectangle.Position = position; rectangle.Size = size
                        rectangle.FillColor = 0x2879B9 if i == 0 else 0xCF733C
                        page.add(rectangle)
                elif factory == 'smath': doc.Formula = 'a^2 + b^2 = c^2'
                elif factory == 'swriter': doc.Text.String = 'Dokumentvorlage\nFormatierte Dokumentvorschau'
                else:
                    sheets = doc.getSheets()
                    if sheets.getCount() < 2: sheets.insertNewByName('Tabelle2', 1)
                    for i in range(2): sheets.getByIndex(i).getCellRangeByName('A1').String = 'Tabelle ' + str(i + 1)
                for extension in extensions:
                    candidates = []
                    for name in filters.getElementNames():
                        info = {p.Name: p.Value for p in filters.getByName(name)}
                        if not int(info.get('Flags', 0)) & 2: continue
                        service = info.get('DocumentService', '')
                        if service and not doc.supportsService(service): continue
                        try: type_info = {p.Name: p.Value for p in types.getByName(info.get('Type', ''))}
                        except Exception: continue
                        if extension[1:] in type_info.get('Extensions', ()): candidates.append(name)
                    if not candidates: raise RuntimeError('Kein Exportfilter: ' + extension)
                    preferred = {'.ppt': 'MS PowerPoint 97', '.pptx': 'Impress MS PowerPoint 2007 XML',
                                 '.odp': 'impress8', '.odg': 'draw8', '.odf': 'math8', '.ods': 'calc8'}
                    chosen = preferred.get(extension)
                    if chosen not in candidates: chosen = sorted(candidates)[0]
                    target = folder / ('fixture' + extension)
                    doc.storeToURL(target.as_uri(), props(FilterName=chosen, Overwrite=True))
                    outputs.append(target)
            finally: doc.close(True)
        return outputs
    finally:
        if desktop is not None:
            try: desktop.terminate()
            except Exception: pass
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
