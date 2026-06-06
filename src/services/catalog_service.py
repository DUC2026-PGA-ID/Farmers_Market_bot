# ─────────────────────────────────────────────────────────────
#  src/services/catalog_service.py
#  Database Architect: SOK SOVANRITH
#  Purpose: Service layer for all crop/catalog DB queries.
#           Keeps database logic strictly separated from
#           chat handler logic.
# ─────────────────────────────────────────────────────────────
import logging

logger = logging.getLogger(__name__)


def get_all_crops(get_db_connection, ensure_database_ready) -> list:
    """
    Fetch all crops from the database ordered by name.
    Returns a list of dicts, or an empty list on any error.

    Exception Handling (Requirement 3):
      - If DB is unreachable → logs the error and returns []
      - Caller (handler) checks for empty list and notifies user
    """
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
        return cursor.fetchall()
    except Exception:
        logger.exception("catalog_service: DB error in get_all_crops")
        return []
    finally:
        if cursor:
            cursor.close()
        if connection:
            connection.close()
