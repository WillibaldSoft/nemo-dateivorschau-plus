# SPDX-License-Identifier: GPL-3.0-or-later
import sys,tempfile,subprocess,time,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).parent/'src'),str(Path(__file__).parent)]
from preview_document import kind,read_text
from text_format import LIMIT,MAX_SPANS
from preview_extra import media_preview
from preview_widget import Preview,Gtk

class Tests(unittest.TestCase):
    def test_markdown_code_limits_and_no_external_loads(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.md'
            path.write_text('# Titel\n**fett** und *kursiv* `code`\n[Link](https://invalid.example)\n```py\nprint(1)\n```\n')
            result=read_text(path)
            self.assertTrue(result['text'].startswith('Titel\nfett'))
            self.assertTrue({'heading','bold','italic','code','link'} <= {s[0] for s in result['spans']})
            for _,a,b in result['spans']: self.assertTrue(0<=a<=b<=len(result['text']))
            path=path.with_suffix('.py');path.write_text('def f():\n    return "Hallo" # comment\n')
            result=read_text(path)
            self.assertTrue({'keyword','string','comment'} <= {s[0] for s in result['spans']})
            path.write_text('x\n'*(LIMIT//2+1));result=read_text(path)
            self.assertFalse(result['spans'])
            self.assertIn('Rohtext',result['note'])
            path.write_text('1 '*20000);self.assertLessEqual(len(read_text(path)['spans']),MAX_SPANS)
    def test_ts_video_and_typescript(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.ts';path.write_text('export const n: number = 42;\n')
            self.assertEqual(kind(path),'text')
            self.assertTrue(read_text(path)['spans'])
            video=Path(folder)/'video.ts'
            subprocess.run(['/usr/bin/ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=10','-t','1','-c:v','mpeg2video','-f','mpegts',str(video)],check=True,timeout=15)
            self.assertEqual(kind(video),'video')
            self.assertEqual(media_preview(video,True)['kind'],'video')
    def test_gtk_details_and_formatted_tags(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.md';path.write_text('# Überschrift\n**Text**')
            window=Gtk.OffscreenWindow();pane=Preview(sidebar=True);window.add(pane);window.show_all()
            pane.set_selection(path)
            deadline=time.monotonic()+5
            while pane.text_view.get_buffer().get_char_count()==0 and time.monotonic()<deadline:
                while Gtk.events_pending():Gtk.main_iteration_do(False)
                time.sleep(.01)
            self.assertIn('Größe:',pane.file_details_label.get_text())
            self.assertIn(str(path),pane.file_details_label.get_text())
            self.assertTrue(pane.text_view.get_buffer().get_start_iter().has_tag(pane.text_view.get_buffer().get_tag_table().lookup('heading')))
            self.assertFalse(pane.detail_scroll.get_visible())
            pane.set_selection(None);self.assertEqual(pane.file_details_label.get_text(),'')
            window.destroy()
