from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel, create_engine, Session, select

DATABASE_URL = "sqlite:///./abandono.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

MENSAGEM_PADRAO = """Olá, {nome}! 👋

Você deixou alguns itens no carrinho. Preparamos uma oferta especial para você:

🏷️ Use o cupom *{cupom}* e ganhe *{desconto}% de desconto* na sua compra.

Válido por 24 horas. É só aplicar no checkout! 😉"""


class Loja(SQLModel, table=True):
    __tablename__ = "lojas"

    store_id: str = Field(primary_key=True)
    access_token: str
    nome_loja: Optional[str] = None
    email: Optional[str] = None
    ativo: bool = True
    instalado_em: datetime = Field(default_factory=datetime.utcnow)


class Configuracao(SQLModel, table=True):
    __tablename__ = "configuracoes"

    store_id: str = Field(primary_key=True, foreign_key="lojas.store_id")
    evolution_instance: Optional[str] = None
    evolution_conectado: bool = False
    mensagem_template: Optional[str] = None
    cupom: str = "VOLTA15"
    desconto_pct: int = 15
    minutos_espera: int = 10
    ativo: bool = True


class Envio(SQLModel, table=True):
    __tablename__ = "envios"

    id: Optional[int] = Field(default=None, primary_key=True)
    store_id: str = Field(foreign_key="lojas.store_id")
    checkout_id: str
    cliente_nome: Optional[str] = None
    telefone: Optional[str] = None
    status: str = "pendente"
    agendado_para: Optional[datetime] = None
    enviado_em: Optional[datetime] = None
    erro_msg: Optional[str] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)


def create_db():
    SQLModel.metadata.create_all(engine)


def migrate_db():
    """Migrates configuracoes table to Evolution API schema, preserving existing data."""
    import sqlite3
    db_path = DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(configuracoes)")
    cols = {row[1] for row in cur.fetchall()}

    new_cols = [
        ("evolution_instance", "ALTER TABLE configuracoes ADD COLUMN evolution_instance TEXT"),
        ("evolution_conectado", "ALTER TABLE configuracoes ADD COLUMN evolution_conectado BOOLEAN DEFAULT 0"),
        ("mensagem_template", "ALTER TABLE configuracoes ADD COLUMN mensagem_template TEXT"),
    ]

    for col_name, sql in new_cols:
        if col_name not in cols:
            cur.execute(sql)

    conn.commit()
    conn.close()


def get_session():
    with Session(engine) as session:
        yield session


def get_loja(session: Session, store_id: str) -> Optional[Loja]:
    return session.get(Loja, store_id)


def get_configuracao(session: Session, store_id: str) -> Optional[Configuracao]:
    return session.get(Configuracao, store_id)


def get_ultimos_envios(session: Session, store_id: str, limit: int = 10):
    stmt = (
        select(Envio)
        .where(Envio.store_id == store_id)
        .order_by(Envio.criado_em.desc())
        .limit(limit)
    )
    return session.exec(stmt).all()


def get_stats(session: Session, store_id: str) -> dict:
    from sqlalchemy import func

    total = session.exec(
        select(func.count(Envio.id)).where(Envio.store_id == store_id)
    ).one()
    enviados = session.exec(
        select(func.count(Envio.id)).where(
            Envio.store_id == store_id, Envio.status == "enviado"
        )
    ).one()
    taxa = round((enviados / total * 100), 1) if total > 0 else 0.0
    return {"total": total, "enviados": enviados, "taxa": taxa}
