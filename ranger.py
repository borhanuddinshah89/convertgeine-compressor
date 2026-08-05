#!/usr/bin/env python3

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent

parser = argparse.ArgumentParser(
    prog="Ranger",
    description="ConvertGeine Builder"
)

sub = parser.add_subparsers(dest="command")

sub.add_parser("status")
sub.add_parser("check")

args = parser.parse_args()

if args.command == "status":
    print("="*60)
    print("RANGER STATUS")
    print("="*60)

    subprocess.run(["git","status"])

elif args.command == "check":
    print("="*60)
    print("RANGER CHECK")
    print("="*60)

    subprocess.run(["python3","-m","py_compile","app.py"])

else:
    parser.print_help()
