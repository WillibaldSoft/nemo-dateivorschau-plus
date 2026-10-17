# SPDX-License-Identifier: GPL-3.0-or-later
import hashlib,json,os,struct,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'src'))
from preview_xcf import render_xcf,cache_root,prune,MAX_SOURCE,DISK_BUDGET,cached_thumbnail
from preview_document import kind
from preview_widget import Preview,Gtk,worker

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        cls.fixture=cls.root/'sichtbar ä "test".xcf'
        q=json.dumps(str(cls.fixture),ensure_ascii=False)
        script='''(let* ((img (car (gimp-image-new 64 48 RGB)))
        (base (car (gimp-layer-new img 64 48 RGB-IMAGE "rot" 100 NORMAL-MODE)))
        (hidden (car (gimp-layer-new img 64 48 RGB-IMAGE "blau unsichtbar" 100 NORMAL-MODE))))
        (gimp-image-insert-layer img base 0 0) (gimp-context-set-background '(255 0 0))
        (gimp-drawable-fill base BACKGROUND-FILL)
        (gimp-image-insert-layer img hidden 0 0) (gimp-context-set-background '(0 0 255))
        (gimp-drawable-fill hidden BACKGROUND-FILL) (gimp-item-set-visible hidden FALSE)
        (gimp-xcf-save RUN-NONINTERACTIVE img base %s %s) (gimp-image-delete img))'''%(q,q)
        subprocess.run(['/usr/bin/gimp-console-2.10','-n','-i','-d','-f','-s','--console-messages',
            '--batch-interpreter=plug-in-script-fu-eval','-b',script,'-b','(gimp-quit 0)'],
            env=dict(os.environ,GIMP2_DIRECTORY=str(cls.root/'profile')),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=25)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.cache=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,XDG_CACHE_HOME=self.cache.name);self.env.start()
    def tearDown(self):self.env.stop();self.cache.cleanup()
    def test_layers_readonly_disk_cache_and_invalidation(self):
        before=self.fixture.read_bytes();pix,note=render_xcf(self.fixture)
        self.assertEqual((pix.get_width(),pix.get_height()),(64,48))
        self.assertEqual(tuple(pix.get_pixels()[:3]),(255,0,0))
        self.assertEqual(self.fixture.read_bytes(),before)
        with patch('preview_xcf.subprocess.Popen',side_effect=AssertionError('Cache must avoid GIMP')):
            self.assertIn('gespeicherte',render_xcf(self.fixture)[1])
        stamp=self.fixture.stat();os.utime(self.fixture,ns=(stamp.st_atime_ns,stamp.st_mtime_ns+1000000000))
        self.assertIn('sichtbare',render_xcf(self.fixture)[1])
        self.assertEqual(len(list(cache_root().glob('*.png'))),2)
        self.assertEqual(kind(self.fixture),'xcf')
        self.assertEqual(worker(self.fixture).get_width(),64)
    def test_standard_thumbnail_metadata_and_limits(self):
        source=Path(self.cache.name)/'source.xcf';source.write_bytes(self.fixture.read_bytes())
        pix,_=render_xcf(source)
        uri=source.as_uri();key=hashlib.md5(uri.encode(),usedforsecurity=False).hexdigest()+'.png'
        folder=Path(self.cache.name)/'thumbnails/large';folder.mkdir(parents=True)
        target=folder/key
        pix.savev(str(target),'png',['tEXt::Thumb::URI','tEXt::Thumb::MTime','tEXt::Thumb::Size'],[uri,str(int(source.stat().st_mtime)),str(source.stat().st_size)])
        self.assertIsNotNone(cached_thumbnail(source))
        source.write_bytes(source.read_bytes()+b'changed')
        self.assertIsNone(cached_thumbnail(source))
        broken=Path(self.cache.name)/'broken.xcf';broken.write_bytes(b'not xcf')
        with self.assertRaises(ValueError):render_xcf(broken)
        huge=Path(self.cache.name)/'huge.xcf';huge.write_bytes(b'gimp xcf v011\x00\x00'+struct.pack('>II',100000,100000)+b'\x00'*8)
        with self.assertRaises(ValueError):render_xcf(huge)
        with huge.open('wb') as stream:stream.truncate(MAX_SOURCE+1)
        with self.assertRaises(ValueError):render_xcf(huge)
        root=cache_root()
        for n in range(30):(root/(str(n)+'.png')).write_bytes(b'x')
        prune(root);self.assertLessEqual(len(list(root.glob('*.png'))),24)
    def test_gtk_xcf_no_camera_editor(self):
        window=Gtk.OffscreenWindow();pane=Preview(sidebar=True);window.add(pane);window.show_all();pane.set_selection(self.fixture)
        until=time.monotonic()+10
        while pane.pixbuf is None and time.monotonic()<until:
            while Gtk.events_pending():Gtk.main_iteration_do(False)
            time.sleep(.02)
        self.assertIsNotNone(pane.pixbuf,pane.status.get_text())
        self.assertFalse(pane.edit.get_visible());self.assertFalse(pane.detail_scroll.get_visible())
        self.assertIn('XCF',pane.status.get_text());window.destroy()
