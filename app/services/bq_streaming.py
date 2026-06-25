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
