"""
FastAPI application — ponto de entrada do backend.

Inclui:
- CORS configurado para o frontend Next.js
- APScheduler para jobs periódicos (sheets, meta, ghl reconcile)
- Rotas: /health, /ingest/ghl, /api/dashboard/*
"""
from __future__ import annotations
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.config.settings import settings
from backend.db.client import init_db, get_client
from backend.config.depara import load_from_db
from backend.api.routes.health import router as health_router
from backend.api.routes.dashboard import router as dashboard_router
from backend.api.routes.auth_meta import router as meta_auth_router
from backend.ingest.ghl_webhook import router as ghl_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Attribution System API",
    version="2.0.0",
    docs_url="/docs",
)

# ─── CORS ────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rotas ───────────────────────────────────────────────────────────────────
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(meta_auth_router)
app.include_router(ghl_router, prefix="/ingest")

# ─── Scheduler ───────────────────────────────────────────────────────────────
scheduler = AsyncIOScheduler()


def _job_sheets():
    """Job periódico: importa a planilha de Leads."""
    from backend.ingest.sheets_sync import sync_sheet
    from backend.engine.match import run_match
    try:
        stats = sync_sheet()
        logger.info(f"[scheduler] sheets_sync: {stats}")
        match_stats = run_match()
        logger.info(f"[scheduler] match: {match_stats}")
    except Exception as exc:
        logger.error(f"[scheduler] sheets_sync falhou: {exc}", exc_info=True)


def _job_meta():
    """Job diário: sincroniza Meta Ads Insights."""
    from backend.ingest.meta_sync import sync_meta
    try:
        stats = sync_meta()
        logger.info(f"[scheduler] meta_sync: {stats}")
    except Exception as exc:
        logger.error(f"[scheduler] meta_sync falhou: {exc}", exc_info=True)


def _job_ghl_reconcile():
    """Job diário: reconcilia contatos do GHL."""
    from backend.ingest.ghl_reconcile import reconcile_ghl
    try:
        stats = reconcile_ghl()
        logger.info(f"[scheduler] ghl_reconcile: {stats}")
    except Exception as exc:
        logger.error(f"[scheduler] ghl_reconcile falhou: {exc}", exc_info=True)


# ─── Lifecycle ───────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    logger.info("Iniciando Attribution System...")

    # Inicializa cliente do Supabase
    init_db()
    _db = get_client()  # referência local ao client já inicializado

    # Carrega tabela de-para do banco para cache em memória
    try:
        rows = _db.table("depara_status").select("*").execute().data or []
        load_from_db(rows)
        logger.info(f"De-para carregado: {len(rows)} mapeamentos")
    except Exception as exc:
        logger.warning(f"Não foi possível carregar de-para do banco: {exc}")

    # Configura jobs agendados
    # Planilha: a cada 30 minutos
    scheduler.add_job(
        _job_sheets,
        trigger=IntervalTrigger(minutes=30),
        id="sheets_sync",
        replace_existing=True,
        max_instances=1,
    )
    # Meta Ads: diariamente às 06:00 UTC
    scheduler.add_job(
        _job_meta,
        trigger=CronTrigger(hour=6, minute=0),
        id="meta_sync",
        replace_existing=True,
        max_instances=1,
    )
    # GHL reconciliação: diariamente às 03:00 UTC
    scheduler.add_job(
        _job_ghl_reconcile,
        trigger=CronTrigger(hour=3, minute=0),
        id="ghl_reconcile",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info("Scheduler iniciado. Jobs: sheets(30min), meta(06h), ghl(03h)")


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown(wait=False)
    logger.info("Attribution System encerrado.")


# ─── Endpoints de trigger manual (útil para testes e re-ingestão) ────────────
@app.post("/admin/sync-sheets")
async def trigger_sheets():
    """Força a sincronização da planilha imediatamente."""
    from backend.ingest.sheets_sync import sync_sheet
    from backend.engine.match import run_match
    stats = sync_sheet()
    match_stats = run_match()
    return {"sheets": stats, "match": match_stats}


@app.post("/admin/sync-meta")
async def trigger_meta():
    """Força a sincronização do Meta Ads imediatamente."""
    from backend.ingest.meta_sync import sync_meta
    return sync_meta()


@app.post("/admin/sync-ghl")
async def trigger_ghl():
    """Força a reconciliação do GHL imediatamente."""
    from backend.ingest.ghl_reconcile import reconcile_ghl
    return reconcile_ghl()


@app.post("/admin/run-match")
async def trigger_match():
    """Força o motor de cruzamento imediatamente."""
    from backend.engine.match import run_match
    return run_match()
