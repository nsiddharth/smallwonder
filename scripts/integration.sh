#!/bin/bash
# Full-stack integration test. Real hardware, real models, real downloads.
# Usage: scripts/integration.sh [--backend lmstudio|llamaswap]
set -euo pipefail
BACKEND=${2:-lmstudio}
[ "${1:-}" = "--backend" ] && BACKEND=$2

SW=${SW:-smallwonder}   # override with .venv/bin/smallwonder for dev

echo "=== setup ($BACKEND) ==="
$SW setup --backend "$BACKEND" --yes

echo "=== status ==="
$SW status

echo "=== doctor ==="
$SW doctor || { echo "doctor found issues"; exit 1; }

echo "=== evals ==="
$SW evals

echo "=== reasoning_effort escape hatch ==="
KEY=$(awk '/^api_key:/ {print $2}' "$HOME/.smallwonder/config.yaml")
ANSWER=$(curl -sf --max-time 120 http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"model":"fast","messages":[{"role":"user","content":"Say ready"}],"max_tokens":50,"reasoning_effort":"none"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])')
echo "fast says: $ANSWER"

echo "=== ALL GREEN ==="
