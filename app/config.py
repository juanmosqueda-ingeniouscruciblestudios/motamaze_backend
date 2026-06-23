from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gcp_project_id: str
    environment: str = "dev"
    bq_dataset: str = "motamaze_analytics"
    log_level: str = "info"
    jwt_issuer: str = "https://api.motamaze.com"
    jwks_url: str = "https://api.motamaze.com/.well-known/jwks.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
