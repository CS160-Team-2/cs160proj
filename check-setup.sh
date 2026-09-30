#!/bin/bash
# OFS setup doctor — macOS
# Run:  bash check-setup.sh
#
# Checks everything the spike needs and tells you what is missing.
# Changes nothing on your machine.

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'; BOLD=$'\033[1m'; OFF=$'\033[0m'

PASS=0; WARN=0; FAIL=0

ok()   { printf "  ${GREEN}PASS${OFF}  %-28s %s\n" "$1" "$2"; PASS=$((PASS+1)); }
warn() { printf "  ${YELLOW}WARN${OFF}  %-28s %s\n" "$1" "$2"; WARN=$((WARN+1)); }
bad()  { printf "  ${RED}FAIL${OFF}  %-28s %s\n" "$1" "$2"; FAIL=$((FAIL+1)); }
head2(){ printf "\n${BOLD}${BLUE}%s${OFF}\n" "$1"; }

printf "${BOLD}OFS Feasibility Spike — Setup Check${OFF}\n"

# ---------------------------------------------------------------- machine
head2 "Machine"
printf "  macOS %s on %s\n" "$(sw_vers -productVersion 2>/dev/null)" "$(uname -m)"
if [ "$(uname -m)" = "arm64" ]; then
  ok "Apple Silicon" "use ARM64 downloads for everything"
else
  warn "Intel Mac" "ARM notes in the docs do not apply to you"
fi

# ---------------------------------------------------------------- python
head2 "Python"
if command -v python3 >/dev/null 2>&1; then
  PYV=$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null)
  case "$PYV" in
    3.11|3.12) ok "python3 $PYV" "$(command -v python3)" ;;
    3.13|3.14) bad "python3 $PYV" "too new — some packages have no wheels. Install 3.12" ;;
    3.10)      warn "python3 $PYV" "should work, but 3.12 is the tested version" ;;
    *)         bad "python3 $PYV" "too old — install 3.12" ;;
  esac
  python3 -c "import venv" 2>/dev/null && ok "venv module" "available" \
    || bad "venv module" "missing — reinstall Python from python.org"
else
  bad "python3" "NOT FOUND — install from python.org/downloads/macos"
fi

# ---------------------------------------------------------------- node
head2 "Node.js"
if command -v node >/dev/null 2>&1; then
  NV=$(node --version | tr -d 'v'); NMAJ=${NV%%.*}
  if [ "$NMAJ" -ge 20 ] 2>/dev/null; then
    ok "node v$NV" "$(command -v node)"
  else
    bad "node v$NV" "Tailwind v4 needs Node 20+. Install the current LTS"
  fi
else
  bad "node" "NOT FOUND — install LTS from nodejs.org (ARM64 .pkg)"
fi
command -v npm >/dev/null 2>&1 && ok "npm $(npm --version)" "" \
  || bad "npm" "NOT FOUND — comes with Node"

# ---------------------------------------------------------------- mysql
head2 "MySQL"
MYSQLBIN=""
for p in /usr/local/mysql/bin/mysql /opt/homebrew/bin/mysql "$(command -v mysql 2>/dev/null)"; do
  [ -x "$p" ] && MYSQLBIN="$p" && break
done
if [ -n "$MYSQLBIN" ]; then
  ok "mysql client" "$($MYSQLBIN --version | sed 's/.*Distrib //;s/,.*//') at $MYSQLBIN"
else
  bad "mysql client" "NOT FOUND — install MySQL Community Server (macOS ARM DMG)"
fi

if nc -z 127.0.0.1 3306 >/dev/null 2>&1; then
  ok "MySQL server" "running and listening on 3306"
else
  bad "MySQL server" "NOT running — System Settings > MySQL > Start MySQL Server"
fi

if [ -d "/Applications/MySQLWorkbench.app" ]; then
  ok "MySQL Workbench" "installed"
else
  warn "MySQL Workbench" "not in /Applications — you can still use the mysql CLI"
fi

