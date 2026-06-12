# ─────────────────────────────────────────────────────────────
#  app.py  |  Thin Entry Point
#  Agri-Trade Bot  |  Immortal Digital
#
#  Architecture (Week 9 Refactor):
#    app.py              ← Flask routes, config, DB pool, startup
#    src/handlers/       ← Chat message routing (Telegram only)
#    src/services/       ← Business logic & network integrations
# ─────────────────────────────────────────────────────────────
import hashlib
import logging
import os
import re
import time as _time
from html import escape
from threading import Lock

import telebot
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request

load_dotenv()

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None
    MySQLError = Exception

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────
BOT_TOKEN          = os.getenv("BOT_TOKEN", "")
WEBHOOK_SECRET     = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_URL        = os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL", "")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin123")
DB_HOST            = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST", "")
DB_PORT            = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT", "3306"))
DB_USER            = os.getenv("MYSQL_USER") or os.getenv("DB_USER", "")
DB_PASSWORD        = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD", "")
DB_NAME            = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME", "")

ADMIN_USER_IDS: set = set()
for _raw in os.getenv("ADMIN_USER_IDS", "").split(","):
    _raw = _raw.strip()
    if _raw.isdigit():
        ADMIN_USER_IDS.add(int(_raw))

# ── Phone Regex (Cambodia) ──────────────────────────────────────
PHONE_REGEX = re.compile(r"^(\+855|0)[0-9]{8,9}$")

# ── Telegram webhook secret ──────────────────────────────────────
TELEGRAM_SECRET_TOKEN = (
    hashlib.sha256(WEBHOOK_SECRET.encode("utf-8")).hexdigest()
    if WEBHOOK_SECRET else ""
)

# ── Bot commands ────────────────────────────────────────────────
GLOBAL_BOT_COMMANDS = [
    telebot.types.BotCommand("start",        "ចុះឈ្មោះ / ចាប់ផ្តើម"),
    telebot.types.BotCommand("view_catalog", "មើលកាតាឡុក / View Catalog"),
    telebot.types.BotCommand("price",        "តម្លៃទីផ្សារភ្នំពេញ / Market Prices"),
    telebot.types.BotCommand("market",       "ទីផ្សារលក់រាយ / Retail Market"),
    telebot.types.BotCommand("sell",         "ប្រកាសលក់កសិផល / Sell Crops"),
    telebot.types.BotCommand("buyers",       "បញ្ជីអ្នកទិញ / Verified Buyers"),
    telebot.types.BotCommand("location",     "ផ្ញើទីតាំងចម្ការរបស់អ្នក / My Location"),
    telebot.types.BotCommand("weather",      "អាកាសធាតុ / Live Weather"),
]
ADMIN_BOT_COMMANDS = GLOBAL_BOT_COMMANDS + [
    telebot.types.BotCommand("addbuyer",     "បន្ថែមអ្នកទិញថ្មី"),
    telebot.types.BotCommand("broadcast",    "ផ្សាយសារទៅអ្នកប្រើទាំងអស់"),
    telebot.types.BotCommand("pricealert",   "ប្រកាសតម្លៃទីផ្សារថ្មី"),
    telebot.types.BotCommand("setprice",     "កំណត់តម្លៃផលិតផល"),
    telebot.types.BotCommand("users",        "ស្ថិតិអ្នកប្រើ"),
    telebot.types.BotCommand("recentusers",  "អ្នកប្រើថ្មីៗ"),
]

# ── Flask + Bot ─────────────────────────────────────────────────
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ── Thread locks ────────────────────────────────────────────────
_webhook_lock        = Lock()
_webhook_configured  = False
_commands_lock       = Lock()
_commands_configured = False
_database_lock       = Lock()
_database_ready      = False

# ── User cache (60-second TTL) ──────────────────────────────────
_user_cache: dict = {}
_user_cache_lock  = Lock()
_USER_CACHE_TTL   = 60.0


# ═══════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════

def _mysql_is_configured() -> bool:
    return bool(DB_HOST and DB_USER and DB_PASSWORD and DB_NAME)


_db_pool = None


