import os
import telebot
from flask import Flask, request
from telebot import types

# ១. បំពាក់លេខ Token ផ្លូវការរបស់អ្នក
BOT_TOKEN = "8716181670:AAGvxUPM6xzQl6NIWDfdfk_RCxgflIbXG2w"
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# ២. ទ្វារទទួលសារ POST ពី Telegram ចំទំព័រដើម '/' របស់ Render
@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Forbidden', 403

# ៣. កូដឆ្លើយតបសារនៅពេលកសិករ ឬអ្នកប្រើប្រាស់ចុច /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # ទាញយកឈ្មោះពិតរបស់អ្នកប្រើប្រាស់ពី Telegram Profile (ដោះស្រាយបញ្ហា NaN)
    user_name = message.from_user.first_name if message.from_user.first_name else "កសិករ"
    
    welcome_text = (
        f"👋 សួស្តី/ជម្រាបសួរ {user_name}! ស្វាគមន៍មកកាន់ប្រព័ន្ធ Agri-Trade Bot ផ្លូវការរបស់ Immortal Digital!\n\n"
        "សូមជ្រើសរើសសេវាកម្មផ្នែកខាងក្រោម៖"
    )
    
    # បង្កើតប៊ូតុងក្តារចុចខ្មែរ (Khmer Reply Keyboard Layout)
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_rice = types.KeyboardButton('🌾 តម្លៃស្រូវ')
    btn_pepper = types.KeyboardButton('🌶️ តម្លៃម្ទេស')
    btn_market = types.KeyboardButton('📈 ទីផ្សារ')
    btn_contact = types.KeyboardButton('📞 ទំនាក់ទំនង')
    
    # រៀបជួរដេកប៊ូតុង
    markup.add(btn_rice, btn_pepper)
    markup.add(btn_market, btn_contact)
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)

# ៤. កូដចាប់យកពាក្យបញ្ជាពីប៊ូតុងនីមួយៗ (Text Message Handler)
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    if message.text == '🌾 តម្លៃស្រូវ':
        bot.reply_to(message, "🌾 **តម្លៃស្រូវថ្ងៃនេះ៖**\n- ស្រូវក្រអូប (លេខ១)៖ 1,300 រៀល/គីឡូក្រាម\n- ស្រូវសចំប៉ា៖ 1,150 រៀល/គីឡូក្រាម")
    elif message.text == '🌶️ តម្លៃម្ទេស':
        bot.reply_to(message, "🌶️ **តម្លៃម្ទេសថ្ងៃនេះ៖**\n- ម្ទេសដៃនាង៖ 3,500 រៀល/គីឡូក្រាម\n- ម្ទេសអាចម៍សត្វ៖ 6,000 រៀល/គីឡូក្រាម")
    elif message.text == '📈 ទីផ្សារ':
        bot.reply_to(message, "📈 **របាយការណ៍ទីផ្សារ៖** ស្ថានភាពតម្លៃកសិផលសប្តាហ៍នេះមានលំនឹងល្អ មិនមានការប្រែប្រួលខ្លាំងឡើយ។")
    elif message.text == '📞 ទំនាក់ទំនង':
        bot.reply_to(message, "📞 **ក្រុមការងារ Immortal Digital៖**\nសហការ និងរាយការណ៍តម្លៃទូរសព្ទ៖ 012 345 678")

# ៥. ទំព័រសម្រាប់ឆែកមើលស្ថានភាពនៅលើ Web Browser (GET)
@app.route('/', methods=['GET'])
def index():
    return "<h1>🌾 Farmers Market Bot Server is Active and Running on Render!</h1>", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)