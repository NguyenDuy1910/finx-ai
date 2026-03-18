#!/bin/bash
cd "$(dirname "$0")/.."

G='\033[0;32m' R='\033[0;31m' N='\033[0m'

check() {
  curl -sf --max-time 3 "$2" >/dev/null 2>&1 \
    && echo -e "  ${G}OK${N}  $1" \
    || echo -e "  ${R}FAIL${N}  $1  ($2)"
}

tcp() {
  nc -z localhost "$2" 2>/dev/null \
    && echo -e "  ${G}OK${N}  $1" \
    || echo -e "  ${R}FAIL${N}  $1  (localhost:$2)"
}

echo ""
echo "  Infrastructure"
tcp  "PostgreSQL" 5432
tcp  "FalkorDB"   6379
echo ""
echo "  Application"
check "API" "http://localhost:8080/api/v1/health"
check "UI"  "http://localhost:3000"
echo ""
