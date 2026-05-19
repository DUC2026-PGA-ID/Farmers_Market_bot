import hashlib
import logging
import os
from html import escape
from threading import Lock

import telebot
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql = None
    MySQLError = Exception

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PATH = "/" + os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip("/")
AUTO_SET_WEBHOOK = os.getenv("AUTO_SET_WEBHOOK", "true").lower() == "true"
MYSQL_HOST = os.getenv("MYSQL_HOST", "")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "")
MYSQL_USER = os.getenv("MYSQL_USER", "")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
ADMIN_USER_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_USER_IDS", "").split(",")
    if value.strip().isdigit()
}
# Telegram user profiles do not expose gender, so we default it until
# you add a separate collection step in the bot conversation.
DEFAULT_GENDER = "unknown"
# Telegram secret tokens only allow a narrow character set, so we derive
# a stable header-safe token from the configured secret.
TELEGRAM_SECRET_TOKEN = (
    hashlib.sha256(WEBHOOK_SECRET.encode("utf-8")).hexdigest()
    if WEBHOOK_SECRET
    else ""
)

BUTTON_RICE = "\U0001f33e \u178f\u1798\u17d2\u179b\u17c3\u179f\u17d2\u179a\u17bc\u179c"
BUTTON_PEPPER = "\U0001f336\ufe0f \u178f\u1798\u17d2\u179b\u17c3\u1798\u17d2\u1791\u17c1\u179f"
BUTTON_MARKET = "\U0001f4c8 \u1791\u17b8\u1795\u17d2\u179f\u17b6\u179a"
BUTTON_CONTACT = "\U0001f4de \u1791\u17c6\u1793\u17b6\u1780\u17cb\u1791\u17c6\u1793\u1784"

