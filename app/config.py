from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gcp_project_id: str
    environment: str = "dev"
    bq_dataset: str = "motamaze_analytics"
    log_level: str = "info"
    jwt_issuer: str = "https://api.motamaze.com"
    jwks_url: str = "https://api.motamaze.com/.well-known/jwks.json"
    google_oauth_client_id: str = ""
    jwt_key_id: str = "motamaze-key-v1"
    jwt_secret_name: str = "jwt-private-key"
    active_season_id: str = "season_001"
    cloudinary_cloud_name: str = "lyku9hz2"
    cloudinary_share_image_id: str = "motamaze_1200x630_v2_yivwuj"
    share_base_url: str = "https://motamaze.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
