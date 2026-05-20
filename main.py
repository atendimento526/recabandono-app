import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Request, Form, Depends, Header
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from database import (
    create_db,
    migrate_db,
    engine,
    get_session,
    get_loja,
    get_configuracao,
    get_ultimos_envios,
    get_stats,
    Loja,
    Configuracao,
    MENSAGEM_PADRAO,
)
from oauth import trocar_codigo_por_token, registrar_webhook
from webhooks import processar_webhook
from scheduler import scheduler
from whatsapp import criar_instancia, obter_qrcode, verificar_conexao

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    migrate_db()
    scheduler.start()
    logger.info("Scheduler iniciado")
    yield
    scheduler.shutdown()
    logger.info("Scheduler encerrado")


app = FastAPI(title="RecAbandono", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=JSONResponse)
async def health():
    return {"status": "ok", "app": "RecAbandono"}


@app.get("/auth/install")
async def auth_install(code: str, user_id: str, session: Session = Depends(get_session)):
    try:
        data = trocar_codigo_por_token(code)
        access_token = data["access_token"]
        store_id = str(data.get("user_id", user_id))

        loja = session.get(Loja, store_id)
        if loja:
            loja.access_token = access_token
        else:
            loja = Loja(store_id=store_id, access_token=access_token)
        session.add(loja)

        config = session.get(Configuracao, store_id)
        if not config:
            config = Configuracao(store_id=store_id)
            session.add(config)

        session.commit()

        try:
            registrar_webhook(store_id, access_token)
        except Exception as exc:
            logger.warning("Falha ao registrar webhook para loja %s: %s", store_id, exc)

        logger.info("Loja %s instalada com sucesso", store_id)
        return RedirectResponse(url=f"/painel/{store_id}", status_code=302)

    except Exception as exc:
        logger.error("Erro na instalação OAuth: %s", exc)
        return RedirectResponse(url=f"/erro?msg={exc}", status_code=302)


@app.get("/painel/{store_id}", response_class=HTMLResponse)
async def painel(request: Request, store_id: str, session: Session = Depends(get_session)):
    loja = get_loja(session, store_id)
    if not loja:
        return RedirectResponse(url="/erro?msg=Loja não encontrada", status_code=302)

    config = get_configuracao(session, store_id)
    if not config:
        config = Configuracao(store_id=store_id)

    envios = get_ultimos_envios(session, store_id)
    stats = get_stats(session, store_id)

    return templates.TemplateResponse(
        "painel.html",
        {
            "request": request,
            "loja": loja,
            "config": config,
            "envios": envios,
            "stats": stats,
            "mensagem_padrao": MENSAGEM_PADRAO,
        },
    )


@app.get("/painel/{store_id}/qrcode")
async def get_qrcode(store_id: str, session: Session = Depends(get_session)):
    loja = get_loja(session, store_id)
    if not loja:
        return JSONResponse({"ok": False, "msg": "Loja não encontrada"}, status_code=404)

    config = session.get(Configuracao, store_id)
    instance = (config.evolution_instance if config else None) or store_id

    if verificar_conexao(instance):
        if config:
            config.evolution_conectado = True
            session.add(config)
            session.commit()
        return JSONResponse({"conectado": True, "qrcode": None})

    ok, _ = criar_instancia(instance)
    if not ok:
        logger.info("Instância %s já existe ou foi recriada", instance)

    ok, qr = obter_qrcode(instance)
    if ok and qr:
        return JSONResponse({"conectado": False, "qrcode": f"data:image/png;base64,{qr}"})

    return JSONResponse({"conectado": False, "qrcode": None})


@app.get("/painel/{store_id}/status")
async def get_status(store_id: str, session: Session = Depends(get_session)):
    loja = get_loja(session, store_id)
    if not loja:
        return JSONResponse({"conectado": False})

    config = session.get(Configuracao, store_id)
    instance = (config.evolution_instance if config else None) or store_id

    conectado = verificar_conexao(instance)

    if config and config.evolution_conectado != conectado:
        config.evolution_conectado = conectado
        session.add(config)
        session.commit()

    return JSONResponse({"conectado": conectado})


@app.post("/painel/{store_id}/config")
async def salvar_config(
    request: Request,
    store_id: str,
    session: Session = Depends(get_session),
    mensagem_template: str = Form(""),
    cupom: str = Form("VOLTA15"),
    desconto_pct: int = Form(15),
    minutos_espera: int = Form(10),
    ativo: str = Form("off"),
):
    loja = get_loja(session, store_id)
    if not loja:
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return JSONResponse({"ok": False, "msg": "Loja não encontrada"}, status_code=404)
        return RedirectResponse(url="/erro?msg=Loja não encontrada", status_code=302)

    config = session.get(Configuracao, store_id)
    if not config:
        config = Configuracao(store_id=store_id)

    config.mensagem_template = mensagem_template.strip() or None
    config.cupom = cupom.strip() or "VOLTA15"
    config.desconto_pct = max(1, min(100, desconto_pct))
    config.minutos_espera = max(1, min(1440, minutos_espera))
    config.ativo = ativo == "on"

    session.add(config)
    session.commit()
    logger.info("Configurações salvas para loja %s", store_id)

    accept = request.headers.get("accept", "")
    if "application/json" in accept:
        return JSONResponse({"ok": True, "msg": "Configurações salvas com sucesso!"})
    return RedirectResponse(url=f"/painel/{store_id}?ok=Configurações salvas!", status_code=302)


@app.post("/webhook/abandoned")
async def webhook_abandoned(
    request: Request,
    session: Session = Depends(get_session),
    x_linkedstore_store_id: str = Header(None, alias="X-Linkedstore-Store-Id"),
):
    store_id = x_linkedstore_store_id
    if not store_id:
        logger.warning("Webhook recebido sem X-Linkedstore-Store-Id")
        return JSONResponse({"ok": False, "erro": "store_id ausente"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        body = {}

    result = processar_webhook(body, store_id, session)
    return JSONResponse(result)


@app.get("/sucesso", response_class=HTMLResponse)
async def sucesso(request: Request):
    store_id = request.query_params.get("store_id", "")
    return templates.TemplateResponse("sucesso.html", {"request": request, "store_id": store_id})


@app.get("/erro", response_class=HTMLResponse)
async def erro(request: Request):
    msg = request.query_params.get("msg", "Erro desconhecido")
    return templates.TemplateResponse("erro.html", {"request": request, "msg": msg})
