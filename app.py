import hashlib
import logging
import os
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
        "\U0001f33e **\u178f\u1798\u17d2\u179b\u17c3\u179f\u17d2\u179a\u17bc\u179c"
        "\u1790\u17d2\u1784\u17c3\u1793\u17c1\u17c7\u17d6**\n"
        "- \u179f\u17d2\u179a\u17bc\u179c\u1780\u17d2\u179a\u17a2\u17bc\u1794 "
        "(\u179b\u17c1\u1781\u17e1)\u17d6 1,300 \u179a\u17c0\u179b/"
        "\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798\n"
        "- \u179f\u17d2\u179a\u17bc\u179c\u179f\u1785\u17c6\u1794\u17c9\u17b6\u17d6 "
        "1,150 \u179a\u17c0\u179b/\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798"
    ),
    BUTTON_PEPPER: (
        "\U0001f336\ufe0f **\u178f\u1798\u17d2\u179b\u17c3\u1798\u17d2\u1791\u17c1\u179f"
        "\u1790\u17d2\u1784\u17c3\u1793\u17c1\u17c7\u17d6**\n"
        "- \u1798\u17d2\u1791\u17c1\u179f\u178a\u17c3\u1793\u17b6\u1784\u17d6 3,500 "
        "\u179a\u17c0\u179b/\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798\n"
        "- \u1798\u17d2\u1791\u17c1\u179f\u17a2\u17b6\u1785\u1798\u17cd\u179f\u178f\u17d2\u179c\u17d6 "
        "6,000 \u179a\u17c0\u179b/\u1782\u17b8\u17a1\u17bc\u1780\u17d2\u179a\u17b6\u1798"
    ),
    BUTTON_MARKET: (
        "\U0001f4c8 **\u179a\u1794\u17b6\u1799\u1780\u17b6\u179a\u178e\u17cd"
        "\u1791\u17b8\u1795\u17d2\u179f\u17b6\u179a\u17d6** "
        "\u179f\u17d2\u1790\u17b6\u1793\u1797\u17b6\u1796\u178f\u1798\u17d2\u179b\u17c3"
        "\u1780\u179f\u17b7\u1795\u179b\u179f\u1794\u17d2\u178f\u17b6\u17a0\u17cd"
        "\u1793\u17c1\u17c7\u1798\u17b6\u1793\u179b\u17c6\u1793\u17b9\u1784\u179b\u17d2\u17a2 "
        "\u1798\u17b7\u1793\u1798\u17b6\u1793\u1780\u17b6\u179a\u1794\u17d2\u179a\u17c2"
        "\u1794\u17d2\u179a\u17bd\u179b\u1781\u17d2\u179b\u17b6\u17c6\u1784\u17a1\u17be\u1799\u17d4"
    ),
    BUTTON_CONTACT: (
        "\U0001f4de **\u1780\u17d2\u179a\u17bb\u1798\u1780\u17b6\u179a\u1784\u17b6\u179a "
        "Immortal Digital\u17d6**\n"
        "\u179f\u17a0\u1780\u17b6\u179a \u1793\u17b7\u1784\u179a\u17b6\u1799\u1780\u17b6"
        "\u179a\u178e\u17cd\u178f\u1798\u17d2\u179b\u17c3\u1791\u17bc\u179a\u179f\u1796\u17d2"
        "\u1791\u17d6 012 345 678"
    ),
}

FALLBACK_TEXT = (
    "\u179f\u17bc\u1798\u1787\u17d2\u179a\u17be\u179f\u179a\u17be\u179f"
    "\u1794\u17ca\u17bc\u178f\u17bb\u1784\u1781\u17b6\u1784\u1780\u17d2\u179a\u17c4\u1798 "
    "\u17ac\u179c\u17b6\u1799 /start \u1798\u17d2\u178f\u1784\u1791\u17c0\u178f\u17d4"
)

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

_webhook_lock = Lock()
_webhook_configured = False
_webhook_skip_logged = False
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
                    joined_date DATETIME NOT NULL DEFAULT UTC_TIMESTAMP(),
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


def _display_name(first_name: str, username: str) -> str:
    if first_name:
        return first_name
    if username:
        return f"@{username}"
    return "\u1780\u179f\u17b7\u1780\u179a"


