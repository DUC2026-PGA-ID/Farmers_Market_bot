# ─────────────────────────────────────────────────────────────
#  src/services/catalog_service.py
#  Database Architect: SOK SOVANRITH
#  Purpose: Service layer for all crop/catalog DB queries.
#           Keeps database logic strictly separated from
#           chat handler logic.
# ─────────────────────────────────────────────────────────────
import logging
import time

logger = logging.getLogger(__name__)

_cached_all_crops = []
_crops_cache_time = 0
_CROPS_CACHE_TTL = 300  # 5 minutes


def get_all_crops(get_db_connection, ensure_database_ready) -> list:
    """
    Fetch all crops from the database ordered by name.
    Returns a list of dicts, or an empty list on any error.

    Exception Handling (Requirement 3):
      - If DB is unreachable → logs the error and returns []
      - Caller (handler) checks for empty list and notifies user
    """
    global _cached_all_crops, _crops_cache_time
    
    if time.time() - _crops_cache_time < _CROPS_CACHE_TTL and _cached_all_crops:
        return _cached_all_crops

    if not ensure_database_ready():
        logger.warning("catalog_service: DB not ready, returning empty crop list.")
        return []

    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT crop_id, crop_name, category, unit FROM crops ORDER BY crop_name"
        )
        rows = cursor.fetchall()
        _cached_all_crops = rows
        _crops_cache_time = time.time()
        return rows
    except Exception:
        logger.exception("catalog_service: DB error in get_all_crops")
        return []
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()


def get_crop_by_id(crop_id: int, get_db_connection, ensure_database_ready) -> dict:
    """Fetch details of a specific crop by ID."""
    if not ensure_database_ready():
        return None
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT crop_id, crop_name, category, unit, description, quality_standards "
            "FROM crops WHERE crop_id = %s",
            (crop_id,)
        )
        rows = cursor.fetchall()
        return rows[0] if rows else None
    except Exception:
        logger.exception("catalog_service: DB error in get_crop_by_id")
        return None
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
