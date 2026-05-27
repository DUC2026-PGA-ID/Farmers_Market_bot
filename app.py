# ─────────────────────────────────────────────────────────────
#  Agri-Trade Bot  |  State Machine User Registration
#  Immortal Digital
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

# ── State Machine ───────────────────────────────────────────────
STATE_START      = "START"
STATE_WAIT_NAME  = "WAIT_NAME"
STATE_WAIT_PHONE = "WAIT_PHONE"
STATE_IDLE       = "IDLE"

# ── Phone Regex (Cambodia) ──────────────────────────────────────
# Valid: 012345678 | 0965123456 | +85512345678
PHONE_REGEX = re.compile(r"^(\+855|0)[0-9]{8,9}$")

# ── Telegram webhook secret ──────────────────────────────────────
TELEGRAM_SECRET_TOKEN = (
    hashlib.sha256(WEBHOOK_SECRET.encode("utf-8")).hexdigest()
    if WEBHOOK_SECRET else ""
)

# ── Bot commands ────────────────────────────────────────────────
GLOBAL_BOT_COMMANDS = [
    telebot.types.BotCommand("start",  "ចុះឈ្មោះ / ចាប់ផ្តើម"),
    telebot.types.BotCommand("status", "ពិនិត្យស្ថានភាព"),
    telebot.types.BotCommand("help",   "បញ្ជីពាក្យបញ្ជា"),
]
ADMIN_BOT_COMMANDS = GLOBAL_BOT_COMMANDS + [
    telebot.types.BotCommand("users",       "ស្ថិតិអ្នកប្រើ"),
    telebot.types.BotCommand("recentusers", "អ្នកប្រើថ្មីៗ"),
]

UNKNOWN_COMMAND_TEXT = (
    "🤖 <b>មិនទាន់ស្គាល់ពាក្យបញ្ជានេះទេ</b>\n"
    "សូមសាកមួយក្នុងចំណោម:\n"
    "• <code>/start</code>\n"
    "• <code>/status</code>\n"
    "• <code>/help</code>"
)

# ── Flask + Bot ─────────────────────────────────────────────────
app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# ── Thread locks ────────────────────────────────────────────────
_webhook_lock       = Lock()
_webhook_configured = False
_commands_lock      = Lock()
_commands_configured = False
_database_lock      = Lock()
_database_ready     = False

# ── User cache (60-second TTL) ──────────────────────────────────
_user_cache: dict = {}
_user_cache_lock  = Lock()
_USER_CACHE_TTL   = 60.0


# ═══════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════

def _mysql_is_configured() -> bool:
    return bool(DB_HOST and DB_USER and DB_PASSWORD and DB_NAME)


def _get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, connection_timeout=10,
    )


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

    # ADD missing columns
    if not col_exists("tg_first_name"):
        safe_exec("ALTER TABLE users ADD COLUMN tg_first_name VARCHAR(255) NULL AFTER chat_id")
    if not col_exists("tg_username"):
        safe_exec("ALTER TABLE users ADD COLUMN tg_username VARCHAR(255) NULL AFTER tg_first_name")
    if not col_exists("name"):
        safe_exec("ALTER TABLE users ADD COLUMN name VARCHAR(255) NULL AFTER tg_username")
    if not col_exists("phone"):
        safe_exec("ALTER TABLE users ADD COLUMN phone VARCHAR(20) NULL AFTER name")
    if not col_exists("state"):
        safe_exec("ALTER TABLE users ADD COLUMN state VARCHAR(20) NOT NULL DEFAULT 'START' AFTER phone")

    # Rename first_name → tg_first_name (copy data then drop)
    if col_exists("first_name"):
        safe_exec("UPDATE users SET tg_first_name = first_name WHERE tg_first_name IS NULL AND first_name IS NOT NULL")
        safe_exec("ALTER TABLE users DROP COLUMN `first_name`")

    # Rename username → tg_username (copy data then drop)
    if col_exists("username"):
        safe_exec("UPDATE users SET tg_username = username WHERE tg_username IS NULL AND username IS NOT NULL")
        safe_exec("ALTER TABLE users DROP COLUMN `username`")

    # Drop other obsolete columns
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
                    tg_username  VARCHAR(255),
                    name         VARCHAR(255),
                    phone        VARCHAR(20),
                    state        VARCHAR(20) NOT NULL DEFAULT 'START',
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
            try:
                if ADMIN_USER_IDS:
                    send_message(list(ADMIN_USER_IDS)[0], f"DEBUG DB Init Error: {e}")
            except:
                pass
            return False
        finally:
            if cursor:     cursor.close()
            if connection: connection.close()