def _get_db_connection():
    global _db_pool
    if _db_pool is None:
        from mysql.connector.pooling import MySQLConnectionPool
        _db_pool = MySQLConnectionPool(
            pool_name="bot_pool",
            pool_size=5,
            pool_reset_session=True,
            host=DB_HOST, port=DB_PORT,
            user=DB_USER, password=DB_PASSWORD,
            database=DB_NAME, connection_timeout=10,
        )
    return _db_pool.get_connection()


def _ensure_columns(cursor) -> None:
    """Add/rename/drop columns — safe against concurrent gunicorn workers."""

    def col_exists(name: str) -> bool:
        cursor.execute("SHOW COLUMNS FROM users LIKE %s", (name,))
        return len(cursor.fetchall()) > 0

    def safe_exec(sql: str) -> None:
        try:
            cursor.execute(sql)
        except Exception as exc:
            logger.warning("Migration skipped (already done): %s", exc)

    if not col_exists("tg_first_name"):
        safe_exec("ALTER TABLE users ADD COLUMN tg_first_name VARCHAR(255) NULL AFTER chat_id")
    if not col_exists("tg_username"):
        safe_exec("ALTER TABLE users ADD COLUMN tg_username VARCHAR(255) NULL AFTER tg_first_name")
    if not col_exists("name"):
        safe_exec("ALTER TABLE users ADD COLUMN name VARCHAR(255) NULL AFTER tg_username")
    if not col_exists("phone"):
        safe_exec("ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL AFTER name")
    if not col_exists("latitude"):
        safe_exec("ALTER TABLE users ADD COLUMN latitude DECIMAL(10,8) NULL AFTER phone")
    if not col_exists("longitude"):
        safe_exec("ALTER TABLE users ADD COLUMN longitude DECIMAL(11,8) NULL AFTER latitude")
    if not col_exists("state"):
        safe_exec("ALTER TABLE users ADD COLUMN state VARCHAR(20) NOT NULL DEFAULT 'START' AFTER longitude")

    if col_exists("first_name"):
        safe_exec("UPDATE users SET tg_first_name = first_name WHERE tg_first_name IS NULL AND first_name IS NOT NULL")
        safe_exec("ALTER TABLE users DROP COLUMN `first_name`")

    if col_exists("username"):
        safe_exec("UPDATE users SET tg_username = username WHERE tg_username IS NULL AND username IS NOT NULL")
        safe_exec("ALTER TABLE users DROP COLUMN `username`")

    for col in ["gender", "province", "crop_interest", "full_name", "onboarding_completed", "onboarding_step"]:
        if col_exists(col):
            safe_exec(f"ALTER TABLE users DROP COLUMN `{col}`")


