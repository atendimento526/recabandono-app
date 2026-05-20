import logging
import os

import requests

logger = logging.getLogger(__name__)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8001")
NUVEMSHOP_APP_ID = os.getenv("NUVEMSHOP_APP_ID", "")
NUVEMSHOP_CLIENT_SECRET = os.getenv("NUVEMSHOP_CLIENT_SECRET", "")


def trocar_codigo_por_token(code: str) -> dict:
    url = f"https://www.nuvemshop.com.br/apps/{NUVEMSHOP_APP_ID}/authorize"
    payload = {
        "client_id": NUVEMSHOP_APP_ID,
        "client_secret": NUVEMSHOP_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def registrar_webhook(store_id: str, access_token: str) -> None:
    url = f"https://api.nuvemshop.com.br/v1/{store_id}/webhooks"
    headers = {
        "Authentication": f"bearer {access_token}",
        "Content-Type": "application/json",
        "User-Agent": "AbandonoApp/1.0",
    }
    payload = {
        "event": "checkout/abandoned",
        "url": f"{APP_BASE_URL}/webhook/abandoned",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 422:
            logger.info("Webhook já registrado para loja %s", store_id)
        else:
            resp.raise_for_status()
            logger.info("Webhook registrado para loja %s", store_id)
    except requests.HTTPError as exc:
        logger.error("Erro ao registrar webhook para loja %s: %s", store_id, exc)
        raise
