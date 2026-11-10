#!/bin/zsh
# launchd entry point: run.sh <script> [args]. Output appended to logs/launchd.log
cd "$(dirname "$0")" || exit 1
echo "=== $(date '+%F %T') $*" >> logs/launchd.log
/usr/bin/caffeinate -i .venv/bin/python "$@" >> logs/launchd.log 2>&1