# ---------------------------------------------------------------- apache
head2 "Apache"
if command -v httpd >/dev/null 2>&1; then
  ok "httpd" "$(httpd -v 2>/dev/null | head -1 | sed 's/Server version: //')"
  MODS=$(httpd -M 2>/dev/null)
  for m in proxy_module proxy_http_module rewrite_module; do
    echo "$MODS" | grep -q "$m" \
      && ok "  mod_${m%_module}" "enabled" \
      || warn "  mod_${m%_module}" "not enabled yet — see deploy/APACHE.md Part 2"
  done
else
  warn "httpd" "not found — unusual on macOS; Apache step will need Homebrew"
fi

# ---------------------------------------------------------------- ports
head2 "Ports"
check_port() {
  if nc -z 127.0.0.1 "$1" >/dev/null 2>&1; then
    [ "$1" = "3306" ] && ok "port $1" "in use — MySQL, as expected" \
                      || warn "port $1" "IN USE — $2"
  else
    [ "$1" = "3306" ] && bad "port $1" "free — MySQL is not running" \
                      || ok "port $1" "free — $2"
  fi
}
check_port 3306 "MySQL"
check_port 5001 "Flask will use this"
check_port 5173 "Vite will use this"
check_port 8080 "Apache will use this"
if nc -z 127.0.0.1 5000 >/dev/null 2>&1; then
  warn "port 5000" "in use (probably AirPlay Receiver) — this is why we use 5001"
fi

# ---------------------------------------------------------------- git
head2 "Other tools"
command -v git >/dev/null 2>&1 && ok "git" "$(git --version | sed 's/git version //')" \
  || bad "git" "NOT FOUND — run: xcode-select --install"
command -v curl >/dev/null 2>&1 && ok "curl" "available" || warn "curl" "missing"

# ---------------------------------------------------------------- project
head2 "Project files"
HERE="$(cd "$(dirname "$0")" && pwd)"
for f in backend/app.py backend/db.py backend/rules.py backend/schema.sql \
         backend/requirements.txt backend/test_integration.py \
         frontend/package.json deploy/ofs.conf; do
  [ -f "$HERE/$f" ] && ok "$f" "" || bad "$f" "MISSING"
done

[ -d "$HERE/backend/.venv" ] && ok "backend/.venv" "created" \
  || warn "backend/.venv" "not yet — Step 3 of the walkthrough creates it"
[ -f "$HERE/backend/.env" ] && ok "backend/.env" "created" \
  || warn "backend/.env" "not yet — copy from .env.example in Step 3"
[ -d "$HERE/frontend/node_modules" ] && ok "frontend/node_modules" "installed" \
  || warn "frontend/node_modules" "not yet — Step 5 runs npm install"

# ---------------------------------------------------------------- database
head2 "Database contents"
if [ -n "$MYSQLBIN" ] && nc -z 127.0.0.1 3306 >/dev/null 2>&1; then
  OUT=$("$MYSQLBIN" -u cs160team2 -pteam2_password -D ofs \
        -e "SELECT COUNT(*) FROM products;" 2>&1)
  if echo "$OUT" | grep -qi "access denied"; then
    warn "cs160team2 login" "user not created yet — run schema.sql (Step 2)"
  elif echo "$OUT" | grep -qi "unknown database"; then
    warn "ofs database" "not created yet — run schema.sql (Step 2)"
  elif echo "$OUT" | grep -q "[0-9]"; then
    N=$(echo "$OUT" | tail -1)
    [ "$N" -ge 3 ] 2>/dev/null && ok "ofs.products" "$N rows — schema loaded" \
                               || warn "ofs.products" "$N rows — expected 3+"
  else
    warn "database check" "could not verify — run schema.sql (Step 2)"
  fi
else
  warn "database check" "skipped — MySQL not reachable"
fi

# ---------------------------------------------------------------- summary
printf "\n${BOLD}Summary:${OFF} ${GREEN}%d pass${OFF}  ${YELLOW}%d warn${OFF}  ${RED}%d fail${OFF}\n" \
  "$PASS" "$WARN" "$FAIL"

if [ "$FAIL" -gt 0 ]; then
  printf "\n${RED}Install the FAIL items before starting.${OFF} WARN items are things\n"
  printf "the walkthrough will create for you as you go.\n"
else
  printf "\n${GREEN}Nothing blocking.${OFF} Open WALKTHROUGH.md and start at Step 2.\n"
fi
