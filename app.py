import hashlib
import logging
import os
from threading import Lock

import telebot
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, request

load_dotenv()

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required.")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_PATH = "/" + os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip("/")
AUTO_SET_WEBHOOK = os.getenv("AUTO_SET_WEBHOOK", "true").lower() == "true"
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


def send_welcome(chat_id: int, user_name: str) -> None:
    welcome_text = (
        f"\U0001f44b \u179f\u17bd\u179f\u17d2\u178f\u17b8/\u1787\u1798\u17d2\u179a"
        f"\u17b6\u1794\u179f\u17bd\u179a {user_name}! \u179f\u17d2\u179c\u17b6\u1782"
        "\u1798\u1793\u17cd\u1798\u1780\u1780\u17b6\u1793\u17cb\u1794\u17d2\u179a\u1796"
        "\u17d0\u1793\u17d2\u1792 Agri-Trade Bot \u1795\u17d2\u179b\u17bc\u179c\u1780"
        "\u17b6\u179a\u179a\u1794\u179f\u17cb Immortal Digital!\n\n"
        "\u179f\u17bc\u1798\u1787\u17d2\u179a\u17be\u179f\u179a\u17be\u179f\u179f\u17c1"
        "\u179c\u17b6\u1780\u1798\u17d2\u1798\u1795\u17d2\u1793\u17c2\u1780\u1781\u17b6"
        "\u1784\u1780\u17d2\u179a\u17c4\u1798\u17d6"
    )
    bot.send_message(chat_id, welcome_text, reply_markup=build_main_keyboard())


def handle_text_message(chat_id: int, text: str, first_name: str) -> None:
    command = text.split()[0].split("@")[0].lower() if text else ""
    if command == "/start":
        send_welcome(chat_id, first_name or "\u1780\u179f\u17b7\u1780\u179a")
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
    first_name = from_user.get("first_name", "")

    if not chat_id:
        return "OK", 200

    logger.info("Incoming Telegram message: chat_id=%s text=%r", chat_id, text)

    try:
        handle_text_message(chat_id, text, first_name)
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
