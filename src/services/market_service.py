# ─────────────────────────────────────────────────────────────
#  src/services/market_service.py
#  Purpose: REQ-S05 — B-Grade Retail Market
# ─────────────────────────────────────────────────────────────
import logging

logger = logging.getLogger(__name__)

def ensure_listings_table(get_db_connection, ensure_database_ready) -> bool:
    if not ensure_database_ready():
        return False
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id             BIGINT       NOT NULL AUTO_INCREMENT,
                seller_chat_id BIGINT       NOT NULL,
                crop_name      VARCHAR(100) NOT NULL,
                grade          VARCHAR(50)  NOT NULL DEFAULT 'B-Grade',
                quantity       VARCHAR(100) NOT NULL,
                price          VARCHAR(100) NOT NULL,
                created_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            )
        """)
        connection.commit()
        return True
    except Exception:
        logger.exception("market_service: Failed to create listings table")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()

def add_listing(seller_chat_id: int, crop_name: str, grade: str, quantity: str, price: str,
                get_db_connection, ensure_database_ready) -> bool:
    if not ensure_database_ready():
        return False
    ensure_listings_table(get_db_connection, ensure_database_ready)

    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO listings (seller_chat_id, crop_name, grade, quantity, price)
            VALUES (%s, %s, %s, %s, %s)
        """, (seller_chat_id, crop_name, grade, quantity, price))
        connection.commit()
        return True
    except Exception:
        logger.exception("market_service: Failed to add listing")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()

def get_recent_listings(get_db_connection, ensure_database_ready, limit: int = 10) -> list:
    if not ensure_database_ready():
        return []
    ensure_listings_table(get_db_connection, ensure_database_ready)

    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT l.id, l.crop_name, l.grade, l.quantity, l.price, u.name as seller_name, u.phone, u.tg_username, u.latitude, u.longitude
            FROM listings l
            LEFT JOIN users u ON l.seller_chat_id = u.chat_id
            ORDER BY l.created_at DESC
            LIMIT %s
        """, (limit,))
        return cursor.fetchall()
    except Exception:
        logger.exception("market_service: Failed to fetch listings")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()