BUTTON_RESPONSES = {
    BUTTON_RICE: (
        "\U0001f33e <b>\u178f\u1798\u17d2\u179b\u17c3\u179f\u17d2\u179a\u17bc\u179c"
        "\u1790\u17d2\u1784\u17c3\u1793\u17c1\u17c7</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u2022 \u179f\u17d2\u179a\u17bc\u179c\u1780\u17d2\u179a\u17a2\u17bc\u1794 "
        "(\u179b\u17c1\u1781\u17e1): <b>1,300 \u179a\u17c0\u179b/"
        "\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798</b>\n"
        "\u2022 \u179f\u17d2\u179a\u17bc\u179c\u179f\u1785\u17c6\u1794\u17c9\u17b6: "
        "<b>1,150 \u179a\u17c0\u179b/\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798</b>\n\n"
        "\U0001f4a1 \u178f\u1798\u17d2\u179b\u17c3\u17a2\u17b6\u1785\u1794\u17d2\u179a\u17c2"
        "\u1794\u17d2\u179a\u17bd\u179b\u178f\u17b6\u1798\u178f\u17c6\u1794\u1793\u17cb "
        "\u1793\u17b7\u1784\u1796\u17c1\u179b\u179c\u17c1\u179b\u17b6\u17d4"
    ),
    BUTTON_PEPPER: (
        "\U0001f336\ufe0f <b>\u178f\u1798\u17d2\u179b\u17c3\u1798\u17d2\u1791\u17c1\u179f"
        "\u1790\u17d2\u1784\u17c3\u1793\u17c1\u17c7</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u2022 \u1798\u17d2\u1791\u17c1\u179f\u178a\u17c3\u1793\u17b6\u1784: "
        "<b>3,500 \u179a\u17c0\u179b/\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798</b>\n"
        "\u2022 \u1798\u17d2\u1791\u17c1\u179f\u17a2\u17b6\u1785\u1798\u17cd\u179f\u178f\u17d2\u179c: "
        "<b>6,000 \u179a\u17c0\u179b/\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798</b>\n\n"
        "\U0001f4a1 \u178f\u1798\u17d2\u179b\u17c3\u17a2\u17b6\u1785\u1794\u17d2\u179a\u17c2"
        "\u1794\u17d2\u179a\u17bd\u179b\u178f\u17b6\u1798\u1798\u17bb\u1784\u1780\u17b6\u179b "
        "\u1793\u17b7\u1784\u1782\u17bb\u178e\u1797\u17b6\u1796\u1795\u179b\u17b7\u178f\u1795\u179b\u17d4"
    ),
    BUTTON_MARKET: (
        "\U0001f4c8 <b>\u179f\u17d2\u1790\u17b6\u1793\u1797\u17b6\u1796"
        "\u1791\u17b8\u1795\u17d2\u179f\u17b6\u179a</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u2022 \u178f\u1798\u17d2\u179b\u17c3\u1780\u179f\u17b7\u1795\u179b\u179f\u1794\u17d2"
        "\u178f\u17b6\u17a0\u17cd\u1793\u17c1\u17c7\u1798\u17b6\u1793\u179f\u17d2\u1790\u17c1"
        "\u179a\u1797\u17b6\u1796\u179b\u17d2\u17a2\u17d4\n"
        "\u2022 \u178f\u1798\u17d2\u179a\u17bc\u179c\u1780\u17b6\u179a\u1791\u17b8\u1795\u17d2\u179f\u17b6"
        "\u179a\u1793\u17c5\u178f\u17c2\u1798\u17b6\u1793\u179b\u17d2\u17a2\u179f\u1798\u17d2\u179a\u17b6\u1794\u17cb"
        "\u1795\u179b\u17b7\u178f\u1795\u179b\u1780\u179f\u17b7\u1780\u1798\u17d2\u1798\u17d4\n"
        "\u2022 \u179f\u17bc\u1798\u178f\u17b6\u1798\u178a\u17b6\u1793\u1794\u1785\u17d2\u1785\u17bb\u1794\u17d2"
        "\u1794\u1793\u17d2\u1793\u1797\u17b6\u1796\u1787\u17b6\u1794\u17d2\u179a\u1785\u17b6\u17c6\u17d4"
    ),
    BUTTON_CONTACT: (
        "\U0001f4de <b>\u1791\u17c6\u1793\u17b6\u1780\u17cb\u1791\u17c6\u1793\u1784</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "<b>Immortal Digital</b>\n"
        "\u2022 \u1791\u17bc\u179a\u179f\u1796\u17d2\u1791: <code>012 345 678</code>\n"
        "\u2022 \u179f\u17c1\u179c\u17b6: \u1796\u17d0\u178f\u17cc\u1798\u17b6\u1793\u1791\u17b8\u1795\u17d2\u179f\u17b6\u179a "
        "\u1793\u17b7\u1784\u1780\u17b6\u179a\u1782\u17b6\u17c6\u1791\u17d2\u179a\u1780\u179f\u17b7\u1780\u179a\n\n"
        "\U0001f4ac \u179f\u17bc\u1798\u1794\u17d2\u179a\u17be <code>/help</code> "
        "\u178a\u17be\u1798\u17d2\u1794\u17b8\u1798\u17be\u179b\u1798\u17bb\u1781\u1784\u17b6\u179a\u1791\u17b6\u17c6\u1784\u17a2\u179f\u17cb\u17d4"
    ),
}

COMMAND_TO_BUTTON = {
    "/rice": BUTTON_RICE,
    "/pepper": BUTTON_PEPPER,
    "/market": BUTTON_MARKET,
    "/contact": BUTTON_CONTACT,
}

GLOBAL_BOT_COMMANDS = [
    telebot.types.BotCommand("start", "ម៉ឺនុយមេ"),
    telebot.types.BotCommand("help", "មើលបញ្ជីពាក្យបញ្ជា"),
    telebot.types.BotCommand("rice", "មើលតម្លៃស្រូវ"),
    telebot.types.BotCommand("pepper", "មើលតម្លៃម្ទេស"),
    telebot.types.BotCommand("market", "មើលស្ថានភាពទីផ្សារ"),
    telebot.types.BotCommand("contact", "មើលព័ត៌មានទំនាក់ទំនង"),
]

