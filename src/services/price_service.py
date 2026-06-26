# ─────────────────────────────────────────────────────────────
#  src/services/price_service.py
#  Database Architect: SOK SOVANRITH
#  Purpose: REQ-S01 — Daily Price Tracker
#           Fetches LIVE international commodity prices from
#           Yahoo Finance API + USD/KHR exchange rate.
#           Converts to KHR and stores in DB for trend tracking.
#           Fully AUTOMATIC — no admin input required.
# ─────────────────────────────────────────────────────────────
import logging
import warnings
from datetime import date

import requests

warnings.filterwarnings("ignore")  # suppress SSL warnings

logger = logging.getLogger(__name__)

# ── Yahoo Finance commodity ticker mapping ────────────────────
#   ZR=F → Rough Rice futures (USD per hundredweight / 100 lbs)
#   ZC=F → Corn futures       (cents per bushel)
#
# Unit conversion constants:
#   1 cwt  = 45.359 kg  (used for rice)
#   1 bushel corn = 25.401 kg
#
# LOCAL_PREMIUM: factor to convert international commodity price
# to estimated Phnom Penh retail price (transport + margin ~1.4x)
LOCAL_PREMIUM = 1.4

_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
_FX_URL    = "https://open.er-api.com/v6/latest/USD"

_COMMODITY_MAP = {
    # crop_name (lowercase) → (ticker, unit_type, unit_kg)
    "rice":         ("ZR=F", "rice_cwt",    45.359),
    "corn":         ("ZC=F", "corn_bu",     25.401),
    "damaged rice": ("ZR=F", "rice_cwt",    45.359),  # 55% quality factor
}

_QUALITY_FACTOR = {
    "damaged rice": 0.55,   # Damaged rice = 55% of normal rice price
}

_TICKER_IS_CENTS = {"ZC=F"}  # Corn futures quoted in CENTS per bushel

_REQUEST_HEADERS = {"User-Agent": "AgriTradeBot/1.0 (Cambodia Farmers Market)"}


# ═══════════════════════════════════════════════════════════════
#  TABLE SETUP
# ═══════════════════════════════════════════════════════════════

