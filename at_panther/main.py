# -*- coding: utf-8 -*-
import json, time, requests, logging, random, os, sys, io, re
try:
    import psutil
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "psutil"])
    import psutil
from playwright.sync_api import sync_playwright, TimeoutError

# -----------------------------
# Ordner & Dateien im Volume
# -----------------------------
DATA_DIR = os.environ.get("DATA_DIR", "/data")
os.makedirs(DATA_DIR, exist_ok=True)
COOKIE_FILE = os.path.join(DATA_DIR, "cookies.json")
STATE_FILE  = os.path.join(DATA_DIR, "state.json")

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# -----------------------------
# Konstanten
# -----------------------------
LOGIN_URL = "https://login.alditalk-kundenbetreuung.de/signin/XUI/#login/"
DASHBOARD_URL = "https://www.alditalk-kundenportal.de/portal/auth/uebersicht/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/139.0"
HEADLESS = True

# -----------------------------
# Konfig direkt aus ENV
# -----------------------------
RUFNUMMER      = os.environ.get("RUFNUMMER")
PASSWORT       = os.environ.get("PASSWORT")
BOT_TOKEN      = os.environ.get("BOT_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")
TELEGRAM       = os.environ.get("TELEGRAM", "0")
SLEEP_MODE     = os.environ.get("SLEEP_MODE", "random")
SLEEP_INTERVAL = os.environ.get("SLEEP_INTERVAL", "90")
BROWSER        = os.environ.get("BROWSER", "chromium").lower()

if BROWSER not in ["chromium", "firefox", "webkit"]:
    logging.warning(f"Ungültiger Browser '{BROWSER}', fallback auf 'chromium'")
    BROWSER = "chromium"

TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage" if BOT_TOKEN else None

# -----------------------------
# State laden/schreiben
# -----------------------------
LAST_GB = 0.0
try:
    with open(STATE_FILE, "r") as f:
        data = json.load(f)
        if isinstance(data, dict) and "last_gb" in data:
            LAST_GB = float(data["last_gb"])
except Exception:
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"last_gb": 0.0}, f)
    except Exception as e:
        logging.error(f"Konnte 'state.json' nicht erstellen: {e}")

# -----------------------------
# Hilfsfunktionen
# -----------------------------
def is_low_memory():
    return psutil.virtual_memory().total / (1024**3) <= 2.0

def get_launch_args(browser):
    args = []
    # Root oder wenig RAM → Sandbox / SHM optimieren
    if browser == "chromium" and (os.geteuid() == 0 or is_low_memory()):
        args += ["--no-sandbox", "--disable-dev-shm-usage"]
    return args

def send_telegram_message(message, retries=3):
    if TELEGRAM == "1" and TELEGRAM_URL and CHAT_ID:
        for attempt in range(retries):
            try:
                r = requests.post(TELEGRAM_URL, data={"chat_id": CHAT_ID, "text": message})
                if r.status_code == 200:
                    logging.info("Telegram gesendet.")
                    return True
                else:
                    logging.warning(f"Telegram HTTP {r.status_code}: {r.text}")
            except Exception as e:
                logging.error(f"Telegram Fehler (Versuch {attempt+1}): {e}")
        logging.error("Telegram konnte nicht gesendet werden.")
        return False
    else:
        logging.debug("Telegram deaktiviert oder nicht konfiguriert.")
        return False

def wait_and_click(page, selector, timeout=5000, retries=5):
    for attempt in range(retries):
        try:
            logging.info(f"Klicke {selector} (Versuch {attempt+1}/{retries}) ...")
            page.wait_for_selector(selector, timeout=timeout)
            page.click(selector)
            return True
        except TimeoutError:
            logging.warning(f"{selector} nicht gefunden, retry ...")
            time.sleep(1)
        except Exception as e:
            logging.warning(f"Fehler beim Klicken: {e}")
            time.sleep(1)
    logging.error(f"Konnte {selector} nicht klicken.")
    return False

def handle_cookie_banner(page):
    try:
        # 1) Direkter Test-ID Button
        deny_selector = 'button[data-testid="uc-deny-all-button"]'
        try:
            button = page.query_selector(deny_selector)
            if button and button.is_visible():
                logging.info("Cookie-Banner: 'Ablehnen' gefunden (data-testid)")
                button.click()
                time.sleep(1)
                return
        except Exception:
            pass

        # 2) Fallback über Button-Texte
        deny_keywords = ["Verweigern", "Ablehnen", "Decline"]
        buttons = page.query_selector_all("button")
        for button in buttons:
            try:
                text = (button.text_content() or "").strip()
                if not text:
                    continue
                lower = text.lower()
                if any(k.lower() in lower for k in deny_keywords):
                    if button.is_visible():
                        logging.info(f"Cookie-Banner: Button '{text}'")
                        try:
                            button.click()
                            time.sleep(1)
                            return
                        except Exception as click_error:
                            logging.warning(f"Cookie konnte nicht geschlossen werden: {click_error}")
                            return
            except Exception:
                continue
        logging.info("Cookie-Banner: nichts zu tun")
    except Exception as e:
        logging.warning(f"Fehler im handle_cookie_banner: {e}")

