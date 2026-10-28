from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHORIZO_", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql+psycopg://chorizo:chorizo@localhost:5432/chorizo"

    # Auth
    jwt_secret: str = "change-me"
    jwt_ttl_minutes: int = 60 * 24

    # Web app origin, used for CORS and Stripe redirect URLs
    web_url: str = "http://localhost:3000"

    # Billing (Stripe). Price IDs map a plan to a recurring Stripe price.
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_pro: str = ""
    stripe_price_institutional: str = ""
    stripe_price_sponsor: str = ""

    # Data ingestion
    ctgov_base_url: str = "https://clinicaltrials.gov/api/v2"


@lru_cache
def get_settings() -> Settings:
    return Settings()
