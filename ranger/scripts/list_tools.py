#!/usr/bin/env python3

from pathlib import Path

print("=" * 60)
print("CONVERTGEINE TOOLS")
print("=" * 60)

routes = Path("routes")

if not routes.exists():
    print("No routes directory found.")
    raise SystemExit

count = 0

for file in sorted(routes.glob("*.py")):
    if file.name == "__init__.py":
        continue
    print("•", file.stem)
    count += 1

print()
print(f"Total tools: {count}")
