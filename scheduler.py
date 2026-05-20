import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from database import Envio, Configuracao, engine
from whatsapp import verificar_conexao, enviar_mensagem, montar_mensagem
from sqlmodel import Session

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


def executar_envio(store_id: str, envio_id: int) -> None:
    with Session(engine) as session:
        envio = session.get(Envio, envio_id)
        if not envio:
            logger.error("Envio %s não encontrado", envio_id)
            return

        if envio.status != "pendente":
            logger.info("Envio %s já processado (status=%s), ignorando", envio_id, envio.status)
            return

        config = session.get(Configuracao, store_id)

        if not config or not config.ativo:
            logger.info("Loja %s inativa ou sem config, cancelando envio %s", store_id, envio_id)
            envio.status = "erro"
            envio.erro_msg = "Loja inativa ou sem configuração no momento do envio"
            session.add(envio)
            session.commit()
            return

        instance = config.evolution_instance or store_id

        if not verificar_conexao(instance):
            logger.info("WhatsApp desconectado para loja %s, envio %s", store_id, envio_id)
            envio.status = "sem_conexao"
            envio.erro_msg = "WhatsApp não conectado no momento do envio"
            session.add(envio)
            session.commit()
            return

        nome = envio.cliente_nome or "cliente"
        cupom = config.cupom or "VOLTA15"
        desconto = config.desconto_pct or 15

        mensagem = montar_mensagem(config.mensagem_template, nome, cupom, desconto)

        sucesso, resposta = enviar_mensagem(instance, envio.telefone, mensagem)

        if sucesso:
            envio.status = "enviado"
            envio.enviado_em = datetime.utcnow()
            logger.info("Envio %s concluído com sucesso para %s", envio_id, envio.telefone)
        else:
            envio.status = "erro"
            envio.erro_msg = resposta[:500]
            logger.warning("Envio %s falhou: %s", envio_id, resposta)

        session.add(envio)
        session.commit()


def agendar_envio(store_id: str, envio_id: int, segundos: int) -> None:
    from datetime import timedelta

    run_at = datetime.utcnow() + timedelta(seconds=segundos)
    scheduler.add_job(
        executar_envio,
        "date",
        run_date=run_at,
        args=[store_id, envio_id],
        id=f"envio_{envio_id}",
        replace_existing=True,
    )
    logger.info("Envio %s agendado para %s", envio_id, run_at.isoformat())
