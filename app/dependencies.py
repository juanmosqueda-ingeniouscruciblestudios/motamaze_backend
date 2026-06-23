from functools import lru_cache

from google.cloud import bigquery, firestore

from app.config import Settings


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_firestore_client() -> firestore.AsyncClient:
    return firestore.AsyncClient()


def get_bq_client() -> bigquery.Client:
    return bigquery.Client()
