"""
Singleton do cliente Supabase.
Importar `db` em qualquer módulo para acessar o banco.
"""
from supabase import create_client, Client
from backend.config.settings import settings

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


# Atalho para uso direto: from backend.db.client import db
db: Client = None  # inicializado no startup da aplicação


def init_db() -> None:
    """Chame no startup do FastAPI para inicializar o client."""
    global db
    db = get_client()
