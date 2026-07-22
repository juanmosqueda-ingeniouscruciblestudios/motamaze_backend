import asyncio
import logging

from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

logger = logging.getLogger(__name__)

_client: bigquery.Client | None = None


def _get_bq_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client()
    return _client


async def stream_event(
    table_id: str,
    row: dict,
    project_id: str,
    dataset_id: str = "motamaze_analytics",
    *,
    row_id: str | None = None,
    max_retries: int = 3,
) -> None:
    """
    Async BQ streaming insert. Always call via BackgroundTasks — never in the request path.
    row_id: opaque dedup key — BQ deduplicates within a 1-minute window.
    Errors are logged but never propagated to the client.
    """
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    row_ids = [row_id] if row_id else None

    for attempt in range(1, max_retries + 1):
        try:
            errors = await asyncio.to_thread(
                _get_bq_client().insert_rows_json,
                table_ref,
                [row],
                row_ids=row_ids,
            )
            if not errors:
                return
            logger.error(
                "BQ insert errors [table=%s attempt=%d]: %s",
                table_id, attempt, errors,
            )
        except GoogleAPIError as exc:
            logger.error(
                "BQ API error [table=%s attempt=%d]: %s",
                table_id, attempt, exc,
            )

        if attempt < max_retries:
            await asyncio.sleep(2 ** attempt)  # backoff: 2s, 4s

    logger.error(
        "BQ streaming failed after %d attempts [table=%s]",
        max_retries, table_id,
    )


def _run_dml_sync(
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> int:
    job = _get_bq_client().query(
        query,
        job_config=bigquery.QueryJobConfig(query_parameters=params),
    )
    job.result()  # blocks until the DML job completes
    return job.num_dml_affected_rows or 0


async def run_dml(
    query: str,
    params: list[bigquery.ScalarQueryParameter],
) -> int:
    """Runs a parameterized DML statement (UPDATE/DELETE) and returns the
    affected row count. The BigQuery python client has no native async query
    surface, so this runs in a thread — same pattern as verify_google_token's
    _verify_google_token_sync wrapper in auth_service.py.

    Unlike stream_event (fire-and-forget, errors only logged), DML errors
    propagate — the caller (account_deletion_service.purge_user_bigquery_data)
    needs to know a purge failed so it can mark account_deletions status
    accordingly instead of silently reporting success.
    """
    return await asyncio.to_thread(_run_dml_sync, query, params)


async def stream_events(
    table_id: str,
    rows: list[dict],
    project_id: str,
    dataset_id: str = "motamaze_analytics",
    *,
    row_ids: list[str] | None = None,
    max_retries: int = 3,
) -> None:
    """Batch variant of stream_event. Inserts multiple rows in a single BQ API call."""
    if not rows:
        return
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    for attempt in range(1, max_retries + 1):
        try:
            errors = await asyncio.to_thread(
                _get_bq_client().insert_rows_json,
                table_ref,
                rows,
                row_ids=row_ids,
            )
            if not errors:
                return
            logger.error(
                "BQ batch insert errors [table=%s attempt=%d rows=%d]: %s",
                table_id, attempt, len(rows), errors,
            )
        except GoogleAPIError as exc:
            logger.error(
                "BQ API error [table=%s attempt=%d]: %s",
                table_id, attempt, exc,
            )

        if attempt < max_retries:
            await asyncio.sleep(2 ** attempt)

    logger.error(
        "BQ batch streaming failed after %d attempts [table=%s rows=%d]",
        max_retries, table_id, len(rows),
    )
