# SPDX-License-Identifier: GPL-3.0-or-later
import gzip,io,sys,tarfile,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'src'))
from preview_run import render_run_page,clear_cache,CACHE
from run_stream import needs_stream,refresh
import gi
gi.require_version('GdkPixbuf','2.0')
from gi.repository import GdkPixbuf

class Zeros:
    def read(self,size):return b'\0'*size

class Tests(unittest.TestCase):
    def test_cached_frame_preserves_progress(self):
        from run_stream import STATUS
        STATUS['test']={'pages':2,'pages_known':False}
        result=refresh({'stream_id':'test','page':20,'pages':21,'pages_known':False})
        self.assertEqual(result['pages'],21)
        STATUS['test']={'pages':25,'pages_known':True}
        self.assertEqual(refresh(result)['pages'],25)
        STATUS.pop('test')

    def test_background_count_without_navigation_and_cleanup(self):
        from run_stream import start_count,count_state,CLIENTS
        import runpy,threading
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);images=root/'images';images.mkdir()
            for n in range(4):
                pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,64,48);pix.fill(0xff0000ff)
                pix.savev(str(images/(str(n)+'.png')),'png',[],[])
            from show_test_fixtures import fixture_api
            app=fixture_api();show=root/'show.run'
            app['build'](images,False,show,3,False,True,threading.Event(),lambda *args:None)
            with patch('preview_run.needs_stream',return_value=True):
                first=render_run_page(show,1)
                key=first['stream_id'];client=CLIENTS[key]
                self.assertIsNone(client.counter)
                start_count(key);process=client.counter
                start_count(key);self.assertIs(client.counter,process)
                until=time.monotonic()+8
                while time.monotonic()<until and not count_state(key)['pages_known']:time.sleep(.02)
                self.assertTrue(count_state(key)['pages_known']);self.assertEqual(count_state(key)['pages'],4)
                self.assertEqual(refresh(first)['pages'],4)
                second=render_run_page(show,2);self.assertTrue(second['pages_known']);self.assertEqual(second['pages'],4)
                clear_cache();self.assertNotIn(key,CLIENTS)

    def test_over_512_mib_stream_first_frames_without_tar_spool(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);show=root/'gross.run'
            with show.open('wb') as out:
                out.write(b'#!/bin/sh\n# This script was generated using Makeself test\nskip="4"\nexit 0\n')
                with gzip.GzipFile(fileobj=out,mode='wb',compresslevel=1) as zipped:
                    with tarfile.open(fileobj=zipped,mode='w|') as archive:
                        for n,color in [(1,0xff0000ff),(2,0x00ff00ff)]:
                            pix=GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB,False,8,64,48);pix.fill(color)
                            image=root/(str(n)+'.png');pix.savev(str(image),'png',[],[]);data=image.read_bytes()
                            member=tarfile.TarInfo('Bilder/'+str(n).zfill(9)+'.png');member.size=len(data)
                            archive.addfile(member,io.BytesIO(data))
                        padding=tarfile.TarInfo('grosse_zusatzdaten.bin');padding.size=600*1024*1024
                        archive.addfile(padding,Zeros())
            self.assertTrue(needs_stream(show))
            start=time.perf_counter();one=render_run_page(show,1);elapsed=time.perf_counter()-start
            self.assertFalse(one['pages_known']);self.assertEqual(tuple(one['pixbuf'].get_pixels()[:3]),(255,0,0))
            from run_stream import start_count,count_state
            start_count(one['stream_id']);until=time.monotonic()+8
            while time.monotonic()<until and not count_state(one['stream_id'])['pages_known']:time.sleep(.02)
            self.assertEqual(count_state(one['stream_id'])['pages'],2)
            self.assertTrue(count_state(one['stream_id'])['pages_known'])
            two=render_run_page(show,2);self.assertEqual(tuple(two['pixbuf'].get_pixels()[:3]),(0,255,0))
            end=render_run_page(show,3);self.assertTrue(end['pages_known']);self.assertEqual(end['pages'],2)
            self.assertEqual(end['page'],2);self.assertEqual(refresh(one)['pages'],2)
            paths=[Path(item[0].name) for item in CACHE.values()]
            self.assertTrue(all(not (path/'archive.tar').exists() for path in paths))
            self.assertLess(sum(p.stat().st_size for path in paths for p in path.iterdir()),1024*1024)
            print('600-MiB-Testshow: erstes Bild nach %.3f s'%elapsed)
            clear_cache();self.assertTrue(all(not path.exists() for path in paths))
