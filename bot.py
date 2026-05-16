import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

# 1. Load the secret token from the .env file securely
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# 2. Initialize the bot
bot = telebot.TeleBot(BOT_TOKEN)

# 3. Handle the /start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Get the user's first name automatically from Telegram
    user_name = message.from_user.first_name
    
    # Create the personalized Khmer Welcome Message
    welcome_text = f"សួស្តីពូ/មីង {user_name}! សូមស្វាគមន៍មកកាន់ Agri-Trade Bot។\nសូមជ្រើសរើសសេវាកម្មខាងក្រោម៖"
    
    # Create the custom keyboard with 4 buttons
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_rice = KeyboardButton('🌾 តម្លៃស្រូវ')
    btn_pepper = KeyboardButton('🌶️ តម្លៃម្រេច')
    btn_trends = KeyboardButton('📈 ទីផ្សារ')
    btn_contact = KeyboardButton('📞 ទំនាក់ទំនង')
    
    # Add the buttons to the keyboard layout
    markup.add(btn_rice, btn_pepper, btn_trends, btn_contact)
    
    # Send the message and display the buttons to the user
    bot.reply_to(message, welcome_text, reply_markup=markup)

# 4. Start the bot and keep it running
print("Bot is successfully running... Press Ctrl+C to stop.")
bot.infinity_polling()