ADMIN_BOT_COMMANDS = GLOBAL_BOT_COMMANDS + [
    telebot.types.BotCommand("users", "មើលស្ថិតិអ្នកប្រើ"),
    telebot.types.BotCommand("recentusers", "មើលអ្នកប្រើថ្មីៗ"),
]

FALLBACK_TEXT = (
    "\U0001f916 <b>\u1798\u17b7\u1793\u1791\u17b6\u1793\u17cb\u179f\u17d2\u1782\u17b6\u179b\u17cb"
    "\u1796\u17b6\u1780\u17d2\u1799\u1794\u1789\u17d2\u1787\u17b6\u1793\u17c1\u17c7\u1791\u17c1</b>\n"
    "\u179f\u17bc\u1798\u179f\u17b6\u1780\u1798\u17bd\u1799\u1780\u17d2\u1793\u17bb\u1784\u1785\u17c6\u178e\u17c4\u1798:\n"
    "\u2022 <code>/start</code>\n"
    "\u2022 <code>/help</code>\n"
    "\u2022 <code>/rice</code>\n"
    "\u2022 <code>/pepper</code>\n"
    "\u2022 <code>/market</code>\n"
    "\u2022 <code>/contact</code>"
)

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

_webhook_lock = Lock()
_webhook_configured = False
_webhook_skip_logged = False
_commands_lock = Lock()
_commands_configured = False
_database_lock = Lock()
_database_ready = False
_database_skip_logged = False


def _public_base_url() -> str:
    explicit_url = os.getenv("WEBHOOK_URL")
    if explicit_url:
        return explicit_url.rstrip("/")

    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        return render_url.rstrip("/")

    return ""


def _desired_webhook_url() -> str:
    public_base_url = _public_base_url()
    if not public_base_url:
        return ""
    return f"{public_base_url}{WEBHOOK_PATH}"


def _mysql_is_configured() -> bool:
    # XAMPP often uses the default MySQL root user with a blank password.
    # Treat host, database, and user as required, but allow an empty password.
    return all([MYSQL_HOST.strip(), MYSQL_DATABASE.strip(), MYSQL_USER.strip()])


def _get_db_connection():
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        database=MYSQL_DATABASE,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )


