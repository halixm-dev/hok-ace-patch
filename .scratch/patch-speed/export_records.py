"""From a patcher diagnostic export: per session, the staged SHA-256 of every written file and the build time."""
import base64
import json
import re
import sys

records = {}
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    if line.startswith('{"path"'):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        records[value["path"]] = base64.b64decode(value["raw_base64"])

result = {}
for path, raw in records.items():
    match = re.match(r"sessions/([^/]+)/(journal\.json|metrics\.json|build\.log)$", path)
    if not match:
        continue
    session = result.setdefault(match[1], {})
    if match[2] == "metrics.json":
        session["metrics"] = json.loads(raw)
    elif match[2] == "build.log":
        session["build_log_lines"] = raw.decode("utf-8", "replace").count("\n")
    else:
        text = raw.decode("utf-8", "replace")
        writes = dict(re.findall(r'"path":"packages\\?/([^"]+)","sha256":"([0-9a-f]{64})"', text.replace("\\/", "/")))
        session["written"] = dict(sorted(writes.items()))
        phase = re.search(r'"phase":"([A-Z_]+)"', text)
        session["phase"] = phase[1] if phase else None
print(json.dumps(result, indent=1))