def goto_and_handle_cookies(page, url, wait_until="domcontentloaded", sleep_after=0):
    page.goto(url, wait_until=wait_until)
    if sleep_after:
        time.sleep(sleep_after)
    handle_cookie_banner(page)

def wait_and_handle_cookies(page, state="domcontentloaded", sleep_after=0):
    page.wait_for_load_state(state)
    if sleep_after:
        time.sleep(sleep_after)
    handle_cookie_banner(page)

def get_datenvolumen(page):
    """Portal-Update 2026: Statt fragiler nth-child-Selektoren wird das
    Inland-Datenvolumen-Meter über sein Footer-Label gesucht. Gibt (GB, meter)
    zurück; meter ist das one-usage-meter-Element (für den Nachbuch-Button)."""
    logging.info("Lese Datenvolumen aus ...")
    page.wait_for_selector("one-usage-meter", timeout=15000)
    for meter in page.query_selector_all("one-usage-meter"):
        try:
            footer = meter.query_selector('one-button[slot="footer"]')
            label = (footer.text_content() or "").strip() if footer else ""
            if "Roaming" in label or not label.startswith("Inland"):
                continue
            heading = meter.query_selector("one-heading")
            heading_text = (heading.text_content() or "").strip() if heading else ""
            match = re.search(r"([\d\.,]+)\s?(GB|MB)", heading_text)
            if not match:
                continue
            value, unit = match.groups()
            value = float(value.replace(",", "."))
            GB = value / 1024.0 if unit == "MB" else value
            logging.info(f"Inland-Meter gefunden (Label '{label}'): {heading_text}")
            return GB, meter
        except Exception as e:
            logging.warning(f"Usage-Meter nicht lesbar: {e}")

    raise Exception("Konnte das Datenvolumen nicht auslesen – kein gültiger Selector gefunden.")