def ensure_database_ready() -> bool:
    global _database_ready, _database_skip_logged

    if _database_ready:
        return True

    if not _mysql_is_configured():
        if not _database_skip_logged:
            logger.info(
                "MySQL user management is disabled because database "
                "environment variables are not fully configured."
            )
            _database_skip_logged = True
        return False

    if mysql is None:
        if not _database_skip_logged:
            logger.warning(
                "MySQL user management is disabled because "
                "mysql-connector-python is not installed."
            )
            _database_skip_logged = True
        return False

    with _database_lock:
        if _database_ready:
            return True

        connection = None
        cursor = None
        try:
            connection = _get_db_connection()
            cursor = connection.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT NOT NULL AUTO_INCREMENT,
                    chat_id BIGINT NOT NULL,
                    first_name VARCHAR(255) NOT NULL,
                    gender VARCHAR(32) NOT NULL DEFAULT 'unknown',
                    joined_date DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (id),
                    UNIQUE KEY uq_users_chat_id (chat_id)
                )
                """
            )
            connection.commit()
            _database_ready = True
            logger.info("MySQL users table is ready.")
            return True
        except MySQLError:
            logger.exception("Unable to initialize MySQL users table.")
            return False
        finally:
            if cursor is not None:
                cursor.close()
            if connection is not None:
                connection.close()


def register_or_update_user(message: dict) -> dict:
    user = message.get("from", {})
    chat = message.get("chat", {})
    user_id = user.get("id")
    chat_id = chat.get("id")
    is_admin = user_id in ADMIN_USER_IDS if user_id is not None else False

    state = {
        "db_enabled": False,
        "is_new_user": False,
        "is_admin": is_admin,
        "joined_date": None,
        "gender": DEFAULT_GENDER,
    }

    if not user_id or not chat_id or not ensure_database_ready():
        return state

    connection = None
    cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor(dictionary=True)
        latest_first_name = user.get("first_name") or "Farmer"
        cursor.execute(
            "SELECT id, first_name, gender, joined_date FROM users WHERE chat_id = %s",
            (chat_id,),
        )
        existing_user = cursor.fetchone()

        state["db_enabled"] = True
        state["is_new_user"] = existing_user is None
        if existing_user:
            state["joined_date"] = existing_user["joined_date"]
            state["gender"] = existing_user["gender"] or DEFAULT_GENDER
            if latest_first_name != (existing_user["first_name"] or ""):
                cursor.execute(
                    "UPDATE users SET first_name = %s WHERE chat_id = %s",
                    (latest_first_name, chat_id),
                )
                connection.commit()

        if existing_user is None:
            cursor.execute(
                """
                INSERT INTO users (
                    chat_id,
                    first_name,
                    gender,
                    joined_date
                )
                VALUES (%s, %s, %s, UTC_TIMESTAMP())
                """,
                (
                    chat_id,
                    latest_first_name,
                    DEFAULT_GENDER,
                ),
            )
            connection.commit()
            state["joined_date"] = None

        return state
    except MySQLError:
        logger.exception("Unable to save Telegram user to MySQL.")
        return state
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def get_user_stats():
    if not ensure_database_ready():
        return None

    connection = None
    cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                COALESCE(SUM(CASE
                    WHEN DATE(joined_date) = UTC_DATE() THEN 1 ELSE 0 END), 0)
                    AS joined_today
            FROM users
            """
        )
        stats = cursor.fetchone()
        stats["admin_users"] = len(ADMIN_USER_IDS)
        return stats
    except MySQLError:
        logger.exception("Unable to fetch MySQL user stats.")
        return None
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def get_recent_users(limit: int = 10):
    if not ensure_database_ready():
        return []

    connection = None
    cursor = None
    try:
        connection = _get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                id,
                chat_id,
                first_name,
                gender,
                joined_date
            FROM users
            ORDER BY joined_date DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cursor.fetchall()
    except MySQLError:
        logger.exception("Unable to fetch recent MySQL users.")
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None:
            connection.close()


def configure_webhook(force: bool = False) -> bool:
    global _webhook_configured, _webhook_skip_logged

    webhook_url = _desired_webhook_url()
    if not webhook_url:
        if not _webhook_skip_logged:
            logger.info(
                "Skipping Telegram webhook setup because WEBHOOK_URL or "
                "RENDER_EXTERNAL_URL is not set."
            )
            _webhook_skip_logged = True
        return False

    with _webhook_lock:
        if _webhook_configured and not force:
            return True

        try:
            current_webhook = bot.get_webhook_info()
            if current_webhook and current_webhook.url == webhook_url and not force:
                _webhook_configured = True
                logger.info("Telegram webhook already configured: %s", webhook_url)
                return True

            bot.set_webhook(
                url=webhook_url,
                secret_token=TELEGRAM_SECRET_TOKEN or None,
            )
            _webhook_configured = True
            logger.info("Telegram webhook configured: %s", webhook_url)
            return True
        except Exception:
            logger.exception("Unable to configure Telegram webhook.")
            return False


