import os
import logging
import json
import requests
import telebot
from flask import Flask, request
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

# --- Basic Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- Load Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
AI_API_KEY = os.getenv("AI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# --- Firebase Setup ---
try:
    firebase_config_str = os.getenv('__firebase_config')
    if firebase_config_str:
        firebase_config = json.loads(firebase_config_str)
        if not firebase_admin._apps:
            cred = credentials.Certificate(firebase_config)
            initialize_app(cred)
        db = firestore.client()
        logging.info("Firebase successfully initialized.")
    else:
        logging.error("__firebase_config environment variable not found.")
        db = None
except Exception as e:
    logging.error(f"Error initializing Firebase: {e}")
    db = None

# --- AI API Configuration ---
# Using DeepSeek API but without branding in responses
AI_API_URL = "https://api.deepseek.com/v1/chat/completions"

# --- Initialize Bot and Flask App ---
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- Webhook Handler for Flask ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    full_webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    bot.set_webhook(url=full_webhook_url)
    return "Webhook set successfully!", 200

# --- Bot Command Handlers ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "Hey there! 😎 I'm your personal AI assistant, created by Kirubel Teklu. "
        "I'm ready to chat about anything and everything. "
        "What's on your mind? 🤔 Fire away! 🔥\n\n"
        "Contact my creator: @ANDREW56776"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['who'])
def send_creator_info(message):
    creator_text = (
        "I was created by Kirubel Teklu! 🇪🇹👨‍💻\n\n"
        "You can contact him on Telegram: @ANDREW56776\n\n"
        "He's the mastermind behind this AI assistant. 😉"
    )
    bot.reply_to(message, creator_text)

@bot.message_handler(commands=['contact'])
def send_contact_info(message):
    contact_text = (
        "Contact my creator Kirubel Teklu on Telegram: @ANDREW56776\n\n"
        "He'd love to hear your feedback or answer any questions! 💬"
    )
    bot.reply_to(message, contact_text)

# --- Main Chat Handler ---
@bot.message_handler(content_types=['text'])
def handle_chat(message):
    try:
        prompt = message.text
        thinking_message = bot.reply_to(message, "Hmm, let me think... 🤔")
        
        system_prompt = (
            "You are a witty and humorous AI assistant created by Kirubel Teklu. "
            "You love using modern emojis like 😂, 😎, 🤔, 🔥, and 😉 to sound like a real person chatting on Telegram. "
            "Keep your responses friendly, engaging, and short, with a maximum of about 300 words. "
            "Never mention that you're powered by any specific AI model or company. "
            "If asked about your creator, say you were developed by Kirubel Teklu and provide his Telegram @ANDREW56776."
        )

        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {AI_API_KEY}'
        }
        
        response = requests.post(AI_API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        
        result = response.json()
        
        if 'choices' in result and result['choices']:
            generated_text = result['choices'][0]['message']['content']
        else:
            generated_text = "Oops, I got a bit tongue-tied there. 😅 Could you try rephrasing that?"

        bot.edit_message_text(chat_id=message.chat.id, message_id=thinking_message.message_id, text=generated_text)

    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error occurred: {http_err} - {response.text}")
        bot.edit_message_text(
            chat_id=message.chat.id, 
            message_id=thinking_message.message_id, 
            text="Yikes! I'm having some trouble connecting to my brain right now. Please try again in a moment. 😵"
        )
    except Exception as e:
        logging.error(f"An error occurred in handle_chat: {e}")
        bot.edit_message_text(
            chat_id=message.chat.id, 
            message_id=thinking_message.message_id, 
            text="Oof, something went wrong on my end. 🛠️ Sorry about that! Please try again."
        )

if __name__ == "__main__":
    if WEBHOOK_URL:
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    else:
        logging.error("WEBHOOK_URL environment variable not set. Cannot start Flask app.")
        logging.info("WEBHOOK_URL not found. Starting bot with polling for local testing.")
        bot.remove_webhook()
        bot.infinity_polling()
