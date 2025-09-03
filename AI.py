import os
import asyncio
import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import logging
import json

# Set up logging for the application
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Load environment variables. These will be set on Render.
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_KEY = os.getenv("GEMINI_API_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Define the Gemini model URL
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"

async def generate_response(prompt: str) -> str:
    """
    Sends a prompt to the Gemini API and returns the AI's response.
    This includes the Google Search tool for grounded responses.
    """
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "systemInstruction": {
            "parts": [{
                "text": "You are a world-class math and science expert. You specialize in explaining complex concepts and solving equations. Respond directly and clearly to the user's question. If the user asks a question not related to math or science, politely decline and state you can only help with math and science."
            }]
        },
    }
    params = {"key": API_KEY}
    
    # Use exponential backoff for retries
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(API_URL, json=payload, headers=headers, params=params, timeout=30.0)
                response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            
            # Parse the response and extract the text
            result = response.json()
            candidate = result.get("candidates", [])[0]
            text = candidate.get("content", {}).get("parts", [])[0].get("text")
            
            # Extract citations for grounded responses
            sources_text = ""
            grounding_metadata = candidate.get("groundingMetadata", {})
            if grounding_metadata and grounding_metadata.get("groundingAttributions"):
                sources_list = []
                for attribution in grounding_metadata["groundingAttributions"]:
                    web = attribution.get("web")
                    if web and web.get("title") and web.get("uri"):
                        sources_list.append(f"[{web['title']}]({web['uri']})")
                if sources_list:
                    sources_text = "\n\n**Sources:**\n" + "\n".join(sources_list)
            
            return text + sources_text

        except httpx.HTTPStatusError as e:
            logging.error(f"HTTP error on attempt {attempt + 1}/{max_retries}: {e}")
            if e.response.status_code == 429 and attempt < max_retries - 1:
                # Exponential backoff for rate limits
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
    await update.message.reply_text("Hello! I am a math and science bot. Ask me a math question and I'll do my best to solve it for you!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles user messages and sends them to the Gemini API."""
    user_text = update.message.text
    logging.info(f"Received message: {user_text}")
    
    await update.message.reply_text("Thinking...")
    
    # Get the AI's response to the user's message
    response_text = await generate_response(user_text)
    
    # Send the response back to the user
    await update.message.reply_markdown_v2(
        response_text.replace('-', '\\-').replace('.', '\\.').replace('!', '\\!').replace('(', '\\(').replace(')', '\\)').replace('`', '\\`')
    )

def main():
    """Starts the bot using a webhook."""
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Set up the webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
