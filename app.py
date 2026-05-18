import os
import telebot
from flask import Flask, request

# ១. កំណត់លេខ Token ផ្លូវការរបស់ Farmers_Market_Bot
BOT_TOKEN = "8739297491:AAH_N0XN3Nid882olr-kd8K54FvzAFuMAig"
bot = telebot.TeleBot(BOT_TOKEN)

app = Flask(__name__)

# ២. ទ្វារទទួលសារ POST ពី Telegram ចំទំព័រដើម '/' របស់ Render
@app.route('/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        
        # បញ្ជូនសារទៅឱ្យ Handler ដំណើរការឆ្លើយតបភ្លាមៗ
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Forbidden', 403

# ៣. កូដឆ្លើយតបសារផ្លូវការនៅពេលកសិករ ឬអ្នកប្រើប្រាស់ចុច /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "👋 សួស្តី Koemnan! ស្វាគមន៍មកកាន់ប្រព័ន្ធតេស្តបូតផ្លូវការរបស់ Immortal Digital!\n\n"
        "🤖 បូតនេះកំពុងដំណើរការ ២Display ម៉ោង យ៉ាងមានលំនឹងនៅលើ Render.com តាមរយៈ Webhook រួចរាល់ហើយបាទ! 🌾"
    )
    bot.reply_to(message, welcome_text)

# ៤. ទំព័រសម្រាប់ឆែកមើលស្ថានភាពនៅលើ Web Browser (GET)
@app.route('/', methods=['GET'])
def index():
    return "<h1>🌾 Farmers Market Bot Server is Real and Running on Render!</h1>", 200

if __name__ == "__main__":
    # Render តម្រូវឱ្យចាប់យក Port តាមរយះ Environment Variable (Port: 10000)
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)