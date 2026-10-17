# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared bounded LRU of decoded previews; changed files invalidate themselves."""
from collections import OrderedDict
import threading

class PreviewCache:
    def __init__(self, budget=96 * 1024 * 1024, entries=24):
        self.budget, self.entries = budget, entries
        self.data = OrderedDict()
        self.bytes = 0
        self.lock = threading.Lock()

    def get(self, path, kind, page, loader):
        stat = path.stat()
        key = (str(path.absolute()), kind, page, stat.st_ino, stat.st_size,
               stat.st_mtime_ns, stat.st_ctime_ns)
        with self.lock:
            if key in self.data:
                value, size = self.data.pop(key)
                self.data[key] = value, size
                return dict(value)
        value = loader()
        after = path.stat()
        if (stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            return value
        pixbuf = value.get('pixbuf')
        size = (pixbuf.get_rowstride() * pixbuf.get_height() if pixbuf else 0)
        size += len(value.get('text', '').encode('utf-8')) + 1024
        size += len(value.get('spans', [])) * 256
        with self.lock:
            if size <= self.budget:
                if key in self.data:
                    self.bytes -= self.data.pop(key)[1]
                self.data[key] = dict(value), size
                self.bytes += size
                while self.bytes > self.budget or len(self.data) > self.entries:
                    _, (_, old_size) = self.data.popitem(last=False)
                    self.bytes -= old_size
        return value

CACHE = PreviewCache()