def configure_bot_commands(force: bool = False) -> bool:
    global _commands_configured

    with _commands_lock:
        if _commands_configured and not force:
            return True

        try:
            bot.set_my_commands(GLOBAL_BOT_COMMANDS)
            for admin_user_id in ADMIN_USER_IDS:
                bot.set_my_commands(
                    ADMIN_BOT_COMMANDS,
                    scope=telebot.types.BotCommandScopeChat(admin_user_id),
                )
            _commands_configured = True
            logger.info("Telegram command menu configured.")
            return True
        except Exception:
            logger.exception("Unable to configure Telegram command menu.")
            return False


configure_bot_commands()

if AUTO_SET_WEBHOOK:
    configure_webhook()

ensure_database_ready()


def _validate_telegram_request() -> None:
    content_type = request.headers.get("Content-Type", "")
    if not content_type.startswith("application/json"):
        abort(403)

    if TELEGRAM_SECRET_TOKEN:
        secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if secret_header != TELEGRAM_SECRET_TOKEN:
            abort(403)


def build_main_keyboard():
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        telebot.types.KeyboardButton(BUTTON_RICE),
        telebot.types.KeyboardButton(BUTTON_PEPPER),
    )
    markup.add(
        telebot.types.KeyboardButton(BUTTON_MARKET),
        telebot.types.KeyboardButton(BUTTON_CONTACT),
    )
    return markup


def send_bot_message(chat_id: int, text: str, reply_markup=None) -> None:
    bot.send_message(
        chat_id,
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


def _display_name(first_name: str, username: str) -> str:
    if first_name:
        return first_name
    if username:
        return f"@{username}"
    return "\u1780\u179f\u17b7\u1780\u179a"


def _format_datetime(value) -> str:
    if not value:
        return "មិនទាន់មាន"
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y %H:%M")
    return escape(str(value))


def _format_gender(value: str) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"male", "m"}:
        return "ប្រុស"
    if normalized in {"female", "f"}:
        return "ស្រី"
    if normalized in {"other"}:
        return "ផ្សេងៗ"
    return "មិនទាន់កំណត់"


def build_help_text(user_state: dict) -> str:
    lines = [
        "\U0001f4cc <b>បញ្ជីពាក្យបញ្ជា</b>",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
        "\u2022 <code>/start</code> - បើកម៉ឺនុយមេ",
        "\u2022 <code>/help</code> - មើលបញ្ជីពាក្យបញ្ជាទាំងអស់",
        "\u2022 <code>/rice</code> - មើលតម្លៃស្រូវ",
        "\u2022 <code>/pepper</code> - មើលតម្លៃម្ទេស",
        "\u2022 <code>/market</code> - មើលស្ថានភាពទីផ្សារ",
        "\u2022 <code>/contact</code> - មើលព័ត៌មានទំនាក់ទំនង",
    ]
    if user_state.get("is_admin"):
        lines.extend(
            [
                "",
                "\U0001f6e1\ufe0f <b>ពាក្យបញ្ជាសម្រាប់អ្នកគ្រប់គ្រង</b>",
                "\u2022 <code>/users</code> - មើលស្ថិតិអ្នកប្រើ",
                "\u2022 <code>/recentusers</code> - មើលអ្នកប្រើថ្មីៗ",
            ]
        )
    return "\n".join(lines)


