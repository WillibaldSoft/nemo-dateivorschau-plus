#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stream at most 2000 member headers/one MiB, kill reader on limit/timeout."""
from pathlib import Path
import subprocess
import shutil
import sys


def main():
    process = subprocess.Popen([shutil.which('bsdtar') or '/usr/bin/bsdtar', '-tvf', str(Path(sys.argv[1]).absolute())],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    total = 0
    print(Path(sys.argv[1]).name + '\n')
    try:
        for index in range(2000):
            line = process.stdout.readline(8193)
            if not line: break
            total += len(line)
            clean = ''.join(c if c.isprintable() or c in '\t' else ' ' for c in line.decode('utf-8', 'replace')).rstrip()
            print(clean)
            if len(line) > 8192 or total > 1024 * 1024:
                print('\n[Auflistung gekürzt]'); process.kill(); return
        else:
            print('\n[Maximal 2000 Einträge]'); process.kill(); return
        if process.wait(): raise ValueError('Archiv nicht lesbar.')
    finally:
        if process.poll() is None: process.kill()
        process.wait()

if __name__ == '__main__':
    try: main()
    except Exception: sys.exit(1)
