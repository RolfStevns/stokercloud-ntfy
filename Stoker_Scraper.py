import os
import time
import logging
from datetime import datetime, timezone
import requests

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s [%(levelname)s] %(message)s")

STOKERCLOUD_LOGIN_URL = os.getenv("STOKERCLOUD_LOGIN_URL", "https://stokercloud.dk/v2/dataout2/login.php")
STOKERCLOUD_ACCEPT_TERMS_URL = os.getenv("STOKERCLOUD_ACCEPT_TERMS_URL", "https://stokercloud.dk/v2/dataout2/acceptterms.php")
STOKERCLOUD_CONTROLLERDATA_URL = os.getenv("STOKERCLOUD_CONTROLLERDATA_URL", "https://stokercloud.dk/v2/dataout2/controllerdata2.php")
STOKERCLOUD_USER = os.environ["STOKERCLOUD_USER"]
STOKERCLOUD_PASSWORD = os.environ["STOKERCLOUD_PASSWORD"]
DEFAULT_SCREEN_PARAM = \
    ("b1,3,b2,5,b3,4,b4,6,b5,12,b6,14,b7,15,b8,16,b9,9,b10,0,"
    "d1,3,d2,4,d3,0,d4,0,d5,0,d6,0,d7,0,d8,0,d9,0,d10,0,"
    "h1,2,h2,3,h3,4,h4,7,h5,8,h6,0,h7,0,h8,0,h9,0,h10,0,"
    "w1,2,w2,3,w3,9,w4,0,w5,0"
)
STOKERCLOUD_SCREEN = os.getenv("STOKERCLOUD_SCREEN", DEFAULT_SCREEN_PARAM)
LOW_THRESHOLD_KG = float(os.getenv("LOW_THRESHOLD_KG", "140"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))
MAX_CAPACITY_KG = os.getenv("MAX_CAPACITY_KG")
NTFY_SERVER = os.getenv("NTFY_SERVER")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]
NTFY_TITLE = os.getenv("NTFY_TITLE", "Stoker hopper low")
NTFY_PRIORITY = os.getenv("NTFY_PRIORITY", "4")  # 1–5
MIN_ALERT_INTERVAL_MIN = int(os.getenv("MIN_ALERT_INTERVAL_MIN", "2"))


def login_and_get_token(session: requests.Session) -> str:
    """
    Log in and return a token.
    Browser sends: POST login.php?user=...&password=...
    """
    logging.info("Logging in to StokerCloud as %s", STOKERCLOUD_USER)
    params = {
        "user": STOKERCLOUD_USER,
        "password": STOKERCLOUD_PASSWORD,
    }
    resp = session.post(STOKERCLOUD_LOGIN_URL, params=params, timeout=10)
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        logging.error("Login did not return JSON, got: %r", resp.text[:200])
        raise
    token = (
        data.get("token")
        or data.get("Token")
        or data.get("TOKEN")
    )
    if not token:
        logging.error("Could not find token in login response: %r", data)
        raise RuntimeError("Token not found in login response")
    logging.info("Got token from login")
    return token


def accept_terms(session: requests.Session, token: str) -> None:
    """
    Accept terms for the token. Safe to call repeatedly.
    """
    logging.info("Accepting terms for token")
    params = {"token": token}
    resp = session.get(STOKERCLOUD_ACCEPT_TERMS_URL, params=params, timeout=10)
    resp.raise_for_status()
    logging.debug("acceptterms response: %r", resp.text[:200])


