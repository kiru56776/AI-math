import os
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import json
import base64
from firebase_admin import credentials, firestore, initialize_app

# --- Firebase Setup ---
# The following variables are provided by the Canvas environment.
# They are essential for connecting to your Firebase project.
app_id = typeof __app_id !== 'undefined' ? __app_id : 'default-app-id'
firebase_config = json.loads(typeof __firebase_config !== 'undefined' ? __firebase_config : '{}')
initial_auth_token = typeof __initial_auth_token !== 'undefined' ? __initial_auth_token : ''

# Initialize Firebase app and Firestore database
cred = credentials.Certificate(firebase_config)
firebase_app = initialize_app(cred)
db = firestore.client()

# Set up logging for the application
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Load environment variables. These will be set on Render.
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Define the Gemini model URL for text and image
API_URL_TEXT = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
API_URL_IMAGE = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent"

def escape_markdown_v2(text):
    """
    Escapes special characters in a string for use with Telegram's MarkdownV2.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

async def get_chat_history(user_id: str):
    """
    Retrieves the chat history for a user from Firestore.
    """
    try:
        doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id)
        doc = await doc_ref.get()
        if doc.exists:
            return doc.to_dict().get('history', [])
        return []
    except Exception as e:
        logging.error(f"Error getting chat history: {e}")
        return []

async def save_chat_history(user_id: str, history: list):
    """
    Saves the updated chat history to Firestore.
    """
    try:
        doc_ref = db.collection('artifacts').document(app_id).collection('users').document(user_id)
        await doc_ref.set({'history': history}, merge=True)
    except Exception as e:
        logging.error(f"Error saving chat history: {e}")

async def generate_response(prompt: str, user_id: str, image_data: str = None) -> str:
    """
    Sends a prompt and chat history to the Gemini API and returns the response.
    Can also handle image input if provided.
    """
    # Get chat history from Firestore
    history = await get_chat_history(user_id)
    
    # Construct the content payload with the full conversation history
    contents = history + [{"role": "user", "parts": [{"text": prompt}]}]
    if image_data:
        contents[-1]["parts"].append({"inlineData": {"mimeType": "image/jpeg", "data": image_data}})
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": contents,
        "tools": [{"google_search": {}}],
        "systemInstruction": {
            "parts": [{
                "text": "You are a world-class math and science expert. You specialize in explaining complex concepts and solving equations. Respond directly and clearly to the user's question. If the user asks a question not related to math or science, politely decline and state you can only help with math and science."
            }]
        },
    }
    params = {"key": API_KEY}
    api_url = API_URL_IMAGE if image_data else API_URL_TEXT

    # Use exponential backoff for retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(api_url, json=payload, headers=headers, params=params, timeout=60.0)
                response.raise_for_status()

            # Parse the response and extract the text
            result = response.json()
            candidate = result.get("candidates", [])[0]
            text = candidate.get("content", {}).get("parts", [])[0].get("text")
            
            # Update chat history
            history.append({"role": "user", "parts": [{"text": prompt}]})
            history.append({"role": "model", "parts": [{"text": text}]})
            await save_chat_history(user_id, history)

            return text

        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error on attempt {attempt + 1}/{max_retries}: {e}")
            if e.response.status_code == 429 and attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return "I'm sorry, I encountered an error. Please try again later."
        except Exception as e:
            logging.error(f"An unexpected error occurred on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                return "I'm sorry, I couldn't process your request."

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text("Hello! I am a math and science bot. Ask me a math question and I'll do my best to solve it for you! Try `/help` to see what I can do.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /help command."""
    help_text = "I am your personal math and science tutor!\n\n"
    help_text += "You can ask me to solve equations, explain complex concepts, or even analyze a graph from an image.\n\n"
    help_text += "Just send me your question or an image of the problem. I'll do my best to help!"
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles user messages and sends them to the Gemini API."""
    user_text = update.message.text
    user_id = str(update.effective_user.id)
    logging.info(f"Received text message from {user_id}: {user_text}")
    
    await update.message.reply_text("Thinking...")
    
    response_text = await generate_response(user_text, user_id)
    
    await update.message.reply_markdown_v2(escape_markdown_v2(response_text))

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles image messages and sends them to the Gemini API."""
    file_id = update.message.photo[-1].file_id
    user_id = str(update.effective_user.id)
    logging.info(f"Received image message from {user_id}")

    # Get the file from Telegram
    file = await context.bot.get_file(file_id)
    
    # Download the file to an in-memory byte stream
    file_stream = await file.download_as_bytearray()
    
    # Encode the image data to base64
    image_base64 = base64.b64encode(file_stream).decode('utf-8')
    
    await update.message.reply_text("Thinking...")

    # A simple prompt to provide context for the image
    prompt = "Please analyze the following image and provide a detailed explanation of the math or science problem shown. Solve it if possible."
    response_text = await generate_response(prompt, user_id, image_base64)

    await update.message.reply_markdown_v2(escape_markdown_v2(response_text))

def main():
    """Starts the bot using a webhook."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers for different message types
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_image))

    # Set up the webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
