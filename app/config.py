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
    # T-124 (2026-07-27): motamaze.com was never registered — the game lives
    # under the studio domain. Must stay without a trailing slash: social.py
    # builds URLs as f"{share_base_url}/s/{token}". The /motamaze path segment
    # is part of the base, so App Links/AASA scope to /motamaze/* accordingly.
    share_base_url: str = "https://ingeniouscruciblestudios.com/motamaze"
    play_package_name: str = "com.ingeniouscruciblestudios.motamaze"
    # aud claim on a native iOS identity_token is the app's bundle ID (not a
    # separate "Services ID" — that's only for web-based Sign in with Apple JS).
    apple_bundle_id: str = "com.ingeniouscruciblestudios.motamaze"
    apple_environment: str = "Sandbox"  # "Sandbox" | "Production" (appstoreserverlibrary Environment)
    # Numeric App Store listing ID — required by SignedDataVerifier only when
    # apple_environment="Production". None is fine for Sandbox. Registered
    # 2026-08-12 (T-IOS-3 ST-05); same value across dev/staging/prod, there's
    # only one App Store Connect app registration.
    apple_app_apple_id: int | None = 6800867964
    geoip2_db_path: str = "/gcs/geolite2/GeoLite2-Country.mmdb"
    firebase_project_number: str = "542009654415"
    pubsub_rtdn_sa_email: str = "game-api-backend@motamaze.iam.gserviceaccount.com"
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "noreply@ingeniouscruciblestudios.com"
    parental_consent_base_url: str = "https://motamaze-backend-542009654415.us-central1.run.app"
    # INFRA-007: must match the `--oidc-token-audience` every /jobs/* Cloud
    # Scheduler job was created with (`gcloud scheduler jobs list --format=
    # "table(httpTarget.oidcToken.audience)"` to confirm) — verify_cloud_scheduler_oidc
    # in app/routers/jobs.py rejects any token whose aud claim doesn't match
    # this exactly. Default here is the dev Cloud Run URL; prod overrides via
    # Secret Manager/.env like the rest of this class.
    cloud_run_service_url: str = "https://motamaze-backend-qxc5bjtn4q-uc.a.run.app"
    company_website_url: str = "https://ingeniouscruciblestudios.com/motamaze/"
    privacy_email: str = "privacy@ingeniouscruciblestudios.com"
    # Decision L (2026-07-21): Option A — static tracking link created once in
    # Tenjin's dashboard (organic/referral channel). Empty until Juan/Saul set
    # it up there; falls back to a direct URL (no attribution) when unset —
    # see social.py's _tenjin_share_url().
    tenjin_share_tracking_link: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