def get_hopper_kg(session: requests.Session, token: str) -> float:
    """
    Call controllerdata2.php and return hopper mass in kg.

    Primary source: frontdata item with id == "hoppercontent"
    Fallback: hopperdata item with id == "3" and unit == "LNG_KG"
    """
    params = {
        "screen": STOKERCLOUD_SCREEN,
        "token": token,
    }
    resp = session.get(STOKERCLOUD_CONTROLLERDATA_URL, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    logging.debug("controllerdata top-level keys: %s", list(data.keys()))
    hopper_kg = None
    frontdata = data.get("frontdata", [])
    if isinstance(frontdata, list):
        for item in frontdata:
            if item.get("id") == "hoppercontent":
                raw_val = str(item.get("value"))
                hopper_kg = float(raw_val.replace(",", "."))
                logging.info(
                    "Hopper (frontdata.hoppercontent): %.1f kg (raw=%r)",
                    hopper_kg,
                    raw_val,
                )
                break
    if hopper_kg is None:
        hopperdata = data.get("hopperdata", [])
        if isinstance(hopperdata, list):
            for item in hopperdata:
                if (
                    item.get("id") == "3"
                    and item.get("unit") == "LNG_KG"
                ):
                    raw_val = str(item.get("value"))
                    hopper_kg = float(raw_val.replace(",", "."))
                    logging.info(
                        "Hopper (hopperdata id=3): %.1f kg (raw=%r)",
                        hopper_kg,
                        raw_val,
                    )
                    break
    if hopper_kg is None:
        raise RuntimeError(
            "Could not find hopper value in frontdata/hopperdata. "
            f"frontdata={frontdata!r}, hopperdata={data.get('hopperdata')!r}"
        )
    return hopper_kg

def send_ntfy_alert(hopper_kg: float, percent: float | None):
    url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
    if percent is not None:
        message = (
            f"Hopper low: {hopper_kg:.1f} kg remaining "
            f"({percent:.1f}% of capacity). Threshold: {LOW_THRESHOLD_KG:.1f} kg."
        )
    else:
        message = (
            f"Hopper low: {hopper_kg:.1f} kg remaining. "
            f"Threshold: {LOW_THRESHOLD_KG:.1f} kg."
        )
    headers = {
        "Title": NTFY_TITLE,
        "Priority": NTFY_PRIORITY,
        "Tags": "warning,fire",
    }
    logging.info("Sending ntfy alert to %s", url)
    try:
        resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        resp.raise_for_status()
        logging.info("ntfy alert sent successfully")
    except Exception as e:
        logging.error("Failed to send ntfy alert: %s", e)


def safe_get_hopper(session: requests.Session, token: str) -> tuple[float, str]:
    """
    Try to fetch hopper data using the current token.
    If it fails, automatically:
      - re-login
      - accept terms
      - retry once
    Returns: (hopper_kg, token_used_or_renewed)
    """
    try:
        hopper_kg = get_hopper_kg(session, token)
        return hopper_kg, token
    except Exception as e:
        logging.warning("Token might be expired or request failed: %s", e)
        logging.info("Attempting re-login...")
        try:
            new_token = login_and_get_token(session)
            accept_terms(session, new_token)
            logging.info("New token obtained, retrying data fetch...")
            hopper_kg = get_hopper_kg(session, new_token)
            return hopper_kg, new_token
        except Exception as e2:
            logging.error("Token renewal failed: %s", e2)
            raise


def main():
    last_alert_time: datetime | None = None
    max_capacity_kg_val: float | None = float(MAX_CAPACITY_KG) if MAX_CAPACITY_KG else None
    session = requests.Session()
    token = login_and_get_token(session)
    accept_terms(session, token)
    while True:
        try:
            hopper_kg, token = safe_get_hopper(session, token)
            percent = None
            if max_capacity_kg_val and max_capacity_kg_val > 0:
                percent = hopper_kg / max_capacity_kg_val * 100.0
            if hopper_kg <= LOW_THRESHOLD_KG:
                should_send = (
                    last_alert_time is None
                    or (datetime.now(timezone.utc) - last_alert_time).total_seconds()
                    >= MIN_ALERT_INTERVAL_MIN * 60
                )
                if should_send:
                    send_ntfy_alert(hopper_kg, percent)
                    last_alert_time = datetime.now(timezone.utc)
                else:
                    logging.info("Hopper low but last alert was recent; skipping alert.")
            else:
                if percent is not None:
                    logging.info(
                        "Hopper OK: %.1f kg (%.1f%%), threshold %.1f kg",
                        hopper_kg, percent, LOW_THRESHOLD_KG
                    )
                else:
                    logging.info(
                        "Hopper OK: %.1f kg, threshold %.1f kg",
                        hopper_kg, LOW_THRESHOLD_KG
                    )
        except Exception as e:
            logging.error("Final failure this cycle: %s", e)
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
