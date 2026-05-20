import logging
from datetime import datetime

from sqlmodel import Session, select

from database import Envio, Configuracao, Loja
from whatsapp import formatar_telefone

logger = logging.getLogger(__name__)


def processar_webhook(body: dict, store_id: str, session: Session) -> dict:
    logger.info("Webhook recebido para loja %s, checkout_id=%s", store_id, body.get("id"))

    loja = session.get(Loja, store_id)
    if not loja or not loja.ativo:
        logger.info("Loja %s não encontrada ou inativa, ignorando webhook", store_id)
        return {"ok": True}

    config = session.get(Configuracao, store_id)

    checkout_id = str(body.get("id", ""))
    cliente_nome = body.get("contact_name") or body.get("customer", {}).get("name", "")
    telefone_raw = body.get("contact_phone") or body.get("customer", {}).get("phone", "")

    existente = session.exec(
        select(Envio).where(Envio.store_id == store_id, Envio.checkout_id == checkout_id)
    ).first()
    if existente:
        logger.info("Checkout %s da loja %s já registrado, ignorando", checkout_id, store_id)
        return {"ok": True}

    if not telefone_raw:
        envio = Envio(
            store_id=store_id,
            checkout_id=checkout_id,
            cliente_nome=cliente_nome,
            telefone=None,
            status="sem_telefone",
        )
        session.add(envio)
        session.commit()
        logger.info("Checkout %s sem telefone, registrado como sem_telefone", checkout_id)
        return {"ok": True}

    telefone = formatar_telefone(str(telefone_raw))
    if not telefone:
        envio = Envio(
            store_id=store_id,
            checkout_id=checkout_id,
            cliente_nome=cliente_nome,
            telefone=telefone_raw,
            status="sem_telefone",
        )
        session.add(envio)
        session.commit()
        logger.info("Telefone inválido para checkout %s: %s", checkout_id, telefone_raw)
        return {"ok": True}

    if not config or not config.ativo:
        envio = Envio(
            store_id=store_id,
            checkout_id=checkout_id,
            cliente_nome=cliente_nome,
            telefone=telefone,
            status="sem_configuracao",
        )
        session.add(envio)
        session.commit()
        logger.info("App inativo/sem config para loja %s, checkout %s", store_id, checkout_id)
        return {"ok": True}

    minutos = config.minutos_espera or 10
    agendado_para = datetime.utcnow()

    envio = Envio(
        store_id=store_id,
        checkout_id=checkout_id,
        cliente_nome=cliente_nome,
        telefone=telefone,
        status="pendente",
        agendado_para=agendado_para,
    )
    session.add(envio)
    session.commit()
    session.refresh(envio)

    from scheduler import agendar_envio
    agendar_envio(store_id, envio.id, minutos * 60)

    logger.info(
        "Envio agendado: loja=%s checkout=%s telefone=%s em %dmin",
        store_id, checkout_id, telefone, minutos,
    )
    return {"ok": True}
