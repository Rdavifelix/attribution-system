"""
Configuração centralizada via variáveis de ambiente.
Usar: from backend.config.settings import settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Supabase
    supabase_url: str
    supabase_service_key: str

    # Google Sheets
    google_service_account_json: str = ""  # JSON inline ou path do arquivo
    sheet_id: str = ""
    sheet_tab: str = "Leads"

    # Meta Ads
    meta_system_user_token: str = ""
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_ad_account_id: str = ""
    meta_api_version: str = "v21.0"
    meta_oauth_redirect_uri: str = "http://localhost:8000/auth/meta/callback"

    # GoHighLevel
    ghl_private_token: str = ""
    ghl_location_id: str = ""
    ghl_funnel_tag: str = ""

    # App
    port: int = 8000
    frontend_url: str = "http://localhost:3000"
    default_funnel_id: int = 1
    webhook_secret: str = ""


settings = Settings()
