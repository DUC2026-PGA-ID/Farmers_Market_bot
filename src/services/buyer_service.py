# ─────────────────────────────────────────────────────────────
#  src/services/buyer_service.py
#  Database Architect: SOK SOVANRITH
#  Purpose: REQ-S02 — Verified Buyer Directory
# ─────────────────────────────────────────────────────────────
import logging

logger = logging.getLogger(__name__)

def ensure_buyers_table(get_db_connection, ensure_database_ready) -> bool:
    if not ensure_database_ready():
        return False
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buyers (
                id          BIGINT       NOT NULL AUTO_INCREMENT,
                name        VARCHAR(100) NOT NULL,
                phone       VARCHAR(20)  NOT NULL,
                company     VARCHAR(150),
                is_verified BOOLEAN      DEFAULT TRUE,
                created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            )
        """)
        connection.commit()
        return True
    except Exception:
        logger.exception("buyer_service: Failed to create buyers table")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


def get_all_buyers(get_db_connection, ensure_database_ready) -> list:
    if not ensure_database_ready():
        return []
    
    ensure_buyers_table(get_db_connection, ensure_database_ready)

    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT name, phone, company, is_verified
            FROM buyers
            ORDER BY is_verified DESC, name ASC
        """)
        return cursor.fetchall()
    except Exception:
        logger.exception("buyer_service: Failed to fetch buyers")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


def add_buyer(name: str, phone: str, company: str, get_db_connection, ensure_database_ready) -> bool:
    if not ensure_database_ready():
        return False
        
    ensure_buyers_table(get_db_connection, ensure_database_ready)

    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO buyers (name, phone, company, is_verified)
            VALUES (%s, %s, %s, TRUE)
        """, (name, phone, company))
        connection.commit()
        return True
    except Exception:
        logger.exception("buyer_service: Failed to add buyer")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()