def send_welcome(chat_id: int, user_name: str, user_state: dict) -> None:
    safe_user_name = escape(user_name)
    if not user_state.get("db_enabled"):
        intro = (
            f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8 {safe_user_name}! "
            "\u179f\u17d2\u179c\u17b6\u1782\u1798\u1793\u17cd\u1798\u1780\u1780\u17b6\u1793\u17cb "
            "Agri-Trade Bot!\n\n"
        )
    elif user_state.get("is_new_user"):
        intro = (
            f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8 {safe_user_name}! "
            "\u17a2\u17d2\u1793\u1780\u1782\u17ba\u1787\u17b6\u17a2\u17d2\u1793\u1780"
            "\u1794\u17d2\u179a\u17be\u1790\u17d2\u1798\u17b8 \u179f\u17d2\u179c\u17b6"
            "\u1782\u1798\u1793\u17cd\u1798\u1780\u1780\u17b6\u1793\u17cb Agri-Trade Bot!\n\n"
        )
    else:
        intro = (
            f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8 {safe_user_name}! "
            "\u179f\u17c2\u179c\u1782\u1798\u1793\u17cd\u1798\u1780\u179c\u17b7\u1789 "
            "Agri-Trade Bot!\n\n"
        )

    admin_note = ""
    if user_state.get("is_admin"):
        admin_note = (
            "\U0001f6e1\ufe0f <b>របៀបអ្នកគ្រប់គ្រងកំពុងដំណើរការ</b>\n"
            "\u2022 <code>/users</code>\n"
            "\u2022 <code>/recentusers</code>\n\n"
        )

    welcome_text = (
        f"{intro}"
        "\U0001f33f <b>Agri-Trade Bot</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        "\u1794\u17d2\u179a\u1796\u17d0\u1793\u17d2\u1792\u1796\u17d0\u178f\u17cc\u1798\u17b6\u1793"
        "\u1791\u17b8\u1795\u17d2\u179f\u17b6\u179a\u1780\u179f\u17b7\u1780\u179a "
        "\u1795\u17d2\u179b\u17bc\u179c\u1780\u17b6\u179a\u179a\u1794\u179f\u17cb Immortal Digital!\n\n"
        "\U0001f680 <b>ពាក្យបញ្ជារហ័ស</b>\n"
        "\u2022 <code>/rice</code>  \u1798\u17be\u179b\u178f\u1798\u17d2\u179b\u17c3\u179f\u17d2\u179a\u17bc\u179c\n"
        "\u2022 <code>/pepper</code>  \u1798\u17be\u179b\u178f\u1798\u17d2\u179b\u17c3\u1798\u17d2\u1791\u17c1\u179f\n"
        "\u2022 <code>/market</code>  \u1798\u17be\u179b\u179f\u17d2\u1790\u17b6\u1793\u1797\u17b6\u1796\u1791\u17b8\u1795\u17d2\u179f\u17b6\u179a\n"
        "\u2022 <code>/contact</code>  \u1780\u17b6\u179a\u1791\u17c6\u1793\u17b6\u1780\u17cb\u1791\u17c6\u1793\u1784\n"
        "\u2022 <code>/help</code>  \u1798\u17be\u179b\u1794\u1789\u17d2\u1787\u17b8\u1796\u17b6\u1780\u17d2\u1799\u1794\u1789\u17d2\u1787\u17b6\u1791\u17b6\u17c6\u1784\u17a2\u179f\u17cb\n\n"
        f"{admin_note}"
        "\U0001f447 \u179f\u17bc\u1798\u1787\u17d2\u179a\u17be\u179f\u1794\u17ca\u17bc\u178f\u17bb\u1784"
        "\u1781\u17b6\u1784\u1780\u17d2\u179a\u17c4\u1798 \u17ac\u1794\u17d2\u179a\u17be slash command \u1781\u17b6\u1784\u179b\u17be\u17d4"
    )
    send_bot_message(chat_id, welcome_text, reply_markup=build_main_keyboard())