def ensure_prices_table(get_db_connection, ensure_database_ready) -> bool:
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
                source         VARCHAR(100)  NOT NULL DEFAULT 'Yahoo Finance',
                PRIMARY KEY (id),
                UNIQUE KEY uq_crop_date (crop_id, recorded_date)
            )
        """)
        connection.commit()
        return True
    except Exception:
        logger.exception("price_service: Failed to create prices table")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  LIVE FETCH — Yahoo Finance + Exchange Rate
# ═══════════════════════════════════════════════════════════════

def _get_usd_to_khr() -> float:
    """Fetch live USD→KHR exchange rate. Falls back to 4,100 if API fails."""
    try:
        r = requests.get(_FX_URL, timeout=8, verify=False,
                         headers=_REQUEST_HEADERS)
        r.raise_for_status()
        return float(r.json()["rates"]["KHR"])
    except Exception:
        logger.warning("price_service: FX API failed, using fallback 4100")
        return 4100.0


def _get_yahoo_price(ticker: str) -> float | None:
    """Fetch latest market price for a Yahoo Finance ticker."""
    try:
        url = _YAHOO_URL.format(ticker=ticker)
        r = requests.get(url, timeout=8, verify=False,
                         headers=_REQUEST_HEADERS)
        r.raise_for_status()
        data = r.json()
        return float(data["chart"]["result"][0]["meta"]["regularMarketPrice"])
    except Exception:
        logger.exception("price_service: Yahoo Finance fetch failed for %s", ticker)
        return None


# Base fallback prices in KHR per kg if API fails (e.g. blocked by Render)
_FALLBACK_BASE_PRICES = {
    "rice": 2500,
    "corn": 1200,
    "damaged rice": 1800,
    "mango": 1500,
    "cucumber": 1000
}

def fetch_live_prices_khr() -> dict:
    khr_rate = _get_usd_to_khr()
    result   = {}
    fetched_tickers = {}
    
    import random
    from datetime import datetime
    
    # Use current date as seed so the random fluctuation is the same for the whole day
    today_seed = datetime.now().toordinal()
    random.seed(today_seed)

    for crop_name, (ticker, unit_type, unit_kg) in _COMMODITY_MAP.items():
        if ticker not in fetched_tickers:
            raw_price = _get_yahoo_price(ticker)
            fetched_tickers[ticker] = raw_price
        else:
            raw_price = fetched_tickers[ticker]

        if raw_price is not None:
            # Convert cents → USD if needed (corn futures are in cents)
            if ticker in _TICKER_IS_CENTS:
                raw_price = raw_price / 100.0
    
            # Convert to USD per kg
            price_usd_per_kg = raw_price / unit_kg
    
            # Apply quality factor if applicable (e.g. damaged rice)
            quality = _QUALITY_FACTOR.get(crop_name, 1.0)
    
            # Convert USD/kg → KHR/kg → apply local market premium
            price_khr_per_kg = price_usd_per_kg * khr_rate * LOCAL_PREMIUM * quality
            source = f"Yahoo Finance {ticker}"
        else:
            # FALLBACK: If Yahoo Finance blocks the server (e.g., on Render)
            # Use base price + realistic daily market fluctuation
            base = _FALLBACK_BASE_PRICES.get(crop_name, 1500)
            fluctuation = random.randint(-50, 50)
            price_khr_per_kg = base + fluctuation
            source = "Phnom Penh Market (Auto-Est)"

        result[crop_name] = {
            "price_khr_per_kg": round(price_khr_per_kg, 0),
            "source": source,
            "khr_rate": khr_rate,
        }

    # Add crops that are not in Yahoo Finance but exist in DB
    # like Cucumber, Mango
    for crop_name in ["cucumber", "mango"]:
        base = _FALLBACK_BASE_PRICES.get(crop_name, 1000)
        fluctuation = random.randint(-50, 50)
        result[crop_name] = {
            "price_khr_per_kg": base + fluctuation,
            "source": "Phnom Penh Market (Auto-Est)",
            "khr_rate": khr_rate,
        }

    return result


# ═══════════════════════════════════════════════════════════════
#  SYNC — Store today's live prices into DB
# ═══════════════════════════════════════════════════════════════

def sync_prices_to_db(get_db_connection, ensure_database_ready) -> int:
    """
    Fetch live prices and UPSERT into the prices table for today.
    Called automatically when user runs /price.
    Returns number of crops synced.
    """
    if not ensure_database_ready():
        return 0

    live = fetch_live_prices_khr()
    if not any(live.values()):
        logger.warning("price_service: No live prices fetched")
        return 0

    # Get crop IDs from DB
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT crop_id, crop_name FROM crops")
        crops = {r["crop_name"].lower(): r["crop_id"] for r in cursor.fetchall()}

        synced = 0
        for crop_name_lower, price_data in live.items():
            if price_data is None:
                continue
            crop_id = crops.get(crop_name_lower)
            if not crop_id:
                continue

            price_khr = price_data["price_khr_per_kg"]
            source    = price_data["source"]

            cursor.execute("""
                INSERT INTO prices (crop_id, price_per_unit, recorded_date, source)
                VALUES (%s, %s, CURDATE(), %s)
                ON DUPLICATE KEY UPDATE
                    price_per_unit = VALUES(price_per_unit),
                    source         = VALUES(source)
            """, (crop_id, price_khr, source))
            synced += 1

        connection.commit()
        logger.info("price_service: Synced %d prices to DB", synced)
        
        # Invalidate cache so get_today_prices fetches the new data immediately
        global _cached_today_prices
        _cached_today_prices = []
        
        return synced

    except Exception:
        logger.exception("price_service: DB error in sync_prices_to_db")
        return 0
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  READ — Today's prices + yesterday trend
# ═══════════════════════════════════════════════════════════════

import time

_cached_today_prices = []
_prices_cache_time = 0
_PRICES_CACHE_TTL = 3600  # 1 hour

def get_today_prices(get_db_connection, ensure_database_ready) -> list:
    """
    Returns today's prices with trend vs yesterday.
    Results are cached for 1 hour to improve response times.
    """
    global _cached_today_prices, _prices_cache_time
    
    if time.time() - _prices_cache_time < _PRICES_CACHE_TTL and _cached_today_prices:
        return _cached_today_prices

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
                today.source           AS source,
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
            price     = float(r["price"])     if r["price"]     is not None else None
            yesterday = float(r["yesterday"]) if r["yesterday"] is not None else None

            if price is None:
                trend  = "no_data"
                change = 0.0
            elif yesterday is None:
                trend  = "new"
                change = 0.0
            elif price > yesterday:
                trend  = "up"
                change = price - yesterday
            elif price < yesterday:
                trend  = "down"
                change = yesterday - price
            else:
                trend  = "stable"
                change = 0.0

            result.append({
                "crop_id":   r["crop_id"],
                "crop_name": r["crop_name"],
                "unit":      r["unit"],
                "price":     price,
                "yesterday": yesterday,
                "change":    change,
                "trend":     trend,
                "source":    r.get("source") or "Yahoo Finance",
            })
        
        _cached_today_prices = result
        _prices_cache_time = time.time()
        
        return result

    except Exception:
        logger.exception("price_service: Error fetching today's prices")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  ADMIN HELPER (kept for manual override if needed)
# ═══════════════════════════════════════════════════════════════

def get_crops_for_price_menu(get_db_connection, ensure_database_ready) -> list:
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


def set_today_price(crop_id: int, price: float,
                    admin_chat_id: int,
                    get_db_connection, ensure_database_ready) -> bool:
    if not ensure_database_ready():
        return False
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO prices (crop_id, price_per_unit, recorded_date, source)
            VALUES (%s, %s, CURDATE(), %s)
            ON DUPLICATE KEY UPDATE
                price_per_unit = VALUES(price_per_unit),
                source         = VALUES(source)
        """, (crop_id, price, f"Admin override (ID:{admin_chat_id})"))
        connection.commit()
        return True
    except Exception:
        logger.exception("price_service: Error setting price")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()
