# ─────────────────────────────────────────────────────────────
#  src/services/notification_service.py
#  Purpose: REQ-S03 — Push Notifications
# ─────────────────────────────────────────────────────────────
import logging
from src.services.price_service import get_today_prices

logger = logging.getLogger(__name__)

def get_all_user_chat_ids(get_db_connection, ensure_database_ready) -> list:
    if not ensure_database_ready():
        return []
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT chat_id FROM users WHERE chat_id IS NOT NULL")
        return [row["chat_id"] for row in cursor.fetchall()]
    except Exception:
        logger.exception("notification_service: Failed to fetch chat IDs")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()

def generate_price_alert_message(get_db_connection, ensure_database_ready) -> str:
    """Generates a push notification message for price alerts."""
    prices = get_today_prices(get_db_connection, ensure_database_ready)
    if not prices:
        return ""
        
    msg = "🚨 <b>ព័ត៌មានតម្លៃទីផ្សារភ្នំពេញថ្មី!</b>\n<code>━━━━━━━━━━━━━━━━</code>\n"
    
    has_data = False
    for p in prices:
        if p["price"] is None:
            continue
            
        has_data = True
        trend_icon = "➖"
        if p["trend"] == "up":
            trend_icon = "📈"
        elif p["trend"] == "down":
            trend_icon = "📉"
            
        msg += f"{trend_icon} <b>{p['crop_name']}</b>: {int(p['price']):,} ៛/{p['unit']}\n"
        if p["change"] > 0:
            direction = "កើនឡើង" if p["trend"] == "up" else "ធ្លាក់ចុះ"
            msg += f"   <i>({direction} {int(p['change']):,} ៛)</i>\n"
            
    if not has_data:
        return ""
        
    msg += "\n🔎 <i>សូមពិនិត្យមើល /price សម្រាប់ពត៌មានលម្អិត។</i>"
    return msg
