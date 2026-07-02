#!/usr/bin/env bash
# Liest die Add-on-Optionen (/data/options.json) und exportiert sie als
# Umgebungsvariablen, wie AT-Panther sie erwartet. Danach startet main.py.
set -e

eval "$(python3 - <<'PYEOF'
import json, shlex

with open("/data/options.json") as f:
    o = json.load(f)

env = {
    "APP_NAME": "AT-Panther HA-Addon",
    "RUFNUMMER": o.get("rufnummer", ""),
    "PASSWORT": o.get("passwort", ""),
    "TELEGRAM": "1" if o.get("telegram") else "0",
    "BOT_TOKEN": o.get("bot_token") or "",
    "CHAT_ID": o.get("chat_id") or "",
    "SLEEP_MODE": o.get("sleep_mode", "smart"),
    "SLEEP_INTERVAL": str(o.get("sleep_interval", 90)),
    "BROWSER": o.get("browser", "chromium"),
    "DATA_DIR": "/data",
}
for k, v in env.items():
    print(f"export {k}={shlex.quote(v)}")
PYEOF
)"

if [ -z "$PASSWORT" ]; then
    echo "FEHLER: Kein Passwort gesetzt. Bitte in der Add-on-Konfiguration eintragen." >&2
    exit 1
fi

cd /app
exec python -u main.py