def send_welcome(chat_id: int, user_name: str, user_state: dict) -> None:
    if not user_state.get("db_enabled"):
        intro = (
            f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8 {user_name}! "
            "\u179f\u17d2\u179c\u17b6\u1782\u1798\u1793\u17cd\u1798\u1780\u1780\u17b6\u1793\u17cb "
            "Agri-Trade Bot!\n\n"
        )
    elif user_state.get("is_new_user"):
        intro = (
            f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8 {user_name}! "
            "\u17a2\u17d2\u1793\u1780\u1782\u17ba\u1787\u17b6\u17a2\u17d2\u1793\u1780"
            "\u1794\u17d2\u179a\u17be\u1790\u17d2\u1798\u17b8 \u179f\u17d2\u179c\u17b6"
            "\u1782\u1798\u1793\u17cd\u1798\u1780\u1780\u17b6\u1793\u17cb Agri-Trade Bot!\n\n"
        )
    else:
        intro = (
            f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8 {user_name}! "
            "\u179f\u17c2\u179c\u1782\u1798\u1793\u17cd\u1798\u1780\u179c\u17b7\u1789 "
            "Agri-Trade Bot!\n\n"
        )

    admin_note = ""
    if user_state.get("is_admin"):
        admin_note = (
            "\U0001f6e1\ufe0f Admin mode active.\n"
            "Commands: /users , /recentusers\n\n"
        )

    welcome_text = (
        f"{intro}{admin_note}"
        "\u1794\u17d2\u179a\u1796\u17d0\u1793\u17d2\u1792 Agri-Trade Bot "
        "\u1795\u17d2\u179b\u17bc\u179c\u1780\u17b6\u179a\u179a\u1794\u179f\u17cb Immortal Digital!\n\n"
        "\u179f\u17bc\u1798\u1787\u17d2\u179a\u17be\u179f\u179a\u17be\u179f\u179f\u17c1"
        "\u179c\u17b6\u1780\u1798\u17d2\u1798\u1795\u17d2\u1793\u17c2\u1780\u1781\u17b6"
        "\u1784\u1780\u17d2\u179a\u17c4\u1798\u17d6"
    )
    bot.send_message(chat_id, welcome_text, reply_markup=build_main_keyboard())


def send_admin_stats(chat_id: int) -> None:
    stats = get_user_stats()
    if not stats:
        bot.send_message(
            chat_id,
            "MySQL user database is not ready yet. Please check database settings.",
        )
        return

    stats_text = (
        "\U0001f465 User Stats\n"
        f"- Total users: {stats['total_users']}\n"
        f"- Joined today: {stats['joined_today']}\n"
        f"- Admin users: {stats['admin_users']}"
    )
    bot.send_message(chat_id, stats_text)


def send_recent_users(chat_id: int) -> None:
    recent_users = get_recent_users()
    if not recent_users:
        bot.send_message(
            chat_id,
            "No recent users found, or MySQL user database is not ready yet.",
        )
        return

    lines = ["\U0001f4cb Recent Users"]
    for user in recent_users:
        name = user["first_name"] or "Unknown"
        admin_badge = " [admin]" if user["chat_id"] in ADMIN_USER_IDS else ""
        lines.append(
            f"- {name}{admin_badge}: gender={user['gender']}, joined={user['joined_date']}"
        )

    bot.send_message(chat_id, "\n".join(lines))


def handle_text_message(chat_id: int, text: str, user_state: dict, user: dict) -> None:
    command = text.split()[0].split("@")[0].lower() if text else ""
    user_name = _display_name(user.get("first_name", ""), user.get("username", ""))

    if command == "/start":
        send_welcome(chat_id, user_name, user_state)
        return

    if command == "/users":
        if user_state.get("is_admin"):
            send_admin_stats(chat_id)
        else:
            bot.send_message(chat_id, "This command is for admins only.")
        return

    if command == "/recentusers":
        if user_state.get("is_admin"):
            send_recent_users(chat_id)
        else:
            bot.send_message(chat_id, "This command is for admins only.")
        return

    response = BUTTON_RESPONSES.get(text, FALLBACK_TEXT)
    bot.send_message(chat_id, response)


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
    configured = configure_webhook(force=True)
    return jsonify(
        {
            "ok": configured,
            "desired_webhook_url": _desired_webhook_url(),
        }
    ), (200 if configured else 500)


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
