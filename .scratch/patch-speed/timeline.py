"""Stage timeline of one patch run from `adb logcat -v epoch | grep HokAce` lines.

Stages run from one worker progress line to the next; engine bridge calls report their own duration.
"""
import json
import re
import sys

LINE = re.compile(r"^\s*(\d+\.\d+)\s+\d+\s+\d+\s+\w\s+(HokAce\S*?):\s(.*)$")
progress, engine = [], []
for raw in open(sys.argv[1], encoding="utf-8", errors="replace"):
    match = LINE.match(raw)
    if not match:
        continue
    time, tag, message = float(match[1]), match[2], match[3]
    if tag == "HokAce/worker" and message.startswith(("Progress: ", "Result: ")):
        progress.append((time, message.split(": ", 1)[1][:90]))
    elif tag == "HokAce/engine":
        found = re.match(r"(\w+) finished in (\d+) ms", message)
        if found:
            engine.append((found[1], int(found[2]) / 1000))

stages = []
for (start, name), (end, _) in zip(progress, progress[1:]):
    stages.append({"stage": name, "seconds": round(end - start, 1)})
total = progress[-1][0] - progress[0][0] if progress else 0
print(f"{'seconds':>8}  stage")
for stage in stages:
    print(f"{stage['seconds']:8.1f}  {stage['stage']}")
print(f"{total:8.1f}  TOTAL (first to last worker line)")
print("\nengine calls:")
for name, seconds in engine:
    print(f"{seconds:8.1f}  {name}")
if len(sys.argv) > 2:
    with open(sys.argv[2], "w", encoding="utf-8") as output:
        json.dump({"stages": stages, "engine": engine, "total": total}, output, indent=1)
