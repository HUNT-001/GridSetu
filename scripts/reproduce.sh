#!/usr/bin/env bash
# Re-run the full study from scratch and check that every committed result is reproduced.
#   pip install -r requirements-lock.txt
#   bash scripts/reproduce.sh
# Exits non-zero if outputs/results.json differs (ignoring run time) from the fresh run.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
OUT="$(mktemp -d)"
echo "Running the 3-seed study into $OUT (about 1-2 minutes) ..."
python -m gridsetu run --seeds 3 --out "$OUT" --quiet
python - "$OUT" <<'EOF'
import json, sys
new = json.load(open(f"{sys.argv[1]}/results.json"))
old = json.load(open("outputs/results.json"))
for d in (new, old):
    d["about"].pop("runtime_s", None)

def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            yield from diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, f"{path}[{i}]")
    elif a != b:
        yield path, a, b

d = list(diff(old, new))
if d:
    print(f"NOT REPRODUCED: {len(d)} values differ. First 15:")
    for p, a, b in d[:15]:
        print(f"  {p}: committed={a!r} fresh={b!r}")
    print("Check that you installed requirements-lock.txt (exact versions).")
    sys.exit(1)
print("REPRODUCED: fresh run matches outputs/results.json exactly.")
EOF
