#!/usr/bin/env python3

from pathlib import Path
import shutil

deleted = 0

patterns = [
    "*.backup",
    "*.before-*",
    "*.pyc",
]

for pattern in patterns:
    for f in Path(".").rglob(pattern):
        try:
            f.unlink()
            print(f"🗑️  {f}")
            deleted += 1
        except Exception:
            pass

for d in Path(".").rglob("__pycache__"):
    try:
        shutil.rmtree(d)
        print(f"🗑️  {d}")
        deleted += 1
    except Exception:
        pass

print()
print(f"✅ Cleanup complete ({deleted} items removed)")
