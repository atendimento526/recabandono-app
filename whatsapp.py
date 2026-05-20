import requests
import os
import logging

logger = logging.getLogger(__name__)

EVOLUTION_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_KEY = os.getenv("EVOLUTION_API_KEY", "")

HEADERS = {
    "apikey": EVOLUTION_KEY,
    "Content-Type": "application/json"
}

MENSAGEM_PADRAO = """Olá, {nome}! 👋

Você deixou alguns itens no carrinho. Preparamos uma oferta especial para você:

🏷️ Use o cupom *{cupom}* e ganhe *{desconto}% de desconto* na sua compra.

Válido por 24 horas. É só aplicar no checkout! 😉"""


def criar_instancia(store_id):
    """Cria uma instância na Evolution API para a loja."""
    url = f"{EVOLUTION_URL}/instance/create"
    payload = {
        "instanceName": str(store_id),
        "integration": "WHATSAPP-BAILEYS"
    }
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=10)
        return r.status_code in [200, 201], r.json()
    except Exception as e:
        logger.error(f"Erro ao criar instância: {e}")
        return False, {}


def obter_qrcode(store_id):
    """Retorna o QR Code em base64 para conexão."""
    url = f"{EVOLUTION_URL}/instance/connect/{store_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            data = r.json()
            qr = data.get("base64") or data.get("qrcode", {}).get("base64", "")
            return True, qr
        return False, ""
    except Exception as e:
        logger.error(f"Erro ao obter QR Code: {e}")
        return False, ""


def verificar_conexao(store_id):
    """Verifica se o WhatsApp está conectado."""
    url = f"{EVOLUTION_URL}/instance/connectionState/{store_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            state = data.get("instance", {}).get("state", "")
            return state == "open"
        return False
    except Exception as e:
        logger.error(f"Erro ao verificar conexão: {e}")
        return False


def enviar_mensagem(store_id, telefone, mensagem):
    """Envia mensagem de texto via Evolution API."""
    url = f"{EVOLUTION_URL}/message/sendText/{store_id}"
    payload = {
        "number": telefone,
        "text": mensagem
    }
    try:
        r = requests.post(url, json=payload, headers=HEADERS, timeout=15)
        sucesso = r.status_code == 200
        if not sucesso:
            logger.error(f"Erro ao enviar mensagem: {r.status_code} {r.text}")
        return sucesso, r.text
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem: {e}")
        return False, str(e)


def formatar_telefone(telefone_raw):
    """Formata para padrão internacional sem + (ex: 5543999999999)."""
    nums = "".join(filter(str.isdigit, telefone_raw or ""))
    if not nums:
        return None
    if nums.startswith("55") and len(nums) >= 12:
        return nums
    if len(nums) >= 10:
        return f"55{nums}"
    return None


def montar_mensagem(template, nome, cupom, desconto):
    """Substitui variáveis na mensagem."""
    msg = template or MENSAGEM_PADRAO
    return (msg
        .replace("{nome}", nome or "cliente")
        .replace("{cupom}", cupom or "DESCONTO")
        .replace("{desconto}", str(desconto or 15)))