def get_or_create_user(chat_id: int, tg_first_name: str, tg_username: str) -> dict:
    """Return user state dict from cache → DB → default."""
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
            # Keep Telegram name/username fresh
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

    except Exception as e:
        logger.exception("DB error in get_or_create_user")
        try:
            send_message(chat_id, f"DEBUG DB Error (get): {e}")
        except:
            pass
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
        cols   = list(sanitized.keys())
        vals   = list(sanitized.values())
        # UPSERT: create row if missing, otherwise update in place
        col_str  = ", ".join(cols)
        ph_str   = ", ".join(["%s"] * len(cols))
        upd_str  = ", ".join(f"`{k}` = %s" for k in cols)
        cursor.execute(
            f"INSERT INTO users (chat_id, {col_str}) "
            f"VALUES (%s, {ph_str}) "
            f"ON DUPLICATE KEY UPDATE {upd_str}",
            [chat_id] + vals + vals,
        )
        connection.commit()
        return True
    except Exception as e:
        logger.exception("DB error in update_user_state")
        try:
            send_message(chat_id, f"DEBUG DB Error (update): {e}")
        except:
            pass
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
            bot.set_my_commands(GLOBAL_BOT_COMMANDS)
            _commands_configured = True
        except Exception:
            logger.exception("Failed to set bot commands")


# ═══════════════════════════════════════════════════════════════
#  STATE MACHINE HANDLERS
# ═══════════════════════════════════════════════════════════════

def handle_start(chat_id: int, user_state: dict) -> None:
    """
    stateDiagram-v2
      [*] --> START
      START --> WAIT_NAME : /start
    """
    state = user_state.get("state", STATE_START)

    if state == STATE_IDLE:
        name  = escape(user_state.get("name")  or "—")
        phone = escape(user_state.get("phone") or "—")
        send_bot_message(
            chat_id,
            "✅ <b>អ្នកបានចុះឈ្មោះហើយ!</b>\n"
            "<code>━━━━━━━━━━━━━━━━</code>\n"
            f"👤 <b>ឈ្មោះ:</b> {name}\n"
            f"📱 <b>ទូរស័ព្ទ:</b> {phone}\n"
            "<code>━━━━━━━━━━━━━━━━</code>\n"
            "💡 ប្រើ <code>/status</code> ដើម្បីពិនិត្យ។",
            reply_markup=telebot.types.ReplyKeyboardRemove(),
        )
        return

    # Move to WAIT_NAME
    update_user_state(chat_id, state=STATE_WAIT_NAME)
    tg_name = escape(user_state.get("tg_first_name") or "")
    send_bot_message(
        chat_id,
        f"👋 <b>ស្វាគមន៍{(' ' + tg_name) if tg_name else ''}!</b>\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        "✏️ <b>ជំហានទី 1/2 — ឈ្មោះ</b>\n"
        "សូមវាយ <b>ឈ្មោះពេញ</b> របស់អ្នក:\n"
        "<i>(ឧ: សេង កុមារ)</i>",
        reply_markup=telebot.types.ReplyKeyboardRemove(),
    )


def handle_wait_name(chat_id: int, text: str) -> None:
    """
    WAIT_NAME --> WAIT_PHONE : input text (name ≥ 2 chars)
    WAIT_NAME --> WAIT_NAME  : name too short
    """
    name = text.strip()
    if len(name) < 2:
        send_bot_message(
            chat_id,
            "❌ <b>ឈ្មោះខ្លីពេក!</b>\n"
            "✏️ សូមវាយ <b>ឈ្មោះពេញ</b> ម្តងទៀត:\n"
            "<i>(ឧ: សេង កុមារ)</i>",
        )
        return  # Stay in WAIT_NAME

    update_user_state(chat_id, name=name, state=STATE_WAIT_PHONE)
    send_bot_message(
        chat_id,
        f"✅ <b>ឈ្មោះ:</b> {escape(name)}\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        "📱 <b>ជំហានទី 2/2 — ទូរស័ព្ទ</b>\n"
        "សូមវាយ <b>លេខទូរស័ព្ទ</b> របស់អ្នក:\n"
        "<i>(ឧ: 012345678 ឬ +85512345678)</i>",
    )


