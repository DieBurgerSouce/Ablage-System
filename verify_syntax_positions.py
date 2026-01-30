#!/usr/bin/env python3
"""Syntax-Verifikation für positions.py"""

import py_compile
import sys

try:
    py_compile.compile(
        'app/api/v1/personal/positions.py',
        doraise=True
    )
    print("✓ Syntax-Verifikation erfolgreich für app/api/v1/personal/positions.py")
    sys.exit(0)
except py_compile.PyCompileError as e:
    print(f"✗ Syntax-Fehler gefunden:")
    print(e)
    sys.exit(1)