def ensure_database_ready() -> bool:
    global _database_ready
    if _database_ready:
        return True
    if not _mysql_is_configured() or mysql is None:
        return False

    with _database_lock:
        if _database_ready:
            return True
        connection = cursor = None
        try:
            connection = _get_db_connection()
            cursor = connection.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id           BIGINT NOT NULL AUTO_INCREMENT,
                    chat_id      BIGINT NOT NULL,
                    tg_first_name VARCHAR(255),
                    tg_username   VARCHAR(255),
                    name          VARCHAR(255),
                    phone         VARCHAR(20),
                    latitude      DECIMAL(10,8),
                    longitude     DECIMAL(11,8),
                    state         VARCHAR(20) NOT NULL DEFAULT 'START',
                    joined_date  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_chat_id (chat_id)
                )
            """)
            _ensure_columns(cursor)
            connection.commit()
            _database_ready = True
            logger.info("MySQL users table is ready.")
            return True
        except Exception as e:
            logger.exception("Unable to init MySQL table.")
            return False
        finally:
            if cursor:     cursor.close()
            if connection: connection.close()


def get_or_create_user(chat_id: int, tg_first_name: str, tg_username: str) -> dict:
    """Return user state dict from cache → DB → default."""
    from src.handlers.message_handler import STATE_START
    with _user_cache_lock:
        cached = _user_cache.get(chat_id)
        if cached and (_time.monotonic() - cached["ts"]) < _USER_CACHE_TTL:
            return dict(cached["state"])

    default = {
        "db_enabled":    False,
        "chat_id":       chat_id,
        "tg_first_name": tg_first_name,
        "tg_username":   tg_username,
        "name":          "",
        "phone":         "",
        "state":         STATE_START,
        "joined_date":   None,
    }

    if not ensure_database_ready():
        return default

    connection = cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT chat_id, tg_first_name, tg_username, name, phone, state, joined_date "
            "FROM users WHERE chat_id = %s",
            (chat_id,),
        )
        rows = cursor.fetchall()
        row = rows[0] if rows else None

        if row is None:
            cursor.execute(
                "INSERT INTO users (chat_id, tg_first_name, tg_username, state) "
                "VALUES (%s, %s, %s, %s)",
                (chat_id, tg_first_name, tg_username or None, STATE_START),
            )
            connection.commit()
            result = {**default, "db_enabled": True}
        else:
            result = {
                "db_enabled":    True,
                "chat_id":       row["chat_id"],
                "tg_first_name": row.get("tg_first_name") or tg_first_name,
                "tg_username":   (row.get("tg_username") or "").strip(),
                "name":          (row.get("name") or "").strip(),
                "phone":         (row.get("phone") or "").strip(),
                "state":         row.get("state") or STATE_START,
                "joined_date":   row.get("joined_date"),
            }
            if (row.get("tg_first_name") != tg_first_name or
                    row.get("tg_username") != tg_username):
                cursor.execute(
                    "UPDATE users SET tg_first_name=%s, tg_username=%s WHERE chat_id=%s",
                    (tg_first_name, tg_username or None, chat_id),
                )
                connection.commit()

        result["is_admin"] = chat_id in ADMIN_USER_IDS

        with _user_cache_lock:
            _user_cache[chat_id] = {"state": dict(result), "ts": _time.monotonic()}
        return result

    except Exception:
        logger.exception("DB error in get_or_create_user")
        return default
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


def update_user_state(chat_id: int, **fields) -> bool:
    """Write allowed fields to DB (UPSERT) and clear cache."""
    allowed = {"name", "phone", "state", "tg_first_name", "tg_username"}
    sanitized = {k: v for k, v in fields.items() if k in allowed}
    if not sanitized or not ensure_database_ready():
        return False

    with _user_cache_lock:
        _user_cache.pop(chat_id, None)

    connection = cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor()
        cols  = list(sanitized.keys())
        vals  = list(sanitized.values())
        col_str = ", ".join(cols)
        ph_str  = ", ".join(["%s"] * len(cols))
        upd_str = ", ".join(f"`{k}` = %s" for k in cols)
        cursor.execute(
            f"INSERT INTO users (chat_id, {col_str}) "
            f"VALUES (%s, {ph_str}) "
            f"ON DUPLICATE KEY UPDATE {upd_str}",
            [chat_id] + vals + vals,
        )
        connection.commit()
        return True
    except Exception:
        logger.exception("DB error in update_user_state")
        return False
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


def get_user_stats() -> dict:
    empty = {"total": 0, "today": 0, "completed": 0, "admins": len(ADMIN_USER_IDS)}
    if not ensure_database_ready():
        return empty
    connection = cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(DATE(joined_date) = CURDATE()) AS today,
                SUM(state = 'IDLE') AS completed
            FROM users
        """)
        rows = cursor.fetchall()
        row = rows[0] if rows else {}
        return {
            "total":     int(row.get("total") or 0),
            "today":     int(row.get("today") or 0),
            "completed": int(row.get("completed") or 0),
            "admins":    len(ADMIN_USER_IDS),
        }
    except Exception:
        logger.exception("DB error in get_user_stats")
        return empty
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


def get_recent_users(limit: int = 20) -> list:
    if not ensure_database_ready():
        return []
    connection = cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT chat_id, tg_first_name, tg_username, name, phone, state, joined_date "
            "FROM users ORDER BY joined_date DESC LIMIT %s",
            (limit,),
        )
        return cursor.fetchall()
    except Exception:
        logger.exception("DB error in get_recent_users")
        return []
    finally:
        if cursor:     cursor.close()
        if connection: connection.close()


# ═══════════════════════════════════════════════════════════════
#  TELEGRAM HELPERS
# ═══════════════════════════════════════════════════════════════

def send_bot_message(chat_id: int, text: str, **kwargs) -> None:
    try:
        bot.send_message(chat_id, text, parse_mode="HTML", **kwargs)
    except Exception:
        logger.exception("Failed to send message to %s", chat_id)


