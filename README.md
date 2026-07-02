# AT-Panther Home-Assistant-Add-on

Wrapper um [AT-Panther](https://gitlab.com/docker_point/at-panther): überwacht
das ALDI-Talk-Datenvolumen per Playwright-Browser-Automation und bucht bei
Unterschreitung von 1 GB automatisch 1 GB nach („Unendlich nachbuchen", im
Tarif kostenlos).

## Installation

1. In Home Assistant: Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories
2. `https://github.com/DirtDrift/at-panther-addon` hinzufügen
3. "AT-Panther (ALDI Talk)" installieren (Image-Build dauert einige Minuten)
4. In der Konfiguration Rufnummer und Passwort eintragen, dann starten

## Abweichungen vom Original (`main.py` gepatcht)

Das Original-Image ist von 2025; ALDI Talk hat Portal und Login-Seite seitdem
umgebaut. Dieses Add-on überschreibt `/app/main.py` mit einer gefixten Version:

- **Login-Submit** (v1.0.1): Der Login-Button hat keine stabile CSS-Klasse
  mehr. Submit per Enter im Passwortfeld (`#input-6`), alter Selektor bleibt
  als Fallback.
- **Datenvolumen auslesen** (v1.0.2): Die alten `nth-child`-Selektoren greifen
  nicht mehr. Das Inland-Meter wird jetzt über das Footer-Label („Inland") des
  `one-usage-meter`-Elements gefunden, der Wert aus dessen `one-heading`
  gelesen. Nachgebucht wird über den `one-button[slot="action"]` desselben
  Meters.
- **Overlay-Fix** (v1.0.3): Ein unsichtbares Usercentrics-Consent-Overlay
  fängt Pointer-Events ab. `#usercentrics-root` wird vor dem Klick entfernt;
  falls der Klick trotzdem blockiert, `dispatch_event("click")` als Fallback.

Hinweis: Bei ≥ 1 GB Restvolumen öffnet der „1 GB"-Button nur ein Info-Modal
und bucht nichts – versehentliche Klicks sind harmlos.

## Optionen

| Option | Default | Beschreibung |
| --- | --- | --- |
| `rufnummer` | – | ALDI-Talk-Rufnummer (Login) |
| `passwort` | – | Portal-Passwort |
| `telegram` | `false` | Telegram-Benachrichtigungen aktivieren |
| `bot_token` / `chat_id` | – | Telegram-Zugangsdaten (nur bei `telegram: true`) |
| `sleep_mode` | `smart` | `smart`, `fixed`, `random`, `random_MIN-MAX` |
| `sleep_interval` | `90` | Sekunden, nur bei `fixed` |
| `browser` | `chromium` | `chromium`, `firefox`, `webkit` |

## Struktur

- `repository.yaml` – macht das Repo als HA-Add-on-Store-Quelle nutzbar
- `at_panther/config.yaml` – Add-on-Metadaten, Optionen, Schema
- `at_panther/Dockerfile` – basiert auf dem Original-Image, ersetzt `main.py` und Entrypoint
- `at_panther/run.sh` – liest `/data/options.json`, exportiert ENV-Variablen, startet `main.py`
- `at_panther/main.py` – gepatchtes Original-Skript (siehe oben)

## Release-Ablauf

Version in `at_panther/config.yaml` hochzählen, committen, pushen. In HA
erscheint das Update nach einem Store-Reload (oder automatisch nach ein paar
Stunden).
