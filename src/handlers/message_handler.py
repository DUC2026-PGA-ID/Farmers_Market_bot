# ─────────────────────────────────────────────────────────────
#  src/handlers/message_handler.py
#  Lead Developer: ROEUNG BUNHENG
#  Purpose: Strictly handles chat messages only.
#           No DB queries. No network calls.
#           Delegates all business logic to src/services/.
# ─────────────────────────────────────────────────────────────
import logging
from html import escape

import telebot

from src.services.catalog_service import get_all_crops
from src.services.weather_service import fetch_weather

logger = logging.getLogger(__name__)

# ── State constants (imported by app.py too) ─────────────────
STATE_START      = "START"
STATE_WAIT_NAME  = "WAIT_NAME"
STATE_WAIT_PHONE = "WAIT_PHONE"
STATE_IDLE       = "IDLE"


# ═══════════════════════════════════════════════════════════════
#  HELPERS (injected from app.py to avoid circular imports)
# ═══════════════════════════════════════════════════════════════

_send_bot_message   = None
_update_user_state  = None
_get_or_create_user = None
_get_db_connection  = None
_ensure_db_ready    = None
_admin_ids          = set()
_phone_regex        = None
_bot                = None


def init_handler(send_fn, update_fn, get_user_fn,
                 db_conn_fn, db_ready_fn,
                 admin_ids, phone_regex, bot_instance):
    """
    Called once from app.py at startup to inject dependencies.
    This keeps message_handler.py free of global state / config.
    """
    global _send_bot_message, _update_user_state, _get_or_create_user
    global _get_db_connection, _ensure_db_ready
    global _admin_ids, _phone_regex, _bot

    _send_bot_message   = send_fn
    _update_user_state  = update_fn
    _get_or_create_user = get_user_fn
    _get_db_connection  = db_conn_fn
    _ensure_db_ready    = db_ready_fn
    _admin_ids          = admin_ids
    _phone_regex        = phone_regex
    _bot                = bot_instance


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
        _send_bot_message(
            chat_id,
            "✅ <b>អ្នកបានចុះឈ្មោះហើយ!</b>\n"
            "<code>━━━━━━━━━━━━━━━━</code>\n"
            f"👤 <b>ឈ្មោះ:</b> {name}\n"
            f"📱 <b>ទូរស័ព្ទ:</b> {phone}\n"
            "<code>━━━━━━━━━━━━━━━━</code>\n",
            reply_markup=telebot.types.ReplyKeyboardRemove(),
        )
        return

    _update_user_state(chat_id, state=STATE_WAIT_NAME)
    tg_name = escape(user_state.get("tg_first_name") or "")
    _send_bot_message(
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
    WAIT_NAME --> WAIT_PHONE : name >= 2 chars
    WAIT_NAME --> WAIT_NAME  : name too short
    """
    name = text.strip()
    if len(name) < 2:
        _send_bot_message(
            chat_id,
            "❌ <b>ឈ្មោះខ្លីពេក!</b>\n"
            "✏️ សូមវាយ <b>ឈ្មោះពេញ</b> ម្តងទៀត:\n"
            "<i>(ឧ: សេង កុមារ)</i>",
        )
        return

    _update_user_state(chat_id, name=name, state=STATE_WAIT_PHONE)
    _send_bot_message(
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
    if not _phone_regex.match(phone):
        _send_bot_message(
            chat_id,
            "❌ <b>លេខទូរស័ព្ទមិនត្រឹមត្រូវ!</b>\n"
            "📱 សូមវាយ​ម្តងទៀត:\n"
            "<i>(ឧ: 012345678 ឬ +85512345678)</i>",
        )
        return

    name = escape(user_state.get("name") or "")
    _update_user_state(chat_id, phone=phone, state=STATE_IDLE)
    _send_bot_message(
        chat_id,
        "🎉 <b>ការចុះឈ្មោះរួចរាល់!</b>\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        f"👤 <b>ឈ្មោះ:</b> {name}\n"
        f"📱 <b>ទូរស័ព្ទ:</b> {escape(phone)}\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        "✅ <b>បានចុះឈ្មោះជោគជ័យ!</b>",
    )


# ═══════════════════════════════════════════════════════════════
#  COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════

def handle_view_catalog(chat_id: int) -> None:
    """
    Delegates to catalog_service (src/services layer).
    Renders live DB rows as an InlineKeyboard menu.
    """
    crops = get_all_crops(_get_db_connection, _ensure_db_ready)
    if not crops:
        _send_bot_message(
            chat_id,
            "📦 <b>មិនមានកសិផលក្នុងកាតាឡុកទេ / No products in catalog yet.</b>"
        )
        return

    markup = telebot.types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        telebot.types.InlineKeyboardButton(
            f"{c['crop_name']} — {c['unit']}",
            callback_data=f"crop_{c['crop_id']}"
        )
        for c in crops
    ]
    markup.add(*buttons)
    _send_bot_message(
        chat_id,
        "📦 <b>កាតាឡុកកសិផល / Product Catalog:</b>\n"
        "សូមជ្រើសរើសផលិតផលខាងក្រោម:",
        reply_markup=markup,
    )


def handle_weather(chat_id: int) -> None:
    """
    Delegates to weather_service (src/services layer).
    Calls Open-Meteo live API and renders result.

    Exception Handling (Requirement 3):
      - ConnectionError → friendly timeout message to user
      - ValueError      → friendly parse error message to user
      - Server never crashes — all exceptions caught here.
    """
    _send_bot_message(chat_id, "🌐 <b>កំពុងទាញទិន្នន័យ… / Fetching live weather…</b>")
    try:
        w = fetch_weather()
        time_label = "🌞 昼間" if w["is_day"] else "🌙 夜間"
        _send_bot_message(
            chat_id,
            "🌤️ <b>អាកាសធាតុបច្ចុប្បន្ន — ភ្នំពេញ / Live Weather — Phnom Penh</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            f"{w['icon']} <b>លក្ខខណ្ឌ:</b> {w['condition']}\n"
            f"🌡️ <b>សីតុណ្ហភាព:</b> {w['temperature']} °C\n"
            f"💨 <b>ល្បឿនខ្យល់:</b> {w['windspeed']} km/h\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "<i>ប្រភព: Open-Meteo API (Real-time)</i>",
        )
    except (ConnectionError, ValueError) as exc:
        # Graceful error — bot notifies user, server keeps running
        _send_bot_message(chat_id, str(exc))
    except Exception:
        logger.exception("handle_weather: unexpected error")
        _send_bot_message(
            chat_id,
            "⚠️ <b>មានបញ្ហាផ្ទៃក្នុង / Internal error. Please try again.</b>"
        )


def send_admin_stats(chat_id: int, get_user_stats_fn) -> None:
    s = get_user_stats_fn()
    _send_bot_message(
        chat_id,
        "👥 <b>ស្ថិតិអ្នកប្រើ</b>\n"
        "<code>━━━━━━━━━━━━━━━━</code>\n"
        f"📊 <b>អ្នកប្រើសរុប:</b> {s['total']}\n"
        f"🆕 <b>ចូលថ្ងៃនេះ:</b> {s['today']}\n"
        f"✅ <b>ចុះឈ្មោះហើយ (IDLE):</b> {s['completed']}\n"
        f"🛡️ <b>Admin:</b> {s['admins']}\n",
    )


def send_recent_users_msg(chat_id: int, get_recent_users_fn,
                          format_datetime_fn) -> None:
    users = get_recent_users_fn(10)
    if not users:
        _send_bot_message(chat_id, "📬 <b>មិនទាន់មានអ្នកប្រើទេ។</b>")
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
        admin_badge = " 🛡️ <b>[ADMIN]</b>" if u["chat_id"] in _admin_ids else ""
        lines.append(
            f"{icon} <b>#{i} {escape(u.get('tg_first_name') or '—')}</b>{admin_badge}\n"
            f"• 🆔 <code>{u['chat_id']}</code>  🏷️ {un_t}\n"
            f"• 👤 {escape(u.get('name') or '—')}  "
            f"📱 {escape(u.get('phone') or '—')}\n"
            f"• 📅 {format_datetime_fn(u.get('joined_date'))}\n"
        )
    lines.append("<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>")
    _send_bot_message(chat_id, "\n".join(lines))


# ═══════════════════════════════════════════════════════════════
#  MAIN MESSAGE ROUTER
# ═══════════════════════════════════════════════════════════════

UNKNOWN_COMMAND_TEXT = (
    "🤖 <b>មិនទាន់ស្គាល់ពាក្យបញ្ជានេះទេ</b>\n"
    "សូមសាក:\n"
    "• <code>/start</code>\n"
    "• <code>/view_catalog</code>\n"
    "• <code>/weather</code>"
)


def handle_text_message(message: dict,
                        get_user_stats_fn,
                        get_recent_users_fn,
                        format_datetime_fn) -> None:
    user     = message.get("from") or {}
    chat     = message.get("chat") or {}
    chat_id  = chat.get("id")
    text     = (message.get("text") or "").strip()
    if not chat_id or not text:
        return

    tg_first_name = user.get("first_name") or "User"
    tg_username   = user.get("username")   or ""
    is_admin      = user.get("id") in _admin_ids

    user_state = _get_or_create_user(chat_id, tg_first_name, tg_username)
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

    if command == "/view_catalog":
        handle_view_catalog(chat_id)
        return

    if command == "/weather":
        handle_weather(chat_id)
        return

    if command == "/users" and is_admin:
        send_admin_stats(chat_id, get_user_stats_fn)
        return

    if command == "/recentusers" and is_admin:
        send_recent_users_msg(chat_id, get_recent_users_fn, format_datetime_fn)
        return

    if command:
        _send_bot_message(chat_id, UNKNOWN_COMMAND_TEXT)
        return

    # ── State machine: free-text routing ─────────────────────────
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
        _send_bot_message(
            chat_id,
            "✅ <b>អ្នកបានចុះឈ្មោះហើយ!</b>\n"
            "ប្រើ <code>/view_catalog</code> ដើម្បីមើលផលិតផល\n"
            "ប្រើ <code>/weather</code> ដើម្បីមើលអាកាសធាតុ",
        )

    else:  # STATE_START or unknown
        _send_bot_message(
            chat_id,
            "👋 ប្រើ <code>/start</code> ដើម្បីចុះឈ្មោះ!",
        )