def send_admin_stats(chat_id: int) -> None:
    stats = get_user_stats()
    if not stats:
        send_bot_message(
            chat_id,
            "\u26a0\ufe0f <b>\u1798\u17b7\u1793\u1791\u17b6\u1793\u17cb\u17a2\u17b6\u1785"
            "\u1794\u17be\u1780\u1798\u17bc\u179b\u178a\u17d2\u178b\u17b6\u1793\u1791\u17b7\u1793\u17d2\u1793\u1793\u17d0\u1799"
            "\u17a2\u17d2\u1793\u1780\u1794\u17d2\u179a\u17be\u1794\u17b6\u1793\u1791\u17c1</b>\n"
            "\u179f\u17bc\u1798\u178f\u17d2\u179a\u17bd\u178f\u1796\u17b7\u1793\u17b7\u178f\u17d2\u1799"
            "\u1780\u17b6\u179a\u1780\u17c6\u178e\u178f\u17cb database \u1798\u17d2\u178f\u1784\u1791\u17c0\u178f\u17d4",
        )
        return

    stats_text = (
        "\U0001f465 <b>\u179f\u17d2\u1790\u17b7\u178f\u17b7\u17a2\u17d2\u1793\u1780\u1794\u17d2\u179a\u17be</b>\n"
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"\u2022 \u17a2\u17d2\u1793\u1780\u1794\u17d2\u179a\u17be\u179f\u179a\u17bb\u1794: <b>{stats['total_users']}</b>\n"
        f"\u2022 \u1785\u17bc\u179b\u1794\u17d2\u179a\u17be\u1790\u17d2\u1784\u17c3\u1793\u17c1\u17c7: <b>{stats['joined_today']}</b>\n"
        f"\u2022 \u17a2\u17d2\u1793\u1780\u1782\u17d2\u179a\u1794\u17cb\u1782\u17d2\u179a\u1784: <b>{stats['admin_users']}</b>"
    )
    send_bot_message(chat_id, stats_text)


def send_recent_users(chat_id: int) -> None:
    recent_users = get_recent_users()
    if not recent_users:
        send_bot_message(
            chat_id,
            "\U0001f4ed <b>\u1798\u17b7\u1793\u1791\u17b6\u1793\u17cb\u1798\u17b6\u1793"
            "\u1794\u1789\u17d2\u1787\u17b8\u17a2\u17d2\u1793\u1780\u1794\u17d2\u179a\u17be\u1790\u17d2\u1798\u17b8\u17d7</b>\n"
            "\u1798\u17bc\u179b\u178a\u17d2\u178b\u17b6\u1793\u1791\u17b7\u1793\u17d2\u1793\u1793\u17d0\u1799"
            "\u17a2\u17b6\u1785\u1793\u17c5\u1791\u1791\u17c1 \u17ac \u1798\u17b7\u1793\u1791\u17b6\u1793\u17cb"
            "\u179a\u17bd\u1785\u179a\u17b6\u179b\u17cb\u1793\u17c5\u17a1\u17be\u1799\u1791\u17c1\u17d4",
        )
        return

    lines = [
        "\U0001f4cb <b>\u17a2\u17d2\u1793\u1780\u1794\u17d2\u179a\u17be\u1790\u17d2\u1798\u17b8\u17d7</b>",
        "\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501",
    ]
    for index, user in enumerate(recent_users, start=1):
        name = escape(user["first_name"] or "\u1798\u17b7\u1793\u1791\u17b6\u1793\u17cb\u1798\u17b6\u1793\u1788\u17d2\u1798\u17c4\u17c7")
        admin_badge = " <b>[អ្នកគ្រប់គ្រង]</b>" if user["chat_id"] in ADMIN_USER_IDS else ""
        gender = _format_gender(user["gender"] or DEFAULT_GENDER)
        joined_date = _format_datetime(user["joined_date"])
        lines.append(
            f"{index}. <b>{name}</b>{admin_badge}\n"
            f"   \u2022 \u1797\u17c1\u1791: {gender}\n"
            f"   \u2022 \u1785\u17bc\u179b\u1794\u17d2\u179a\u17be: <code>{joined_date}</code>"
        )
        if index != len(recent_users):
            lines.append("")

    send_bot_message(chat_id, "\n".join(lines))


