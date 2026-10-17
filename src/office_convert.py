#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private UNO conversion process; launched with a process-group timeout."""
from pathlib import Path
import os
import subprocess
import sys
import time
import uuid
import uno
import unohelper
from com.sun.star.task import XInteractionHandler


class AbortInteraction(unohelper.Base, XInteractionHandler):
    def handle(self, request):
        for continuation in request.getContinuations():
            abort = continuation.queryInterface(uno.getTypeByName('com.sun.star.task.XInteractionAbort'))
            if abort is not None:
                abort.select()
                return


def props(**values):
    result = []
    for key, value in values.items():
        prop = uno.createUnoStruct('com.sun.star.beans.PropertyValue')
        prop.Name, prop.Value = key, value
        result.append(prop)
    return tuple(result)


class OfficeSession:
    def __init__(self, profile):
        self.desktop = None
        profile.mkdir(parents=True)
        user = profile / 'user'; user.mkdir()
        (user / 'registrymodifications.xcu').write_text('''<?xml version="1.0" encoding="UTF-8"?>
    <oor:items xmlns:oor="http://openoffice.org/2001/registry">
    <item oor:path="/org.openoffice.Office.Common/Security/Scripting">
    <prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
    <prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
    <prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
    </item></oor:items>''')
        pipe = 'bilddetails_' + uuid.uuid4().hex
        env = dict(os.environ, SAL_USE_VCLPLUGIN='svp', GSETTINGS_BACKEND='memory')
        process = subprocess.Popen(['/usr/bin/libreoffice', '-env:UserInstallation=' + profile.as_uri(),
            '--headless', '--invisible', '--nologo', '--nodefault', '--nofirststartwizard', '--norestore',
            '--accept=pipe,name=' + pipe + ';urp;StarOffice.ComponentContext'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
        self.process = process
        try:
            local = uno.getComponentContext()
            resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
            deadline = time.monotonic() + 20
            while True:
                try:
                    context = resolver.resolve('uno:pipe,name=' + pipe + ';urp;StarOffice.ComponentContext')
                    break
                except Exception:
                    if process.poll() is not None or time.monotonic() >= deadline:
                        raise ValueError('LibreOffice-Konverter konnte nicht gestartet werden.') from None
                    time.sleep(.1)
            desktop = context.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', context)
            self.desktop = desktop
        except Exception:
            self.close()
            raise

    def convert(self, source, output):
        document = None
        try:
            document = self.desktop.loadComponentFromURL(source.as_uri(), '_blank', 0,
                props(Hidden=True, ReadOnly=True, UpdateDocMode=0, MacroExecutionMode=0,
                      InteractionHandler=AbortInteraction()))
            if document is None:
                raise ValueError('Office-Datei nicht lesbar (beschädigt, passwortgeschützt oder nicht unterstützt).')
            filter_name = None
            for service, candidate in [
                ('com.sun.star.presentation.PresentationDocument', 'impress_pdf_Export'),
                ('com.sun.star.sheet.SpreadsheetDocument', 'calc_pdf_Export'),
                ('com.sun.star.drawing.DrawingDocument', 'draw_pdf_Export'),
                ('com.sun.star.formula.FormulaProperties', 'math_pdf_Export'),
                ('com.sun.star.text.TextDocument', 'writer_pdf_Export')]:
                if document.supportsService(service):
                    filter_name = candidate
                    break
            if filter_name is None: raise ValueError('Kein geeigneter Dokument-Konverter verfügbar.')
            document.storeToURL(output.as_uri(), props(FilterName=filter_name, Overwrite=True))
            document.close(True); document = None
        finally:
            if document is not None:
                try: document.dispose()
                except Exception: pass

    def close(self):
        if self.desktop is not None:
            try: self.desktop.terminate()
            except Exception: pass
        if hasattr(self, 'process'):
            try: self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait()


def convert(source, output, profile):
    session = OfficeSession(profile)
    try: session.convert(source, output)
    finally: session.close()


if __name__ == '__main__':
    try:
        convert(*(Path(value).absolute() for value in sys.argv[1:4]))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
