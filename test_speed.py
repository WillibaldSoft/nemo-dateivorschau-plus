# SPDX-License-Identifier: GPL-3.0-or-later
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from speed_cache import PreviewCache

class Tests(unittest.TestCase):
    def test_cache_hit_change_invalidation_and_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'text.txt'; path.write_text('eins')
            cache = PreviewCache(budget=2200, entries=2)
            calls = []
            def load():
                calls.append(1)
                return {'kind': 'text', 'text': path.read_text()}
            first = cache.get(path, 'text', 1, load)
            first['text'] = 'mutated result'
            self.assertEqual(cache.get(path, 'text', 1, load)['text'], 'eins')
            self.assertEqual(len(calls), 1)
            path.write_text('zwei und verändert')
            self.assertEqual(cache.get(path, 'text', 1, load)['text'], 'zwei und verändert')
            self.assertEqual(len(calls), 2)
            for page in range(5): cache.get(path, 'text', page, load)
            self.assertLessEqual(cache.bytes, cache.budget)
            self.assertLessEqual(len(cache.data), 2)
            path.write_text('x' * 5000)
            cache.get(path, 'text', 1, load)
            self.assertLessEqual(cache.bytes, cache.budget)