def handle_text_message(chat_id: int, text: str, user_state: dict, user: dict) -> None:
    command = text.split()[0].split("@")[0].lower() if text else ""
    user_name = _display_name(user.get("first_name", ""), user.get("username", ""))

    if command == "/start":
        send_welcome(chat_id, user_name, user_state)
        return

    if command == "/help":
        send_bot_message(
            chat_id,
            build_help_text(user_state),
            reply_markup=build_main_keyboard(),
        )
        return

    if command in COMMAND_TO_BUTTON:
        send_bot_message(chat_id, BUTTON_RESPONSES[COMMAND_TO_BUTTON[command]])
        return

    if command == "/users":
        if user_state.get("is_admin"):
            send_admin_stats(chat_id)
        else:
            send_bot_message(
                chat_id,
                "\u26d4 <b>\u179f\u1798\u17d2\u179a\u17b6\u1794\u17cb\u17a2\u17d2\u1793\u1780"
                "\u1782\u17d2\u179a\u1794\u17cb\u1782\u17d2\u179a\u1784\u1794\u17c9\u17bb\u178e\u17d2\u178e\u17c4\u17c7</b>\n"
                "\u1796\u17b6\u1780\u17d2\u1799\u1794\u1789\u17d2\u1787\u17b6\u1793\u17c1\u17c7\u17a2\u17b6\u1785"
                "\u1794\u17d2\u179a\u17be\u1794\u17b6\u1793\u178f\u17c2\u178a\u17c4\u1799\u17a2\u17d2\u1793\u1780\u1782\u17d2\u179a\u1794\u17cb\u1782\u17d2\u179a\u1784\u1794\u17c9\u17bb\u178e\u17d2\u178e\u17c4\u17c7\u17d4",
            )
        return

    if command == "/recentusers":
        if user_state.get("is_admin"):
            send_recent_users(chat_id)
        else:
            send_bot_message(
                chat_id,
                "\u26d4 <b>\u179f\u1798\u17d2\u179a\u17b6\u1794\u17cb\u17a2\u17d2\u1793\u1780"
                "\u1782\u17d2\u179a\u1794\u17cb\u1782\u17d2\u179a\u1784\u1794\u17c9\u17bb\u178e\u17d2\u178e\u17c4\u17c7</b>\n"
                "\u1796\u17b6\u1780\u17d2\u1799\u1794\u1789\u17d2\u1787\u17b6\u1793\u17c1\u17c7\u17a2\u17b6\u1785"
                "\u1794\u17d2\u179a\u17be\u1794\u17b6\u1793\u178f\u17c2\u178a\u17c4\u1799\u17a2\u17d2\u1793\u1780\u1782\u17d2\u179a\u1794\u17cb\u1782\u17d2\u179a\u1784\u1794\u17c9\u17bb\u178e\u17d2\u178e\u17c4\u17c7\u17d4",
            )
        return

    response = BUTTON_RESPONSES.get(text, FALLBACK_TEXT)
    send_bot_message(chat_id, response)


@app.post(WEBHOOK_PATH)
def telegram_webhook():
    _validate_telegram_request()

    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message")
    if not message:
        return "OK", 200

    chat = message.get("chat", {})
    from_user = message.get("from", {})
    chat_id = chat.get("id")
    text = message.get("text", "")

    if not chat_id:
        return "OK", 200

    user_state = register_or_update_user(message)
    logger.info("Incoming Telegram message: chat_id=%s text=%r", chat_id, text)

    try:
        handle_text_message(chat_id, text, user_state, from_user)
    except Exception:
        logger.exception("Failed to handle Telegram message.")
        return "ERROR", 500

    return "OK", 200


@app.get("/")
def index():
    return jsonify(
        {
            "service": "farmers-market-bot",
            "status": "running",
            "mode": "webhook",
            "webhook_path": WEBHOOK_PATH,
        }
    )


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/setup-webhook")
def setup_webhook():
    commands_configured = configure_bot_commands(force=True)
    configured = configure_webhook(force=True)
    return jsonify(
        {
            "ok": configured and commands_configured,
            "commands_ok": commands_configured,
            "desired_webhook_url": _desired_webhook_url(),
        }
    ), (200 if configured and commands_configured else 500)


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