def _format_datetime(dt) -> str:
    if not dt:
        return "—"
    try:
        return dt.strftime("%d %b %Y %H:%M")
    except Exception:
        return str(dt)


# ═══════════════════════════════════════════════════════════════
#  WEBHOOK / COMMAND SETUP
# ═══════════════════════════════════════════════════════════════

def _desired_webhook_url() -> str:
    base = (WEBHOOK_URL or "").rstrip("/")
    return f"{base}/telegram-webhook" if base else ""


def configure_webhook(force: bool = False) -> bool:
    global _webhook_configured
    url = _desired_webhook_url()
    if not url:
        return False
    with _webhook_lock:
        if _webhook_configured and not force:
            return True
        try:
            bot.set_webhook(
                url=url,
                secret_token=TELEGRAM_SECRET_TOKEN or None,
                max_connections=10,
            )
            _webhook_configured = True
            logger.info("Webhook set → %s", url)
            return True
        except Exception:
            logger.exception("Failed to set webhook")
            return False


def configure_bot_commands() -> None:
    global _commands_configured
    with _commands_lock:
        if _commands_configured:
            return
        try:
            bot.delete_my_commands(scope=telebot.types.BotCommandScopeDefault())
            bot.set_my_commands(GLOBAL_BOT_COMMANDS, scope=telebot.types.BotCommandScopeDefault())
            for aid in ADMIN_USER_IDS:
                try:
                    bot.set_my_commands(ADMIN_BOT_COMMANDS, scope=telebot.types.BotCommandScopeChat(aid))
                except Exception:
                    pass
            _commands_configured = True
        except Exception:
            logger.exception("Failed to set bot commands")


# ═══════════════════════════════════════════════════════════════
#  WIRE UP HANDLER (inject dependencies into message_handler)
# ═══════════════════════════════════════════════════════════════

from src.handlers.message_handler import init_handler, handle_text_message  # noqa: E402

init_handler(
    send_fn        = send_bot_message,
    update_fn      = update_user_state,
    get_user_fn    = get_or_create_user,
    db_conn_fn     = _get_db_connection,
    db_ready_fn    = ensure_database_ready,
    admin_ids      = ADMIN_USER_IDS,
    phone_regex    = PHONE_REGEX,
    bot_instance   = bot,
)


# ═══════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════════

def _process_update_async(update: dict) -> None:
    configure_bot_commands()
    message = update.get("message") or update.get("edited_message")
    if message:
        try:
            handle_text_message(
                message,
                get_user_stats_fn    = get_user_stats,
                get_recent_users_fn  = get_recent_users,
                format_datetime_fn   = _format_datetime,
            )
        except Exception:
            logger.exception("Error handling message")


@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    if TELEGRAM_SECRET_TOKEN:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != TELEGRAM_SECRET_TOKEN:
            abort(403)

    try:
        update = request.get_json(force=True, silent=True) or {}
        if update:
            import threading
            threading.Thread(target=_process_update_async, args=(update,)).start()
    except Exception:
        pass

    return jsonify({"ok": True})


@app.route("/setup-webhook")
def setup_webhook_route():
    if WEBHOOK_SECRET and request.args.get("token", "") != WEBHOOK_SECRET:
        abort(403)
    ok  = configure_webhook(force=True)
    url = _desired_webhook_url()
    return jsonify({"ok": ok, "webhook_url": url})


@app.route("/health")
@app.route("/healthz")
def health():
    return jsonify({"status": "ok", "bot": "Agri-Trade Bot"})


@app.route("/dashboard")
def dashboard():
    if WEBHOOK_SECRET and request.args.get("token", "") != WEBHOOK_SECRET:
        abort(403)
    if DASHBOARD_PASSWORD and request.args.get("password", "") != DASHBOARD_PASSWORD:
        abort(403)
    return render_template(
        "dashboard.html",
        stats=get_user_stats(),
        recent_users=get_recent_users(20),
        webhook_url=_desired_webhook_url(),
        format_datetime=_format_datetime,
        ADMIN_USER_IDS=ADMIN_USER_IDS,
        STATE_IDLE="IDLE",
        STATE_START="START",
        STATE_WAIT_NAME="WAIT_NAME",
        STATE_WAIT_PHONE="WAIT_PHONE",
    )


# ═══════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════

ensure_database_ready()
configure_webhook()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
