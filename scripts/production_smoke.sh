#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8080}"
API_AUTH_TOKEN="${API_AUTH_TOKEN:-}"

auth_args=()
if [[ -n "$API_AUTH_TOKEN" ]]; then
  auth_args=(-H "X-API-Key: $API_AUTH_TOKEN")
fi

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

cat >"$tmp_file" <<'TXT'
员工手册：工资发放日为每月十日。迟到三次记一次书面提醒。
TXT

echo "== health =="
curl -fsS "$BASE_URL/api/health"
echo

echo "== ready =="
curl -fsS "$BASE_URL/api/ready"
echo

echo "== upload policy =="
curl -fsS "${auth_args[@]}" -F "file=@${tmp_file};filename=employee_policy.txt" \
  "$BASE_URL/api/documents/upload"
echo

echo "== list documents =="
curl -fsS "${auth_args[@]}" "$BASE_URL/api/documents"
echo

echo "== chat =="
curl -fsS "$BASE_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"query":"试用期最长多久？"}'
echo

echo "== contract review =="
curl -fsS "$BASE_URL/api/review/contract" \
  -H "Content-Type: application/json" \
  -d '{"contract_text":"甲方可随时解除合同且不支付经济补偿。乙方自愿放弃社保。"}'
echo
