
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

# --- Gemini API URL ---
# Using gemini-1.5-flash which is great for chat
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

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
    """
    Sends a cool and engaging welcome message when the user starts a chat.
    """
    welcome_text = (
        "Hey there! 😎 I'm your personal pocket AGI, ready to chat about anything and everything. "
        "What's on your mind? 🤔 Fire away! 🔥"
    )
    bot.reply_to(message, welcome_text)

@bot.message_handler(commands=['who'])
def send_creator_info(message):
    """
    Responds with information about the bot's creator.
    """
    creator_text = (
        "I was brought to life by a brilliant Ethiopian developer named Edym! 🇪🇹👨‍💻\n\n"
        "You can find him on Telegram at @ANDREW56776. He's the mastermind behind this little AGI. 😉"
    )
    bot.reply_to(message, creator_text)

# --- Main Chat Handler ---

@bot.message_handler(content_types=['text'])
def handle_chat(message):
    """
    This handler catches all text messages that aren't commands and processes them.
    """
    try:
        prompt = message.text
        # Let the user know we're thinking 🤔
        thinking_message = bot.reply_to(message, "Hmm, let me think... 🤔")
        
        # This system instruction is key to the bot's personality
        system_instruction = (
            "You are a witty and humorous AI assistant that calls itself 'a little AGI'. "
            "You love using modern emojis like 😂, 😎, 🤔, 🔥, and 😉 to sound like a real person chatting on Telegram. "
            "Keep your responses friendly, engaging, and short, with a maximum of about 300 words."
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            }
        }
        headers = {'Content-Type': 'application/json'}
        api_url_with_key = f"{API_URL}?key={API_KEY}"
        
        response = requests.post(api_url_with_key, json=payload, headers=headers, timeout=60)
        response.raise_for_status() # Raises an error for bad status codes (4xx or 5xx)
        
        result = response.json()
        
        # Safely get the generated text
        if 'candidates' in result and result['candidates']:
            generated_text = result['candidates'][0]['content']['parts'][0]['text']
        else:
            # Handle cases where the API returns no candidates (e.g., safety blocks)
            generated_text = "Oops, I got a bit tongue-tied there. 😅 Could you try rephrasing that?"

        # Edit the "thinking..." message to show the final response
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


# --- Main entry point to run the Flask app ---
if __name__ == "__main__":
    # This part is useful for local testing. 
    # On a platform like Render, Gunicorn or another WSGI server runs the 'app' object.
    if WEBHOOK_URL:
        # For local testing, you might need to use a tool like ngrok to create a public URL
        # and set it as your WEBHOOK_URL environment variable.
        app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
    else:
        logging.error("WEBHOOK_URL environment variable not set. Cannot start Flask app.")
        # Fallback to polling for local development without a webhook
        logging.info("WEBHOOK_URL not found. Starting bot with polling for local testing.")
        bot.remove_webhook()
        bot.infinity_polling()
