#!/bin/zsh
# launchd: brain.sh <SLOT> <model>. One headless Claude run per slot. Log: logs/brain/<date>-<SLOT>.log
export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin
cd "$(dirname "$0")" || exit 1
mkdir -p logs/brain
LOG="logs/brain/$(date +%F)-$1.log"
# one brain at a time: an EVENT that collides with a scheduled run is left in .brain_event for that run
if ! mkdir .brain.lock 2>/dev/null; then
  [[ $(( $(date +%s) - $(stat -f %m .brain.lock) )) -lt 1800 ]] && { echo "$(date +%T) $1 skipped: brain busy" >> "$LOG"; exit 0; }
  rmdir .brain.lock; mkdir .brain.lock
fi
trap 'rmdir .brain.lock 2>/dev/null' EXIT
# skip weekends/NSE holidays (if the calendar expired, run anyway so the brain can fix it)
.venv/bin/python -c "import trader,sys
try: sys.exit(0 if trader.market_day() else 1)
except trader.Fatal: sys.exit(0)" || exit 0
# Allowlist (dontAsk = anything else is denied). Web content can't make the brain run arbitrary shell,
# read secrets, or edit its own launcher/permissions.
ALLOW=(Read Glob Grep WebSearch WebFetch Edit Write
  "Bash(.venv/bin/python trader.py *)" "Bash(.venv/bin/python angel.py price *)" "Bash(.venv/bin/python angel.py candles *)" "Bash(.venv/bin/python angel.py status)" "Bash(.venv/bin/python test_trader.py)"
  "Bash(.venv/bin/python live_test.py)" "Bash(.venv/bin/python backtest.py *)" "Bash(.venv/bin/python research_bt.py)"
  "Bash(date *)" "Bash(ls *)" "Bash(.venv/bin/python trader.py notify *)" "Bash(rm .brain_event)" "Bash(rm docs/live_test_result.json)")
# Secrets + session tokens unreadable; gate state (live-test result, bot state) changes only through trader.py.
DENY=("Read(./.env)" "Read(./.session.json)" "Read(./logs/app.log)" "Read(./logs/**/app.log)" "Read(../zerodha/**)"
  "Read(~/.ssh/**)" "Read(~/.config/gh/**)"
  "Edit(./.env)" "Edit(./brain.sh)" "Edit(./run.sh)" "Edit(./brain_prompt.md)" "Edit(./dashboard.py)"
  "Edit(./state_*.json)" "Edit(./docs/live_test_result.json)" "Edit(~/Library/**)" "Edit(~/.claude/**)"
  "Write(./.env)" "Write(./brain.sh)" "Write(./run.sh)" "Write(./brain_prompt.md)" "Write(./dashboard.py)"
  "Write(./state_*.json)" "Write(./docs/live_test_result.json)" "Write(~/Library/**)" "Write(~/.claude/**)"
  "Edit(./.venv/**)" "Write(./.venv/**)" "Edit(./dashboard.html)" "Write(./dashboard.html)" "Edit(./.gitignore)" "Write(./.gitignore)"
  "Edit(~/.zshrc)" "Write(~/.zshrc)" "Edit(~/.zprofile)" "Write(~/.zprofile)" "Edit(~/.zshenv)" "Write(~/.zshenv)" "Edit(~/.zlogin)" "Write(~/.zlogin)" "Edit(~/.bashrc)" "Write(~/.bashrc)" "Edit(~/.bash_profile)" "Write(~/.bash_profile)" "Edit(~/.profile)" "Write(~/.profile)" "Edit(~/.gitconfig)" "Write(~/.gitconfig)" "Edit(~/.config/**)" "Write(~/.config/**)" "Edit(./.git/**)" "Write(./.git/**)" "Edit(../.git/**)" "Write(../.git/**)" "Edit(./CLAUDE.md)" "Write(./CLAUDE.md)" "Edit(../CLAUDE.md)" "Write(../CLAUDE.md)" "Edit(./.claude/**)" "Write(./.claude/**)" "Edit(../.claude/**)" "Write(../.claude/**)")
# ponytail: brain may still Edit *.py (self-repair after a failed live run, user's ask 2026-11-05); prompt-injection via
# WebFetch -> code edit is the known residual risk. Full fix: drop WebFetch/WebSearch from runs that may edit code.
/usr/bin/caffeinate -i timeout 1500 /Users/harish/.local/bin/claude -p "$(cat brain_prompt.md)

SLOT: $1
NOW: $(date '+%F %T %Z')" --model "${2:-opus}" --permission-mode dontAsk \
  --allowedTools "${ALLOW[@]}" --disallowedTools "${DENY[@]}" < /dev/null >> "$LOG" 2>&1
echo "exit $? at $(date +%T)" >> "$LOG"
