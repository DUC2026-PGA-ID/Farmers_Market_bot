# ─────────────────────────────────────────────────────────────
#  src/handlers/message_handler.py
#  Lead Developer: ROEUNG BUNHENG
#  Purpose: Strictly handles chat messages only.
#           No DB queries. No network calls.
#           Delegates all business logic to src/services/.
# ─────────────────────────────────────────────────────────────
import logging
from html import escape
import re
import os
import telebot

from src.services.catalog_service import get_all_crops, get_crop_by_id
from src.services.weather_service import fetch_weather
from src.services.price_service import (
    get_today_prices,
    get_crops_for_price_menu, ensure_prices_table,
)
from src.services.buyer_service import get_all_buyers, add_buyer
from src.services.notification_service import get_all_user_chat_ids, generate_price_alert_message
from src.services.market_service import add_listing, get_recent_listings

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
    # Guard: if regex not yet initialised, fail safely
    if _phone_regex is None or not _phone_regex.match(phone):
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

def _translate_to_khmer(text: str) -> str:
    if not text:
        return ""
    translations = {
        "Corn": "ពោត",
        "Cucumber": "ម្ទេស",
        "Damaged Rice": "ឪឡឹក",
        "Mango": "ស្វាយ",
        "Rice": "អង្ករ",
        "kg": "គីឡូក្រាម",
        "Sack": "បាវ",
        "50kg Sack": "បាវ ៥០គីឡូ"
    }
    return translations.get(text.strip(), text.strip())

