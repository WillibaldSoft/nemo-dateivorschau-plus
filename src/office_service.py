#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""One private, reusable converter; exits when its owning preview closes."""
import json
import sys
from pathlib import Path
from office_convert import OfficeSession

session = None
try:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if session is None:
                session = OfficeSession(Path(sys.argv[1]).absolute())
            session.convert(Path(request['source']), Path(request['output']))
            response = {'ok': True}
        except Exception as exc:
            response = {'error': str(exc)}
        print(json.dumps(response), flush=True)
finally:
    if session is not None:
        session.close()