def handle_wait_phone(chat_id: int, text: str, user_state: dict) -> None:
    """
    WAIT_PHONE --> IDLE       : regex pass ✅
    WAIT_PHONE --> WAIT_PHONE : regex fail ❌
    """
    phone = text.strip()
    if not PHONE_REGEX.match(phone):
        send_bot_message(
            chat_id,
            "❌ <b>លេខទូរស័ព្ទមិនត្រឹមត្រូវ!</b>\n"
            "📱 សូមវាយ​ម្តងទៀត:\n"
            "<i>(ឧ: 012345678 ឬ +85512345678)</i>",
        )
        return  # Stay in WAIT_PHONE

    name = escape(user_state.get("name") or "")
    update_user_state(chat_id, phone=phone, state=STATE_IDLE)
    send_bot_message(
        chat_id,
        "🎉 <b>ការចុះឈ្មោះរួចរាល់!</b>\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👤 <b>ឈ្មោះ:</b> {name}\n"
        f"📱 <b>ទូរស័ព្ទ:</b> {escape(phone)}\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        "✅ <b>បានចុះឈ្មោះជោគជ័យ!</b>",
    )


def handle_status(chat_id: int, user_state: dict) -> None:
    state = user_state.get("state", STATE_START)
    labels = {
        STATE_START:      "🔵 START — មិនទាន់ចាប់ផ្តើម",
        STATE_WAIT_NAME:  "🟡 WAIT_NAME — រង់ចាំឈ្មោះ",
        STATE_WAIT_PHONE: "🟠 WAIT_PHONE — រង់ចាំទូរស័ព្ទ",
        STATE_IDLE:       "🟢 IDLE — ចុះឈ្មោះរួចហើយ ✅",
    }
    send_bot_message(
        chat_id,
        "📊 <b>ស្ថានភាពការចុះឈ្មោះ</b>\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        f"⚙️ <b>State:</b> {labels.get(state, state)}\n"
        f"👤 <b>ឈ្មោះ:</b> {escape(user_state.get('name') or '—')}\n"
        f"📱 <b>ទូរស័ព្ទ:</b> {escape(user_state.get('phone') or '—')}\n"
        f"📅 <b>ចូលប្រើ:</b> {_format_datetime(user_state.get('joined_date'))}\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        + ("✅ ចុះឈ្មោះរួចហើយ!" if state == STATE_IDLE else
           "💡 ប្រើ <code>/start</code> ដើម្បីបន្ត។"),
    )


def handle_help(chat_id: int, is_admin: bool = False) -> None:
    lines = [
        "📌 <b>បញ្ជីពាក្យបញ្ជា</b>",
        "━━━━━━━━━━━━",
        "• <code>/start</code>  — ចុះឈ្មោះ / ចាប់ផ្តើម",
        "• <code>/status</code> — ពិនិត្យស្ថានភាព",
        "• <code>/help</code>   — បញ្ជីពាក្យបញ្ជា",
    ]
    if is_admin:
        lines += [
            "",
            "🛡️ <b>Admin Commands</b>",
            "• <code>/users</code>       — ស្ថិតិអ្នកប្រើ",
            "• <code>/recentusers</code> — អ្នកប្រើថ្មីៗ",
        ]
    send_bot_message(chat_id, "\n".join(lines))


def send_admin_stats(chat_id: int) -> None:
    s = get_user_stats()
    send_bot_message(
        chat_id,
        "👥 <b>ស្ថិតិអ្នកប្រើ</b>\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📊 <b>អ្នកប្រើសរុប:</b> {s['total']}\n"
        f"🆕 <b>ចូលថ្ងៃនេះ:</b> {s['today']}\n"
        f"✅ <b>ចុះឈ្មោះហើយ (IDLE):</b> {s['completed']}\n"
        f"🛡️ <b>Admin:</b> {s['admins']}\n",
    )


