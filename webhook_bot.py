import os
import telebot
from flask import Flask, request
from dotenv import load_dotenv

# -------------------------------------------------------------
# ការកំណត់ប្រព័ន្ធសុវត្ថិភាព និង ទាញយក Token
# -------------------------------------------------------------
# load_dotenv() នឹងស្វែងរក File .env ដែលនៅទីតាំងជាមួយវាដោយស្វ័យប្រវត្តិ
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

app = Flask(__name__)
bot = telebot.TeleBot(BOT_TOKEN)

# -------------------------------------------------------------
# ១. កូដបញ្ជា /start និងការរៀបចំប៊ូតុងភាសាខ្មែរ (Task #7)
# -------------------------------------------------------------
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_name = message.from_user.first_name
    welcome_text = f"សួស្តី {user_name}! សូមស្វាគមន៍មកកាន់ Agri-Trade Bot\nសូមជ្រើសរើសសេវាកម្មខាងក្រោម៖"
    
    # បង្កើតប៊ូតុង Keyboard ទាំង ៤
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_rice = telebot.types.KeyboardButton('🌾 តម្លៃស្រូវ')
    btn_pepper = telebot.types.KeyboardButton('🌶️ តម្លៃម្រេច')
    btn_trends = telebot.types.KeyboardButton('📈 ទីផ្សារ')
    btn_contact = telebot.types.KeyboardButton('📞 ទំនាក់ទំនង')
    
    markup.add(btn_rice, btn_pepper, btn_trends, btn_contact)
    
    bot.reply_to(message, welcome_text, reply_markup=markup)

# -------------------------------------------------------------
# ២. ប្រព័ន្ធ Webhook សម្រាប់ទទួលសារពី Telegram ដោយស្វ័យប្រវត្តិ
# -------------------------------------------------------------
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    # ទទួលទិន្នន័យពី Telegram រួចបញ្ជូនទៅឱ្យ Bot ឆ្លើយតប
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# -------------------------------------------------------------
# ៣. កន្លែងបញ្ឆេះប្រព័ន្ធ Webhook ឱ្យរត់ ២៤ ម៉ោង
# -------------------------------------------------------------
@app.route("/")
def webhook():
    bot.remove_webhook()
    
    # បានបញ្ចូលឈ្មោះគណនី Nannfranco រួចរាល់!
    username = "Nannfranco" 
    webhook_url = f"https://{username}.pythonanywhere.com/{BOT_TOKEN}"
    
    bot.set_webhook(url=webhook_url)
    return "Webhook is setup successfully! Bot is running 24/7 securely.", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))