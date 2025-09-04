import telebot
import os
import logging
from telebot import types
import google.generativeai as genai
from firebase_admin import credentials, initialize_app, firestore
import firebase_admin
from firebase_admin import db as firebase_db
from firebase_admin import auth
import random
import string
import json

# Setup logging for the application
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# load environment variables. These will be set on Render.
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Define the Gemini model URL for text and image
API_URL_TEXT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
API_URL_IMAGE = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent"

def escape_markdown_v2(text):
    """
    Escapes special characters in a string for use with Telegram's markdownV2.
    """
    escape_chars = '_*[]()~`>#+-=|{}.!'
    return ''.join('\\' + char if char in escape_chars else char for char in text)

# Firebase Setup
# The following variables are provided by the Canvas environment.
# They are essential for connecting to your Firebase project.
app_id = os.environ.get('__app_id') if '__app_id' in os.environ else 'default-app-id'
firebase_config = json.loads(os.environ.get('__firebase_config') if '__firebase_config' in os.environ else '{}')
initial_auth_token = os.environ.get('__initial_auth_token') if '__initial_auth_token' in os.environ else None

# Initialize Firebase app and firestore database
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_config)
    firebase_app = initialize_app(cred)
db = firestore.client()

# Initialize the bot
bot = telebot.TeleBot(BOT_TOKEN)

# Set up webhook
bot.set_webhook(url=WEBHOOK_URL)

def run_auth():
    """
    Sign in the user with the custom auth token provided by Canvas.
    """
    try:
        if initial_auth_token:
            auth.sign_in_with_custom_token(initial_auth_token)
        else:
            auth.sign_in_anonymously()
    except Exception as e:
        print(f"Error during authentication: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        user_id = auth.current_user['uid'] if auth.current_user else ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        btn1 = types.KeyboardButton('Image Generation')
        btn2 = types.KeyboardButton('Text Generation')
        markup.add(btn1, btn2)
        bot.reply_to(message, "Hello! I am a Gemini-powered Telegram Bot. I can generate text and images for you.", reply_markup=markup)
        bot.reply_to(message, f"Your user ID is: `{user_id}`")
    except Exception as e:
        logging.error(f"Error in /start command: {e}")
        bot.reply_to(message, "Sorry, something went wrong. Please try again.")

@bot.message_handler(func=lambda message: message.text == "Text Generation")
def text_generation_mode(message):
    try:
        bot.reply_to(message, "You've selected Text Generation. Please send me a prompt.")
        bot.register_next_step_handler(message, process_text_generation_prompt)
    except Exception as e:
        logging.error(f"Error in Text Generation command: {e}")

def process_text_generation_prompt(message):
    try:
        prompt = message.text
        bot.reply_to(message, "Generating response, please wait...")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
            "systemInstruction": {
                "parts": [{"text": "You are a helpful and creative AI assistant."}]
            }
        }
        
        headers = {
            'Content-Type': 'application/json'
        }
        
        api_url = f"{API_URL_TEXT}?key={API_KEY}"
        
        import requests
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        candidate = result.get('candidates', [{}])[0]
        generated_text = candidate.get('content', {}).get('parts', [{}])[0].get('text', "Sorry, I couldn't generate a response.")
        
        bot.reply_to(message, generated_text)

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Gemini API: {e}")
        bot.reply_to(message, "Sorry, I am unable to connect to the Gemini API right now. Please try again later.")
    except Exception as e:
        logging.error(f"Error processing text generation prompt: {e}")
        bot.reply_to(message, "Sorry, something went wrong. Please try again.")

@bot.message_handler(func=lambda message: message.text == "Image Generation")
def image_generation_mode(message):
    try:
        bot.reply_to(message, "You've selected Image Generation. Please send me a prompt to generate an image.")
        bot.register_next_step_handler(message, process_image_generation_prompt)
    except Exception as e:
        logging.error(f"Error in Image Generation command: {e}")

def process_image_generation_prompt(message):
    try:
        prompt = message.text
        bot.reply_to(message, "Generating image, please wait...")
        payload = {
            "contents": [{
                "parts": [{ "text": prompt }]
            }],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"]
            },
        }

        headers = {
            'Content-Type': 'application/json'
        }
        
        api_url = f"{API_URL_IMAGE}?key={API_KEY}"

        import requests
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()

        result = response.json()
        base64_data = result['candidates'][0]['content']['parts'][0]['inlineData']['data']
        
        import base64
        image_bytes = base64.b64decode(base64_data)
        bot.send_photo(message.chat.id, photo=image_bytes)

    except requests.exceptions.RequestException as e:
        logging.error(f"Error calling Gemini API: {e}")
        bot.reply_to(message, "Sorry, I am unable to connect to the Gemini API for image generation right now. Please try again later.")
    except Exception as e:
        logging.error(f"Error processing image generation prompt: {e}")
        bot.reply_to(message, "Sorry, something went wrong. Please try again.")

def main():
    run_auth()
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Error in bot polling: {e}")

if __name__ == '__main__':
    main()