def login_and_check_data():
    global LAST_GB
    browser = None
    with sync_playwright() as p:
        for attempt in range(3):  # bis zu 3 Versuche
            try:
                logging.info(f"Starte Browser {BROWSER} ...")
                LAUNCH_ARGS = get_launch_args(BROWSER)

                if BROWSER == "firefox":
                    browser = p.firefox.launch(headless=HEADLESS, args=LAUNCH_ARGS)
                elif BROWSER == "webkit":
                    browser = p.webkit.launch(headless=HEADLESS, args=LAUNCH_ARGS)
                else:
                    browser = p.chromium.launch(headless=HEADLESS, args=LAUNCH_ARGS)

                # Kontext mit/ohne gespeicherte Cookies
                if os.path.exists(COOKIE_FILE):
                    logging.info("Lade gespeicherte Cookies ...")
                    context = browser.new_context(user_agent=USER_AGENT, storage_state=COOKIE_FILE)
                else:
                    logging.info("Keine Cookies vorhanden – neuer Kontext.")
                    context = browser.new_context(user_agent=USER_AGENT)

                page = context.new_page()

                def login_erfolgreich(p):
                    try:
                        p.wait_for_selector('one-heading[level="h1"]', timeout=8000)
                        heading = p.text_content('one-heading[level="h1"]')
                        return heading and "Übersicht" in heading
                    except Exception:
                        return False

                # Direkt Dashboard aufrufen – ggf. redirect zum Login
                goto_and_handle_cookies(page, DASHBOARD_URL, sleep_after=3)

                if "login" in page.url.lower():
                    logging.info("Nicht eingeloggt – führe Login durch ...")
                    goto_and_handle_cookies(page, LOGIN_URL)
                    logging.info("Fülle Login-Daten aus ...")

                    # Selektoren ggf. anpassen, falls sich IDs ändern
                    page.fill('#input-5', RUFNUMMER or "")
                    page.fill('#input-6', PASSWORT or "")

                    # Portal-Update 2026: Der Login-Button hat keine stabile
                    # Klasse mehr. Enter im Passwortfeld submittet das Formular
                    # zuverlässig; der alte Klassen-Selektor bleibt als Fallback.
                    submitted = False
                    try:
                        logging.info("Sende Login per Enter im Passwortfeld ...")
                        page.press('#input-6', 'Enter')
                        submitted = True
                    except Exception as e:
                        logging.warning(f"Enter-Submit fehlgeschlagen: {e}")
                    if not submitted and not wait_and_click(page, '[class="button button--solid button--medium button--color-default button--has-label"]'):
                        raise Exception("Login-Button konnte nicht geklickt werden.")

                    logging.info("Warte auf Login ...")
                    time.sleep(8)

                    if login_erfolgreich(page):
                        logging.info("Login erfolgreich – Cookies speichern.")
                        context.storage_state(path=COOKIE_FILE)
                    else:
                        raise Exception("Login fehlgeschlagen – Übersichtsseite nicht sichtbar.")
                else:
                    logging.info("Bereits eingeloggt (per Cookies).")

                # Fallback, falls Session doch kaputt ist
                if not login_erfolgreich(page):
                    logging.warning("Session abgelaufen – versuche erneuten Login.")
                    if os.path.exists(COOKIE_FILE):
                        os.remove(COOKIE_FILE)
                        logging.info("Alte Cookies gelöscht.")
                    browser.close()
                    time.sleep(3)
                    return login_and_check_data()  # Neustart

                # Aktivität simulieren & Cookies erneuern
                try:
                    page.hover('one-heading[level="h1"]')
                except Exception:
                    pass
                context.storage_state(path=COOKIE_FILE)

                # Datenvolumen lesen
                GB, data_meter = get_datenvolumen(page)
                LAST_GB = GB
                try:
                    with open(STATE_FILE, "w") as f:
                        json.dump({"last_gb": LAST_GB}, f)
                except Exception as e:
                    logging.warning(f"Fehler beim Speichern des GB-Werts: {e}")

                interval = get_interval()

                # Nachbuchen, wenn < 1 GB
                if GB < 1.0:
                    logging.info("Weniger als 1 GB – versuche, 1 GB nachzubuchen ...")
                    clicked = False
                    # Action-Button direkt im gefundenen Inland-Meter
                    try:
                        button = data_meter.query_selector('one-button[slot="action"]')
                        if button and button.is_visible() and "1 GB" in (button.text_content() or ""):
                            button.click()
                            logging.info("Nachbuchung über Inland-Meter-Button.")
                            send_telegram_message(f"{RUFNUMMER}: {GB:.2f} GB übrig – 1 GB nachgebucht. 📲")
                            clicked = True
                    except Exception as e:
                        logging.warning(f"Fehler beim Klicken: {e}")

                    # Fallback – alle Buttons durchsuchen
                    if not clicked:
                        try:
                            all_buttons = page.query_selector_all("one-button")
                            for btn in all_buttons:
                                try:
                                    if not btn or not btn.is_visible():
                                        continue
                                    text = (btn.text_content() or "").strip()
                                    if "1 GB" in text:
                                        btn.click()
                                        logging.info("Nachbuchung per Fallback erfolgt.")
                                        send_telegram_message(f"{RUFNUMMER}: {GB:.2f} GB übrig – 1 GB per Fallback nachgebucht. 📲")
                                        clicked = True
                                        break
                                except Exception:
                                    continue
                        except Exception as fallback_error:
                            logging.warning(f"Fallback-Suche Fehler: {fallback_error}")

                    if not clicked:
                        raise Exception("Kein gültiger '1 GB' Button gefunden – Nachbuchung fehlgeschlagen.")
                else:
                    logging.info(f"Aktuelles Datenvolumen: {GB:.2f} GB")
                    send_telegram_message(f"{RUFNUMMER}: Noch {GB:.2f} GB übrig. Nächster Run in {interval} s. ✅")

                # Erfolg → Intervall zurückgeben
                return interval

            except Exception as e:
                logging.error(f"Fehler im Versuch {attempt+1}: {e}")
                send_telegram_message(f"{RUFNUMMER}: ❌ Fehler beim Abrufen/Nachbuchen: {e}")
            finally:
                try:
                    if browser:
                        browser.close()
                        logging.info("Browser geschlossen.")
                except Exception:
                    pass
                time.sleep(2)

        logging.error("Skript hat nach 3 Versuchen aufgegeben.")
        return get_interval()

def get_smart_interval():
    if LAST_GB >= 10:
        return random.randint(3600, 5400)
    elif LAST_GB >= 5:
        return random.randint(900, 1800)
    elif LAST_GB >= 3:
        return random.randint(600, 900)
    elif LAST_GB >= 2:
        return random.randint(300, 450)
    elif LAST_GB >= 1.2:
        return random.randint(150, 240)
    elif LAST_GB >= 1.0:
        return random.randint(60, 90)
    else:
        return 60  # Fallback wenn sehr wenig

def get_interval():
    mode = (SLEEP_MODE or "random").lower()
    if mode == "smart":
        return get_smart_interval()
    elif mode == "fixed":
        try:
            return int(SLEEP_INTERVAL)
        except ValueError:
            return 90
    elif mode.startswith("random_"):
        try:
            _, range_str = mode.split("_", 1)
            min_val, max_val = map(int, range_str.split("-"))
            if min_val >= max_val:
                raise ValueError("Min muss kleiner als Max sein")
            return random.randint(min_val, max_val)
        except Exception:
            return random.randint(300, 500)
    else:
        return random.randint(300, 500)

# -----------------------------
# Main-Loop
# -----------------------------
if __name__ == "__main__":
    while True:
        logging.info("Starte neuen Durchlauf...")
        interval = login_and_check_data()
        logging.info(f"💤 Warte {interval} Sekunden...")
        time.sleep(interval if interval is not None else 90)
