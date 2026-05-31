#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
QUERY="${LEGAL_RAG_WARMUP_QUERY:-试用期最长多久？}"

curl -fsS "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "$(python3 - "$QUERY" <<'PY'
import json, sys
print(json.dumps({"query": sys.argv[1]}, ensure_ascii=False))
PY
)"
echo
