# ─────────────────────────────────────────────────────────────
#  src/services/price_service.py
#  Database Architect: SOK SOVANRITH
#  Purpose: Service layer for daily market price queries.
#           Reads/writes the `prices` table.
#           Returns clean data to message_handler — no Telegram logic here.
# ─────────────────────────────────────────────────────────────
import logging
from datetime import date

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  TABLE SETUP
# ═══════════════════════════════════════════════════════════════

def ensure_prices_table(get_db_connection, ensure_database_ready) -> bool:
    """Create the prices table if it does not exist yet."""
    if not ensure_database_ready():
        return False
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id             BIGINT        NOT NULL AUTO_INCREMENT,
                crop_id        BIGINT        NOT NULL,
                price_per_unit DECIMAL(10,2) NOT NULL,
                recorded_date  DATE          NOT NULL DEFAULT (CURDATE()),
                updated_by     BIGINT        NULL,
                PRIMARY KEY (id),
                UNIQUE KEY uq_crop_date (crop_id, recorded_date)
            )
        """)
        connection.commit()
        logger.info("prices table is ready.")
        return True
    except Exception:
        logger.exception("price_service: Failed to create prices table")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  READ — Today's prices + yesterday trend
# ═══════════════════════════════════════════════════════════════

def get_today_prices(get_db_connection, ensure_database_ready) -> list:
    """
    Returns list of dicts with today's price and trend vs yesterday.

    Each dict:
        {
            "crop_id":   1,
            "crop_name": "Rice",
            "unit":      "50kg Sack",
            "price":     25000.00,      # today's price (KHR)
            "yesterday": 24000.00,      # None if no yesterday data
            "change":    1000.00,       # difference (+/-)
            "trend":     "up"           # "up" | "down" | "stable" | "new"
        }
    """
    if not ensure_database_ready():
        return []
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                c.crop_id,
                c.crop_name,
                c.unit,
                today.price_per_unit   AS price,
                yest.price_per_unit    AS yesterday
            FROM crops c
            LEFT JOIN prices today
                ON today.crop_id = c.crop_id
                AND today.recorded_date = CURDATE()
            LEFT JOIN prices yest
                ON yest.crop_id = c.crop_id
                AND yest.recorded_date = DATE_SUB(CURDATE(), INTERVAL 1 DAY)
            ORDER BY c.crop_name
        """)
        rows = cursor.fetchall()
        result = []
        for r in rows:
            price = float(r["price"]) if r["price"] is not None else None
            yesterday = float(r["yesterday"]) if r["yesterday"] is not None else None

            if price is None:
                trend = "no_data"
                change = 0.0
            elif yesterday is None:
                trend = "new"
                change = 0.0
            elif price > yesterday:
                trend = "up"
                change = price - yesterday
            elif price < yesterday:
                trend = "down"
                change = yesterday - price
            else:
                trend = "stable"
                change = 0.0

            result.append({
                "crop_id":   r["crop_id"],
                "crop_name": r["crop_name"],
                "unit":      r["unit"],
                "price":     price,
                "yesterday": yesterday,
                "change":    change,
                "trend":     trend,
            })
        return result
    except Exception:
        logger.exception("price_service: Error fetching today's prices")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  READ — Get all crops (for admin setprice menu)
# ═══════════════════════════════════════════════════════════════

def get_crops_for_price_menu(get_db_connection, ensure_database_ready) -> list:
    """Returns simple list of crops for admin to pick when setting price."""
    if not ensure_database_ready():
        return []
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT crop_id, crop_name, unit FROM crops ORDER BY crop_name")
        return cursor.fetchall()
    except Exception:
        logger.exception("price_service: Error fetching crops for menu")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  WRITE — Admin sets today's price for a crop
# ═══════════════════════════════════════════════════════════════

def set_today_price(crop_id: int, price: float,
                    admin_chat_id: int,
                    get_db_connection, ensure_database_ready) -> bool:
    """
    UPSERT today's price for a given crop.
    If a price already exists for today it is updated.
    Returns True on success, False on failure.
    """
    if not ensure_database_ready():
        return False
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO prices (crop_id, price_per_unit, recorded_date, updated_by)
            VALUES (%s, %s, CURDATE(), %s)
            ON DUPLICATE KEY UPDATE
                price_per_unit = VALUES(price_per_unit),
                updated_by     = VALUES(updated_by)
        """, (crop_id, price, admin_chat_id))
        connection.commit()
        logger.info("Admin %s set price for crop_id=%s → %.2f KHR",
                    admin_chat_id, crop_id, price)
        return True
    except Exception:
        logger.exception("price_service: Error setting price")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()
