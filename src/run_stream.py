# SPDX-License-Identifier: GPL-3.0-or-later
"""On-demand gzip slideshow reader; bounded thumbnails instead of full tar spools."""
from collections import OrderedDict
import gzip
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

STATUS = {}
CLIENTS = {}
FRAME_BUDGET = 128 * 1024 * 1024


def needs_stream(path):
    size = path.stat().st_size
    if size > 32 * 1024 * 1024: return True
    if size < 4: return False
    with path.open('rb') as stream:
        stream.seek(-4,2)
        expanded = int.from_bytes(stream.read(4),'little')
    return expanded > 64 * 1024 * 1024


def refresh(result):
    client=CLIENTS.get(result.get('stream_id'))
    if client is not None:client.read_count()
    state = STATUS.get(result.get('stream_id'))
    if not state:return result
    if not state['pages_known']:
        state=dict(state,pages=max(state['pages'],result['page']+1))
        STATUS[result['stream_id']]=state
    return dict(result, **state)


class Client:
    def __init__(self,path,root,key):
        self.key=repr(key)
        self.path,self.root,self.fingerprint=path,root,key
        self.counter=None;self.count_started=False;self.count_total=None
        CLIENTS[self.key]=self
        self.process=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).absolute()),str(path),str(root)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)

    def get(self,page):
        try:
            self.process.stdin.write((json.dumps({'page':int(page)})+'\n').encode());self.process.stdin.flush()
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout,selectors.EVENT_READ)
                if not selector.select(20): raise ValueError('Zeitlimit beim Laden dieses Fotoshow-Bildes (20 s).')
            result=json.loads(self.process.stdout.readline(65536))
            if 'error' in result: raise ValueError(result['error'])
        except Exception:
            self.close();raise
        self.read_count()
        if self.count_total is not None:
            result.update(pages=self.count_total,pages_known=True)
        if not result['pages_known']:
            result['pages']=max(result['pages'],STATUS.get(self.key,{}).get('pages',1))
        STATUS[self.key]={'pages':result['pages'],'pages_known':result['pages_known']}
        result['stream_id']=self.key
        return result

    def start_count(self):
        if self.count_started or self.process is None:return
        self.count_started=True;self.count_start=time.monotonic()
        command=['/usr/bin/python3',str(Path(__file__).absolute()),'--count',str(self.path),str(self.root),json.dumps(self.fingerprint)]
        import shutil
        if shutil.which('ionice'):command=['ionice','-c','3',*command]
        self.counter=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

    def read_count(self):
        if self.counter is None or self.count_total is not None:return
        if self.counter.poll() is None:
            if time.monotonic()-self.count_start>300:
                try:os.killpg(self.counter.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                self.counter.wait()
            else:return
        path=self.root/'count.json'
        if path.exists():
            try:
                data=json.loads(path.read_text())
                if data.get('pages_known') and data['pages']>0:
                    self.count_total=data['pages']
                    STATUS[self.key]={'pages':self.count_total,'pages_known':True}
            except (OSError,ValueError,KeyError):pass
        self.counter=None

    def close(self):
        CLIENTS.pop(self.key,None)
        STATUS.pop(self.key,None)
        if self.counter is not None:
            try:os.killpg(self.counter.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            self.counter.wait();self.counter=None
        if self.process is None:return
        process,self.process=self.process,None
        try: process.stdin.close()
        except OSError:pass
        try: os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait();process.stdout.close()


class Server:
    def __init__(self,path,root):
        self.path,self.root=path,root
        self.cache=OrderedDict();self.seen=0;self.total=None;self.source=None
        self.reset()

    def reset(self):
        import tarfile
        if self.source is not None:self.source.close()
        self.source=self.path.open('rb');header=self.source.read(256*1024)
        if not header.startswith(b'#!/bin/sh') or b'generated using Makeself' not in header[:2048]:
            raise ValueError('Keine unterstützte Fotoshow-Studio-/Makeself-Datei.')
        match=re.search(rb'^skip="([0-9]{1,5})"\r?$',header,re.M)
        lines=header.splitlines(keepends=True);skip=int(match[1]) if match else 0
        if skip<1 or skip>=len(lines):raise ValueError('Fotoshow-Header nicht lesbar.')
        self.source.seek(sum(map(len,lines[:skip])))
        self.zipped=gzip.GzipFile(fileobj=self.source)
        self.archive=tarfile.open(fileobj=self.zipped,mode='r|')
        self.cursor=0

    def get(self,page):
        from preview_run import image_name
        from preview_image import decode
        page=max(1,page)
        if self.total is not None:page=min(self.total,page)
        if page not in self.cache:
            if page<=self.cursor:self.reset()
            while self.cursor<page:
                member=self.archive.next()
                if member is None:
                    self.total=self.cursor
                    if not self.total:raise ValueError('Keine unterstützten Bilder im Fotoshow-Archiv gefunden.')
                    return self.get(min(page,self.total))
                self.archive.members.clear()  # Do not retain metadata for the whole archive.
                if image_name(member) is None:continue
                self.cursor+=1;self.seen=max(self.seen,self.cursor)
                if not 0<member.size<=64*1024*1024:raise ValueError('Einzelnes Show-Bild über 64 MiB.')
                if self.cursor==page:
                    with self.archive.extractfile(member) as image:data=image.read(member.size)
                    output=self.root/(str(page)+'.png')
                    decode(data).savev(str(output),'png',['compression'],['1'])
                    self.cache[page]=(output,output.stat().st_size)
                    while len(self.cache)>64 or sum(item[1] for item in self.cache.values())>FRAME_BUDGET:
                        _,(old,_) = self.cache.popitem(last=False);old.unlink(missing_ok=True)
        output,size=self.cache.pop(page);self.cache[page]=(output,size)
        return {'page':page,'pages':self.total if self.total is not None else self.seen+1,
                'pages_known':self.total is not None,'output':str(output)}


def start_count(key):
    client=CLIENTS.get(key)
    if client is not None:client.start_count()


def count_state(key):
    client=CLIENTS.get(key)
    if client is not None:client.read_count()
    return STATUS.get(key)


def count_images(path,root,expected):
    from preview_run import fingerprint,image_name
    os.nice(19)
    server=None
    try:
        if list(fingerprint(path))!=expected:raise ValueError('Quelle verändert.')
        server=Server(path,root);count=0
        while True:
            member=server.archive.next()
            if member is None:break
            server.archive.members.clear()
            if image_name(member) is not None:
                if not 0<member.size<=64*1024*1024:raise ValueError('Bildgröße nicht unterstützt.')
                count+=1
        if list(fingerprint(path))!=expected:raise ValueError('Quelle verändert.')
        result={'pages':count,'pages_known':count>0}
    except Exception as exc:result={'error':str(exc)}
    finally:
        if server is not None and server.source is not None:server.source.close()
    temp=root/'count.tmp';temp.write_text(json.dumps(result));os.replace(temp,root/'count.json')


if __name__=='__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
    if sys.argv[1]=='--count':
        signal.alarm(300)
        count_images(Path(sys.argv[2]),Path(sys.argv[3]),json.loads(sys.argv[4]));sys.exit(0)
    server=None
    try:
        for line in sys.stdin:
            try:
                if server is None:server=Server(Path(sys.argv[1]),Path(sys.argv[2]))
                result=server.get(int(json.loads(line)['page']))
            except Exception as exc:result={'error':str(exc)}
            print(json.dumps(result),flush=True)
    finally:
        if server is not None and server.source is not None:server.source.close()
