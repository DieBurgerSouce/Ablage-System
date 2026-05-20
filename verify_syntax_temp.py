#!/usr/bin/env python3
"""Temporary syntax verification script."""
import sys
import py_compile

file_path = r"C:\Users\benfi\Ablage_System\app\api\v1\personal\departments.py"

try:
    py_compile.compile(file_path, doraise=True)
    print(f"✓ Syntax OK: {file_path}")
    sys.exit(0)
except py_compile.PyCompileError as e:
    print(f"✗ Syntax Error: {e}")
    sys.exit(1)
