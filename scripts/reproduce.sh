#!/usr/bin/env bash
# Re-run the full study from scratch and check that every committed result is reproduced.
#   pip install -r requirements-lock.txt
#   bash scripts/reproduce.sh
# Exits non-zero if any value in outputs/results.json differs from the fresh run by more than
# one part in a billion (relative). Differences below that are floating-point noise from a
# different CPU or maths library, far below the precision of any reported figure.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=src
OUT="$(mktemp -d)"
echo "Running the 3-seed study into $OUT (about 1-2 minutes) ..."
python -m gridsetu run --seeds 3 --out "$OUT" --quiet
echo "Running the real-data validation (about 40 seconds) ..."
python -m gridsetu real-data --out "$OUT/real_data" > /dev/null
echo "Running the business case (about a minute) ..."
python -m gridsetu economics --out "$OUT/economics" > /dev/null
python -m gridsetu ownership --out "$OUT/economics" > /dev/null
python - "$OUT" <<'EOF'
import json, math, sys

def diff(a, b, path=""):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            yield from diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            yield from diff(x, y, f"{path}[{i}]")
    elif isinstance(a, float) and isinstance(b, float):
        if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12):
            yield path, a, b
    elif a != b:
        yield path, a, b

failed = False
for rel in ("results.json", "real_data/real_data.json", "economics/economics.json", "economics/ownership.json"):
    new = json.load(open(f"{sys.argv[1]}/{rel}"))
    old = json.load(open(f"outputs/{rel}"))
    for doc in (new, old):
        doc.get("about", {}).pop("runtime_s", None)
    d = list(diff(old, new))
    if d:
        failed = True
        print(f"NOT REPRODUCED: outputs/{rel}: {len(d)} values differ. First 15:")
        for p, a, b in d[:15]:
            print(f"  {p}: committed={a!r} fresh={b!r}")
    else:
        print(f"REPRODUCED: outputs/{rel} (every value within 1 part in a billion).")
if failed:
    print("Check that you installed requirements-lock.txt (exact versions).")
    sys.exit(1)
EOF
