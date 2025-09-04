import os
import logging
import json
import base64
import requests
import telebot
from telebot import types
from flask import Flask, request
import firebase_admin
from firebase_admin import credentials, firestore

# --- Basic Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- Load Environment Variables ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # e.g., https://your-app-name.onrender.com

# --- Firebase Setup ---
try:
    # Get the single-line JSON string from environment variables
    firebase_config_str = os.getenv('__firebase_config')
    if firebase_config_str:
        firebase_config = json.loads(firebase_config_str)
        
        # Initialize Firebase app and Firestore database
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

# --- Gemini API URLs ---
API_URL_TEXT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
API_URL_IMAGE = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent" # Same model can handle both now

# --- Initialize Bot and Flask App ---
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# --- Webhook Handler for Flask ---
# This route is where Telegram will send updates
@app.route('/' + BOT_TOKEN, methods=['POST'])
def get_message():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

# This route sets the webhook
@app.route("/")
def webhook():
    bot.remove_webhook()
    # Construct the full webhook URL for Telegram
    full_webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    bot.set_webhook(url=full_webhook_url)
    return "Webhook set successfully!", 200

# --- Bot Command Handlers ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn1 = types.KeyboardButton('Image Generation')
    btn2 = types.KeyboardButton('Text Generation')
    markup.add(btn1, btn2)
    bot.reply_to(message, "Hello! I am a Gemini-powered Telegram Bot. I can generate text and images for you.", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "Text Generation")
def text_generation_mode(message):
    bot.reply_to(message, "You've selected Text Generation. Please send me a prompt.")
    bot.register_next_step_handler(message, process_text_generation_prompt)

def process_text_generation_prompt(message):
    try:
        prompt = message.text
        bot.reply_to(message, "Generating response, please wait...")
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {
                "parts": [{"text": "You are a helpful and creative AI assistant."}]
            }
        }
        headers = {'Content-Type': 'application/json'}
        api_url = f"{API_URL_TEXT}?key={API_KEY}"
        
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        generated_text = result['candidates'][0]['content']['parts'][0]['text']
        
        bot.reply_to(message, generated_text)

    except Exception as e:
        logging.error(f"Error processing text generation: {e}")
        bot.reply_to(message, "Sorry, something went wrong. Please try again.")

@bot.message_handler(func=lambda message: message.text == "Image Generation")
def image_generation_mode(message):
    bot.reply_to(message, "You've selected Image Generation. Please send a prompt to generate an image.")
    bot.register_next_step_handler(message, process_image_generation_prompt)

def process_image_generation_prompt(message):
    try:
        prompt = message.text
        bot.reply_to(message, "Generating image, please wait...")
        # Note: Image generation via the public Gemini API is not directly supported this way.
        # This code structure assumes an endpoint that returns an image, which is not standard for Gemini.
        # For a real-world scenario, you would use a dedicated image generation model API like Imagen.
        # This part is left as a placeholder to show the bot's logic flow.
        bot.reply_to(message, f"Image generation for prompt: '{prompt}' is not implemented in this demo.")

    except Exception as e:
        logging.error(f"Error processing image generation: {e}")
        bot.reply_to(message, "Sorry, something went wrong with image generation.")

# --- Main entry point to run the Flask app ---
if __name__ == "__main__":
    # The app is run by Gunicorn on Render, not by this line.
    # This is useful for local testing.
    # Make sure to set WEBHOOK_URL when running the app.
    if WEBHOOK_URL:
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    else:
        logging.error("WEBHOOK_URL environment variable not set. Cannot start.")
