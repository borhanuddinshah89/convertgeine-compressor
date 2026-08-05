#!/usr/bin/env python3

from pathlib import Path

APP = Path("app.py")

print("=" * 60)
print("RANGER BUILDER")
print("=" * 60)

if not APP.exists():
    print("❌ app.py not found")
    raise SystemExit(1)

text = APP.read_text()

if '@app.post("/pdf-to-jpg")' in text:
    print("✅ PDF to JPG endpoint already exists.")
    raise SystemExit(0)

print("✅ app.py loaded")
print("📍 Ready to add PDF → JPG endpoint.")
print()
print("Next step: Ranger will inject the endpoint automatically.")
