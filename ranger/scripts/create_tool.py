#!/usr/bin/env python3

from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("name", help="Tool name, e.g. rotate-pdf")
args = parser.parse_args()

ROOT = Path.cwd()

folder = ROOT / "ranger" / "generated"
folder.mkdir(parents=True, exist_ok=True)

tool = folder / f"{args.name}.txt"

tool.write_text(
f"""RANGER TOOL

Name: {args.name}

Status:
[ ] Backend
[ ] Frontend
[ ] SEO
[ ] Test
[ ] Deploy
"""
)

print("="*60)
print(f"Created blueprint for: {args.name}")
print(tool)
