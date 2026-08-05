#!/usr/bin/env python3

import subprocess
import sys

def run(cmd):
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)

print("=" * 60)
print("RANGER DEPLOY")
print("=" * 60)

run(["python3", "-m", "py_compile", "app.py"])
run(["git", "status"])
run(["git", "add", "."])

message = input("\nCommit message: ").strip()
if not message:
    print("Commit message required.")
    sys.exit(1)

run(["git", "commit", "-m", message])
run(["git", "push", "origin", "main"])

print("\n✅ Deploy complete.")
print("Render will redeploy automatically.")