def send_recent_users_msg(chat_id: int) -> None:
    users = get_recent_users(10)
    if not users:
        send_bot_message(chat_id, "📬 <b>មិនទាន់មានអ្នកប្រើទេ។</b>")
        return

    state_icon = {
        STATE_START:      "🔵",
        STATE_WAIT_NAME:  "🟡",
        STATE_WAIT_PHONE: "🟠",
        STATE_IDLE:       "🟢",
    }
    lines = ["📋 <b>អ្នកប្រើថ្មីៗ</b>",
             "<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n"]

    for i, u in enumerate(users, 1):
        st   = u.get("state") or STATE_START
        icon = state_icon.get(st, "⚪")
        un   = u.get("tg_username")
        un_t = f"@{escape(un)}" if un else "<i>គ្មាន</i>"
        admin_badge = " 🛡️ <b>[ADMIN]</b>" if u["chat_id"] in ADMIN_USER_IDS else ""
        lines.append(
            f"{icon} <b>#{i} {escape(u.get('tg_first_name') or '—')}</b>{admin_badge}\n"
            f"• 🆔 <code>{u['chat_id']}</code>  🏷️ {un_t}\n"
            f"• 👤 {escape(u.get('name') or '—')}  "
            f"📱 {escape(u.get('phone') or '—')}\n"
            f"• 📅 {_format_datetime(u.get('joined_date'))}\n"
        )
    lines.append("<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>")
    send_bot_message(chat_id, "\n".join(lines))


# ═══════════════════════════════════════════════════════════════
#  MAIN MESSAGE ROUTER
# ═══════════════════════════════════════════════════════════════

def handle_text_message(message: dict) -> None:
    user     = message.get("from") or {}
    chat     = message.get("chat") or {}
    chat_id  = chat.get("id")
    text     = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    tg_first_name = user.get("first_name") or "User"
    tg_username   = user.get("username")   or ""
    is_admin      = user.get("id") in ADMIN_USER_IDS

    user_state = get_or_create_user(chat_id, tg_first_name, tg_username)
    user_state["is_admin"] = is_admin
    state = user_state.get("state", STATE_START)

    # Parse command
    command = ""
    if text.startswith("/"):
        command = text.split()[0].split("@")[0].lower()

    # ── Command routing ─────────────────────────────────────────
    if command == "/start":
        handle_start(chat_id, user_state)
        return

    if command == "/status":
        handle_status(chat_id, user_state)
        return

    if command == "/help":
        handle_help(chat_id, is_admin=is_admin)
        return

    if command == "/users" and is_admin:
        send_admin_stats(chat_id)
        return

    if command == "/recentusers" and is_admin:
        send_recent_users_msg(chat_id)
        return

    if command:
        send_bot_message(chat_id, UNKNOWN_COMMAND_TEXT)
        return

    # ── State machine: free-text routing ───────────────────────
    #
    #  stateDiagram-v2
    #    [*]          --> START
    #    START        --> WAIT_NAME  : /start
    #    WAIT_NAME    --> WAIT_PHONE : input text (name)
    #    WAIT_PHONE   --> IDLE       : regex pass
    #    WAIT_PHONE   --> WAIT_PHONE : regex fail

    if state == STATE_WAIT_NAME:
        handle_wait_name(chat_id, text)

    elif state == STATE_WAIT_PHONE:
        handle_wait_phone(chat_id, text, user_state)

    elif state == STATE_IDLE:
        send_bot_message(
            chat_id,
            "✅ <b>អ្នកបានចុះឈ្មោះហើយ!</b>\n"
            "💡 ប្រើ <code>/status</code> ដើម្បីមើលព័ត៌មាន។",
        )

    else:  # STATE_START or unknown
        send_bot_message(
            chat_id,
            "👋 ប្រើ <code>/start</code> ដើម្បីចុះឈ្មោះ!",
        )


# ═══════════════════════════════════════════════════════════════
#  FLASK ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    if TELEGRAM_SECRET_TOKEN:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token", "") != TELEGRAM_SECRET_TOKEN:
            abort(403)

    configure_bot_commands()

    try:
        update = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"ok": True})

    message = update.get("message") or update.get("edited_message")
    if message:
        try:
            handle_text_message(message)
        except Exception:
            logger.exception("Error handling message")

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
        STATE_IDLE=STATE_IDLE,
        STATE_START=STATE_START,
        STATE_WAIT_NAME=STATE_WAIT_NAME,
        STATE_WAIT_PHONE=STATE_WAIT_PHONE,
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
