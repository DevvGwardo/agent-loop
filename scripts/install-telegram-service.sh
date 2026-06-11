#!/usr/bin/env bash
# Install the finetuner Telegram bot as an always-on macOS background service
# (launchd LaunchAgent). It restarts on crash and on login.
#
#   ./scripts/install-telegram-service.sh           # install + start
#   ./scripts/install-telegram-service.sh uninstall # stop + remove
#
# Requires a repo-root .env with TELEGRAM_BOT_TOKEN and a model provider key
# (e.g. OPENROUTER_API_KEY) — the service runs `loop telegram`, which sources it.
set -euo pipefail

SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LABEL="dev.finetuner.telegram"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs/finetuner"
LOOP_BIN="$SCRIPT_DIR/loop"

if [ "${1:-install}" = "uninstall" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Uninstalled $LABEL"
  exit 0
fi

if [ ! -f "$ROOT/.env" ]; then
  echo "warning: $ROOT/.env not found — create it with TELEGRAM_BOT_TOKEN and a provider key." >&2
fi

mkdir -p "$LOG_DIR" "$(dirname "$PLIST")"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$LOOP_BIN</string>
    <string>telegram</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/telegram.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/telegram.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST_EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed and started $LABEL"
echo "  logs:   $LOG_DIR/telegram.{out,err}.log"
echo "  stop:   launchctl unload $PLIST"
echo "  status: launchctl list | grep finetuner"