def handle_view_catalog(chat_id: int) -> None:
    """
    Delegates to catalog_service (src/services layer).
    Renders live DB rows as an InlineKeyboard menu.
    """
    try:
        crops = get_all_crops(_get_db_connection, _ensure_db_ready)
        if not crops:
            _send_bot_message(
                chat_id,
                "📦 <b>មិនទាន់មានកសិផលក្នុងកាតាឡុកទេ</b>"
            )
            return

        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        buttons = []
        for c in crops:
            kh_name = _translate_to_khmer(c['crop_name'])
            kh_unit = _translate_to_khmer(c['unit'])
            if c['crop_name'] == "Damaged Rice":
                kh_unit = "គីឡូក្រាម"
            
            # Emojis for better UX
            emoji = "🌾"
            if "ពោត" in kh_name: emoji = "🌽"
            elif "ម្ទេស" in kh_name: emoji = "🌶️"
            elif "ឪឡឹក" in kh_name: emoji = "🍉"
            elif "ស្វាយ" in kh_name: emoji = "🥭"
            elif "អង្ករ" in kh_name: emoji = "🍚"
            
            btn_text = f"{emoji} {kh_name} ({kh_unit})"
            buttons.append(
                telebot.types.InlineKeyboardButton(
                    btn_text,
                    callback_data=f"crop_{c['crop_id']}"
                )
            )
        
        markup.add(*buttons)
        _send_bot_message(
            chat_id,
            "📦 <b>កាតាឡុកកសិផល:</b>\n"
            "សូមជ្រើសរើសប្រភេទកសិផលខាងក្រោម៖",
            reply_markup=markup,
        )
    except Exception:
        logger.exception("handle_view_catalog: unexpected error")
        _send_bot_message(
            chat_id,
            "⚠️ <b>មានបញ្ហាទាញយកផលិតផល សូមព្យាយាមម្តងទៀត។</b>"
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
        _send_bot_message(
            chat_id,
            "🌤️ <b>អាកាសធាតុបច្ចុប្បន្ន — ភ្នំពេញ / Live Weather — Phnom Penh</b>\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            f"{w['icon']} <b>លក្ខខណ្ឌ:</b> {w['condition']}\n"
            f"🌡️ <b>សីតុណ្ហភាព:</b> {w['temperature']} °C\n"
            f"🤔 <b>អារម្មណ៍ដូច:</b> {w['feels_like']} °C\n"
            f"💧 <b>សំណើម:</b> {w['humidity']} %\n"
            f"💨 <b>ល្បឿនខ្យល់:</b> {w['windspeed']} km/h\n"
            "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
            "<i>ប្រភព: wttr.in (Real-time)</i>",
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


# ═══════════════════════════════════════════════════════════════
#  REQ-S01 — DAILY PRICE TRACKER
# ═══════════════════════════════════════════════════════════════

_TREND_ICON = {
    "up":      "📈",
    "down":    "📉",
    "stable":  "➡️",
    "new":     "🆕",
    "no_data": "❓",
}

_TREND_LABEL = {
    "up":      "ឡើង",
    "down":    "ចុះ",
    "stable":  "ថិតថេរ",
    "new":     "ថ្មី",
    "no_data": "គ្មានទិន្នន័យ",
}


def _fmt_price(amount) -> str:
    """Format number as KHR with comma separator. e.g. 25000 → 25,000 ៛"""
    if amount is None:
        return "—"
    try:
        return f"{int(float(amount)):,} ៛"
    except (ValueError, TypeError):
        return str(amount)


def handle_price(chat_id: int) -> None:
    """
    REQ-S01: Show today's verified Phnom Penh market prices with trend.
    Delegated entirely to price_service — no DB logic here.
    """
    try:
        ensure_prices_table(_get_db_connection, _ensure_db_ready)
        prices = get_today_prices(_get_db_connection, _ensure_db_ready)

        if not prices:
            _send_bot_message(
                chat_id,
                "📊 <b>មិនទាន់មានទិន្នន័យតម្លៃទីផ្សារទេ។</b>\n"
                "<i>ប្រព័ន្ធកំពុងទាញយកទិន្នន័យស្វ័យប្រវត្តិ សូមរង់ចាំបន្តិច។</i>"
            )
            return

        lines = [
            "📊 <b>តម្លៃទីផ្សារភ្នំពេញ — ថ្ងៃនេះ</b>",
            "<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>",
        ]

        has_any_price = False
        for p in prices:
            trend = p["trend"]
            icon  = _TREND_ICON.get(trend, "❓")
            label = _TREND_LABEL.get(trend, "")
            kh_name = _translate_to_khmer(p["crop_name"])
            kh_unit = _translate_to_khmer(p["unit"])
            if p["crop_name"] == "Damaged Rice":
                kh_unit = "គីឡូក្រាម"
                
            name  = escape(kh_name)
            unit  = escape(kh_unit)

            if trend == "no_data":
                lines.append(f"❓ <b>{name}</b> — <i>មិនទាន់មានតម្លៃ</i>")
                continue

            has_any_price = True
            price_str = _fmt_price(p["price"])
            change_str = ""
            if trend == "up":
                change_str = f" <i>(+{_fmt_price(p['change'])})</i>"
            elif trend == "down":
                change_str = f" <i>(-{_fmt_price(p['change'])})</i>"

            lines.append(
                f"{icon} <b>{name}</b> — {price_str}/{unit}\n"
                f"   └ {label}{change_str}"
            )

        lines.append("<code>━━━━━━━━━━━━━━━━━━━━━━━━━━</code>")
        if has_any_price:
            lines.append("<i>💡 ប្រភព: ប្រព័ន្ធទាញយកតម្លៃស្វ័យប្រវត្តិប្រចាំថ្ងៃ</i>")
        else:
            lines.append("<i>⏳ ប្រព័ន្ធនឹងធ្វើបច្ចុប្បន្នភាពតម្លៃក្នុងពេលឆាប់ៗនេះ</i>")

        _send_bot_message(chat_id, "\n".join(lines))

    except Exception:
        logger.exception("handle_price: unexpected error")
        _send_bot_message(
            chat_id,
            "⚠️ <b>មានបញ្ហាទាញតម្លៃ / Could not load prices. Try again.</b>"
        )


def send_admin_stats(chat_id: int, get_user_stats_fn) -> None:
    try:
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
    except Exception:
        logger.exception("send_admin_stats: unexpected error")
        _send_bot_message(chat_id, "⚠️ <b>មានបញ្ហាទាញស្ថិតិ / Could not load stats.</b>")


def send_recent_users_msg(chat_id: int, get_recent_users_fn,
                          format_datetime_fn) -> None:
    try:
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
            admin_badge = " 🛡️ <b>[ADMIN]</b>" if u.get("chat_id") in _admin_ids else ""
            lines.append(
                f"{icon} <b>#{i} {escape(u.get('tg_first_name') or '—')}</b>{admin_badge}\n"
                f"• 🆔 <code>{u.get('chat_id', '?')}</code>  🏷️ {un_t}\n"
                f"• 👤 {escape(u.get('name') or '—')}  "
                f"📱 {escape(u.get('phone') or '—')}\n"
                f"• 📅 {format_datetime_fn(u.get('joined_date'))}\n"
            )
        lines.append("<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>")
        _send_bot_message(chat_id, "\n".join(lines))
    except Exception:
        logger.exception("send_recent_users_msg: unexpected error")
        _send_bot_message(chat_id, "⚠️ <b>មានបញ្ហាទាញទិន្នន័យ / Could not load users.</b>")





def handle_buyers(chat_id: int) -> None:
    """
    REQ-S02: Verified Buyer Directory
    Displays a list of verified buyers to the farmers.
    """
    try:
        buyers = get_all_buyers(_get_db_connection, _ensure_db_ready)
        if not buyers:
            _send_bot_message(
                chat_id,
                "🤝 <b>បញ្ជីឈ្មោះអ្នកទិញ</b>\n\n"
                "<i>មិនទាន់មានអ្នកទិញនៅក្នុងប្រព័ន្ធនៅឡើយទេ។</i>"
            )
            return
            
        msg = "🤝 <b>បញ្ជីឈ្មោះអ្នកទិញដែលបានផ្ទៀងផ្ទាត់</b>\n<code>━━━━━━━━━━━━━━━━━━━━━━━━</code>\n\n"
        for i, b in enumerate(buyers, 1):
            icon = "✅" if b["is_verified"] else "⏳"
            company = f"🏢 <b>ក្រុមហ៊ុន:</b> {escape(b['company'])}\n" if b["company"] else ""
            username = b.get("telegram_username")
            username_str = f"💬 <b>Telegram:</b> <a href='https://t.me/{escape(username.replace('@', ''))}'>{escape(username)}</a>\n" if username else ""
            
            msg += f"👤 <b>{i}. {escape(b['name'])}</b> {icon}\n"
            msg += f"📞 <b>ទូរស័ព្ទ:</b> <code>{escape(b['phone'])}</code>\n"
            msg += username_str
            msg += company
            msg += "<code>━━━━━━━━━━━━━━━━</code>\n"
            
        _send_bot_message(chat_id, msg)
    except Exception:
        logger.exception("message_handler: Error in handle_buyers")
        _send_bot_message(chat_id, "⚠️ មានបញ្ហាក្នុងការទាញយកទិន្នន័យអ្នកទិញ។")


def handle_addbuyer(chat_id: int, text: str) -> None:
    """
    REQ-S02: Admin command to add a buyer.
    Format: /addbuyer Name, Phone, @username, [Company]
    """
    try:
        parts = text.replace("/addbuyer", "").strip()
        if not parts:
            _send_bot_message(
                chat_id,
                "ℹ️ <b>របៀបប្រើប្រាស់:</b>\n"
                "<code>/addbuyer</code> ឈ្មោះ, លេខទូរស័ព្ទ, @username, [ក្រុមហ៊ុន]\n\n"
                "ឧទាហរណ៍:\n"
                "<code>/addbuyer</code> លោក សុខ, 012345678, @sokh_buyer, កសិដ្ឋាន កក្កដា"
            )
            return
            
        items = [i.strip() for i in parts.split(',')]
        if len(items) < 3:
            _send_bot_message(chat_id, "⚠️ សូមបញ្ចូលយ៉ាងហោចណាស់ <b>ឈ្មោះ</b>, <b>លេខទូរស័ព្ទ</b> និង <b>@username</b> ដោយខណ្ឌចែកដោយសញ្ញាក្បៀស (,)។")
            return
            
        name = items[0]
        phone = items[1]
        telegram_username = items[2]
        if not telegram_username.startswith("@"):
            telegram_username = "@" + telegram_username
            
        company = items[3] if len(items) > 3 else ""
        
        success = add_buyer(name, phone, telegram_username, company, _get_db_connection, _ensure_db_ready)
        if success:
            company_str = escape(company) if company else "មិនមាន"
            _send_bot_message(chat_id, f"✅ <b>បានបន្ថែមអ្នកទិញជោគជ័យ!</b>\n<code>━━━━━━━━━━━━━━━━</code>\n👤 <b>ឈ្មោះ:</b> {escape(name)}\n📞 <b>ទូរស័ព្ទ:</b> <code>{escape(phone)}</code>\n💬 <b>Telegram:</b> {escape(telegram_username)}\n🏢 <b>ក្រុមហ៊ុន:</b> {company_str}")
        else:
            _send_bot_message(chat_id, "⚠️ មិនអាចបន្ថែមអ្នកទិញបានទេ សូមព្យាយាមម្តងទៀត។")
    except Exception:
        logger.exception("message_handler: Error in handle_addbuyer")
        _send_bot_message(chat_id, "⚠️ មានបញ្ហាក្នុងការបន្ថែមអ្នកទិញ។")


def handle_broadcast(chat_id: int, text: str) -> None:
    """
    REQ-S03: Admin command to broadcast a custom message to all users.
    """
    try:
        msg_text = text.replace("/broadcast", "").strip()
        if not msg_text:
            _send_bot_message(chat_id, "⚠️ សូមបញ្ចូលសារដែលចង់ផ្ញើ។ ឧទាហរណ៍: /broadcast សួស្តីបងប្អូនកសិករ!")
            return
            
        all_chats = get_all_user_chat_ids(_get_db_connection, _ensure_db_ready)
        success_count = 0
        for cid in all_chats:
            try:
                _send_bot_message(cid, f"📢 សេចក្តីជូនដំណឹង:\n\n{escape(msg_text)}")
                success_count += 1
            except Exception:
                pass
                
        _send_bot_message(chat_id, f"✅ បានផ្ញើសារទៅកាន់អ្នកប្រើប្រាស់ចំនួន {success_count} នាក់។")
    except Exception:
        logger.exception("message_handler: Error in handle_broadcast")
        _send_bot_message(chat_id, "⚠️ មានបញ្ហាក្នុងការផ្ញើសារ។")


def handle_pricealert(chat_id: int) -> None:
    """
    REQ-S03: Admin command to broadcast today's prices to all users.
    """
    try:
        alert_msg = generate_price_alert_message(_get_db_connection, _ensure_db_ready)
        if not alert_msg:
            _send_bot_message(chat_id, "⚠️ មិនមានទិន្នន័យតម្លៃទីផ្សារថ្មីទេ។")
            return
            
        all_chats = get_all_user_chat_ids(_get_db_connection, _ensure_db_ready)
        success_count = 0
        for cid in all_chats:
            try:
                _send_bot_message(cid, alert_msg)
                success_count += 1
            except Exception:
                pass
                
        _send_bot_message(chat_id, f"✅ បានផ្ញើដំណឹងតម្លៃទីផ្សារទៅកាន់អ្នកប្រើប្រាស់ចំនួន {success_count} នាក់។")
    except Exception:
        logger.exception("message_handler: Error in handle_pricealert")
        _send_bot_message(chat_id, "⚠️ មានបញ្ហាក្នុងការផ្ញើដំណឹងតម្លៃទីផ្សារ។")


def auto_broadcast_daily_price() -> None:
    """
    Called by background thread in app.py to automatically broadcast
    daily prices at a specific time without admin intervention.
    """
    try:
        alert_msg = generate_price_alert_message(_get_db_connection, _ensure_db_ready)
        if not alert_msg:
            return
            
        all_chats = get_all_user_chat_ids(_get_db_connection, _ensure_db_ready)
        for cid in all_chats:
            try:
                _send_bot_message(cid, alert_msg)
            except Exception:
                pass
        logger.info("message_handler: Auto-broadcasted daily price to %d users.", len(all_chats))
    except Exception:
        logger.exception("message_handler: Error in auto_broadcast_daily_price")


def handle_sell(chat_id: int, text: str) -> None:
    """
    REQ-S05: Let farmers list a B-Grade crop.
    Format: /sell Crop Name, Grade, Quantity, Price
    """
    try:
        parts = text.replace("/sell", "").strip()
        if not parts:
            _send_bot_message(
                chat_id,
                "ℹ️ របៀបប្រកាសលក់កសិផល\n\n"
                "/sell ឈ្មោះដំណាំ, ប្រភេទ, ចំនួន, តម្លៃ\n\n"
                "ឧទាហរណ៍:\n"
                "/sell ស្រូវសើម, ប្រភេទ A, ៥០០គីឡូ, ១២០០៛/គីឡូ"
            )
            return
            
        items = [i.strip() for i in parts.split(',')]
        if len(items) < 4:
            _send_bot_message(chat_id, "⚠️ សូមបញ្ចូលព័ត៌មានឲ្យបានគ្រប់គ្រាន់ ដោយខណ្ឌចែកដោយសញ្ញាក្បៀស (,) ចំនួន៣។")
            return
            
        crop_name = items[0]
        grade = items[1]
        quantity = items[2]
        price = items[3]
        
        success = add_listing(chat_id, crop_name, grade, quantity, price, _get_db_connection, _ensure_db_ready)
        if success:
            _send_bot_message(chat_id, f"✅ <b>បានប្រកាសលក់ជោគជ័យ!</b>\n\n🌾 {escape(crop_name)}\n🏷 {escape(grade)}\n📦 {escape(quantity)}\n💰 {escape(price)}\n\n<i>អ្នកទិញនឹងឃើញការប្រកាសនេះក្នុង /market</i>")
        else:
            _send_bot_message(chat_id, "⚠️ មិនអាចប្រកាសលក់បានទេ សូមព្យាយាមម្តងទៀត។")
    except Exception:
        logger.exception("message_handler: Error in handle_sell")
        _send_bot_message(chat_id, "⚠️ មានបញ្ហាក្នុងការប្រកាសលក់។")


def handle_market(chat_id: int) -> None:
    """
    REQ-S05: Display all B-Grade listings.
    """
    try:
        listings = get_recent_listings(_get_db_connection, _ensure_db_ready)
        if not listings:
            _send_bot_message(
                chat_id,
                "🛒 <b>ទីផ្សារលក់រាយ</b>\n\n"
                "<i>មិនទាន់មានការប្រកាសលក់នៅឡើយទេ។</i>\n"
                "អ្នកអាចប្រកាសលក់បានតាមរយៈ <code>/sell</code>"
            )
            return
            
        msg = "🛒 <b>ទីផ្សារលក់រាយថ្មីៗ</b>\n<code>━━━━━━━━━━━━━━━━</code>\n"
        for l in listings:
            seller = l['seller_name'] or "កសិករ"
            phone = l['phone'] or "មិនមានលេខទូរស័ព្ទ"
            tg_un = f"@{l['tg_username']}" if l.get('tg_username') else "មិនមាន"
            
            msg += f"\n🌾 <b>{escape(l['crop_name'])}</b> ({escape(l['grade'])})\n"
            msg += f"📦 {escape(l['quantity'])} | 💰 {escape(l['price'])}\n"
            msg += f"👤 {escape(seller)} | 📞 <code>{escape(phone)}</code>\n"
            msg += f"💬 Telegram: {escape(tg_un)}\n"
            
            lat = l.get('latitude')
            lon = l.get('longitude')
            if lat and lon:
                maps_url = f"https://www.google.com/maps?q={lat},{lon}"
                msg += f"📍 <b>ទីតាំងចម្ការ:</b> <a href='{maps_url}'>មើលលើផែនទី 🗺️</a>\n"
            
        _send_bot_message(chat_id, msg)
    except Exception:
        logger.exception("message_handler: Error in handle_market")
        _send_bot_message(chat_id, "⚠️ មានបញ្ហាក្នុងការទាញយកទិន្នន័យទីផ្សារ។")


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
    # ── Top-level safety guard — nothing here can crash the server ──
    try:
        _route_message(message, get_user_stats_fn, get_recent_users_fn, format_datetime_fn)
    except Exception:
        logger.exception("handle_text_message: unhandled top-level exception")


def _route_message(message: dict,
                   get_user_stats_fn,
                   get_recent_users_fn,
                   format_datetime_fn) -> None:
    """Inner routing logic — called by handle_text_message inside a try/except."""
    user     = message.get("from") or {}
    chat     = message.get("chat") or {}
    chat_id  = chat.get("id")
    text     = (message.get("text") or "").strip()
    location = message.get("location")
    
    if not chat_id:
        return
        
    if not text and not location:
        return

    tg_first_name = user.get("first_name") or "User"
    tg_username   = user.get("username")   or ""
    is_admin      = user.get("id") in _admin_ids

    user_state = _get_or_create_user(chat_id, tg_first_name, tg_username) or {}
    user_state["is_admin"] = is_admin
    state = user_state.get("state", STATE_START)

    # Parse command
    command = ""
    if text and text.startswith("/"):
        command = text.split()[0].split("@")[0].lower()

    # ── Map / Location logic ────────────────────────────────────
    if location:
        lat = location.get("latitude")
        lng = location.get("longitude")
        _update_user_state(chat_id, latitude=lat, longitude=lng)
        _send_bot_message(
            chat_id,
            "📍 <b>ទទួលបានទីតាំងជោគជ័យ!</b>\n"
            "ឥឡូវនេះអ្នកទិញអាចឃើញទីតាំងចម្ការរបស់អ្នកបានយ៉ាងងាយស្រួល។"
        )
        return

    # ── Command routing ─────────────────────────────────────────
    if command == "/start":
        handle_start(chat_id, user_state)
        return

    if command == "/location":
        _send_bot_message(
            chat_id,
            "📍 <b>របៀបកំណត់ទីតាំងចម្ការរបស់អ្នក</b>\n\n"
            "១. ចុចប៊ូតុង 📎 (Attachment)\n"
            "២. ជ្រើសរើស 📍 Location\n"
            "៣. ផ្ញើទីតាំងរបស់អ្នកមកកាន់ Bot ជាការស្រេច!"
        )
        return

    if command == "/sell":
        handle_sell(chat_id, text)
        return

    if command == "/market":
        handle_market(chat_id)
        return

    if command == "/view_catalog":
        handle_view_catalog(chat_id)
        return

    if command == "/weather":
        handle_weather(chat_id)
        return

    if command == "/buyers":
        handle_buyers(chat_id)
        return

    if command == "/addbuyer" and is_admin:
        handle_addbuyer(chat_id, text)
        return

    if command == "/broadcast" and is_admin:
        handle_broadcast(chat_id, text)
        return

    if command == "/pricealert" and is_admin:
        handle_pricealert(chat_id)
        return

    if command == "/price":
        handle_price(chat_id)
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

    if user_state.get("state", STATE_START) != STATE_START:
        _send_bot_message(
            chat_id,
            "⚠️ <b>លោកអ្នកកំពុងស្ថិតក្នុងដំណើរការផ្សេង!</b>\n"
            "សូមបំពេញដំណើរការនោះឱ្យចប់សិន។"
        )
        return


    elif state == STATE_IDLE:
        _send_bot_message(
            chat_id,
            "✅ <b>អ្នកបានចុះឈ្មោះហើយ!</b>\n"
            "<code>━━━━━━━━━━━━━━━━</code>\n"
            "📦 <code>/view_catalog</code> — មើលផលិតផល\n"
            "📊 <code>/price</code> — តម្លៃទីផ្សារភ្នំពេញ\n"
            "🛒 <code>/market</code> — ទីផ្សារលក់រាយ\n"
            "🤝 <code>/buyers</code> — បញ្ជីអ្នកទិញ\n"
            "🌤️ <code>/weather</code> — អាកាសធាតុ\n"
            "📍 <code>/location</code> — ផ្ញើទីតាំងចម្ការរបស់អ្នក",
        )

    else:  # STATE_START or unknown
        _send_bot_message(
            chat_id,
            "👋 ប្រើ <code>/start</code> ដើម្បីចុះឈ្មោះ!",
        )


def handle_callback_query(callback_query: dict) -> None:
    try:
        data = callback_query.get("data")
        message = callback_query.get("message")
        if not data or not message:
            return
            
        chat_id = message["chat"]["id"]
        
        if data.startswith("crop_"):
            crop_id = int(data.split("_")[1])
            crop = get_crop_by_id(crop_id, _get_db_connection, _ensure_db_ready)
            if crop:
                raw_name = crop.get('crop_name') or 'មិនមាន'
                c_name = escape(_translate_to_khmer(str(raw_name)))
                c_cat  = escape(_translate_to_khmer(str(crop.get('category') or 'មិនមាន')))
                
                raw_unit = str(crop.get('unit') or 'មិនមាន')
                kh_unit = _translate_to_khmer(raw_unit)
                if raw_name == "Damaged Rice":
                    kh_unit = "គីឡូក្រាម"
                c_unit = escape(kh_unit)
                
                # Default information if DB is empty
                default_info = {
                    "Corn": {"desc": "ពោតក្រហមគ្រាប់ធំៗល្អ សាកសមសម្រាប់ផលិតចំណីសត្វ", "qual": "សំណើម < ១៤%, គ្រាប់បែកខូច < ៥%"},
                    "Cucumber": {"desc": "ម្ទេសស្រស់ល្អ មិនទាន់ទុំពេកសាកសមសម្រាប់ការនាំចេញ", "qual": "ទំហំស្តង់ដារ មិនមានស្នាម ឬសត្វល្អិត"},
                    "Damaged Rice": {"desc": "ឪឡឹកផ្អែម សំបកក្រាស់ ល្អសម្រាប់ការទុកដាក់យូរ", "qual": "ទម្ងន់ចាប់ពី ២គីឡូឡើងទៅ គ្មានស្នាមប្រេះ"},
                    "Mango": {"desc": "ស្វាយកែវរមៀតសាច់ក្រាស់ ល្អសម្រាប់ការនាំចេញ និងកែច្នៃ", "qual": "ផ្លែចាស់ល្អ ទំហំចាប់ពី ៣០០ក្រាមឡើងទៅ"},
                    "Rice": {"desc": "អង្ករផ្កាម្លិះលេខ១ គ្រាប់វែង ពេលដាំមានក្លិនក្រអូប", "qual": "គ្រាប់បែក < ៥%, មិនមានកម្ទេចកម្ទីឡើយ"}
                }
                
                db_desc = crop.get('description')
                db_qual = crop.get('quality_standards')
                
                c_desc = db_desc if db_desc else default_info.get(raw_name, {}).get("desc", "មិនមាន")
                c_qual = db_qual if db_qual else default_info.get(raw_name, {}).get("qual", "មិនមាន")
                
                c_desc = escape(str(c_desc))
                c_qual = escape(str(c_qual))
                
                msg = (
                    f"📦 <b>ព័ត៌មានលម្អិត: {c_name}</b>\n"
                    "<code>━━━━━━━━━━━━━━━━━━━━━━</code>\n"
                    f"📋 <b>ប្រភេទ:</b> {c_cat}\n"
                    f"⚖️ <b>ឯកតា:</b> {c_unit}\n\n"
                    f"📝 <b>ការពិពណ៌នា:</b>\n{c_desc}\n\n"
                    f"⭐ <b>ស្តង់ដារគុណភាព:</b>\n{c_qual}"
                )
                _send_bot_message(chat_id, msg)
                
                # Answer callback query to remove loading state on button
                try:
                    if _bot:
                        _bot.answer_callback_query(callback_query["id"])
                except Exception:
                    pass
            else:
                _send_bot_message(chat_id, "⚠️ មិនមានទិន្នន័យសម្រាប់កសិផលនេះទេ។")
    except Exception:
        logger.exception("message_handler: Error in handle_callback_query")
