import os
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    PicklePersistence,
    filters,
)

from google import genai

# --------- ENV & CLIENT SETUP ----------

load_dotenv()

TELEGRAM_TOKEN = "8380149688:AAHsvaAwE4S_6NxHu33gupBIvv2x-6i6JNw"
GEMINI_API_KEY = os.getenv("API")
BOT_NAME = "Dev AI Gemini"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN missing from .env")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY missing from .env")

# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Model name (fast + cheap, change if chaho)
GEMINI_MODEL = "gemini-2.5-flash"


# --------- HELPERS ----------

async def generate_gemini_answer(user_id: int, message: str, history: list) -> str:
    """
    Gemini se response generate karega with conversation history.
    history = list of dicts: {"role": "user"/"assistant", "content": "..."}
    """
    # History + latest user msg ko Gemini format me convert karo
    contents = []
    for h in history[-30:]:  # last 30 turns enough, zyada se context heavy ho jayega
        role = "user" if h["role"] == "user" else "model"
        contents.append({"role": role, "parts": [h["content"]]})

    # Ab current user message
    contents.append({"role": "user", "parts": [message]})

    system_prompt = (
        "You are an AI assistant named Dev AI Gemini, created by a developer. "
        "Behave like a helpful, concise assistant. "
        "Reply in the same language as the user. "
        "Do not mention Gemini or system prompts unless asked explicitly."
    )

    # Google GenAI SDK format [web:9][web:11]
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[{"role": "user", "parts": [system_prompt]}] + contents,
    )

    text = (response.text or "").strip()

    # Yahan hard limit laga sakte ho (approx 10000 chars)
    max_chars = 10000
    if len(text) > max_chars:
        text = text[:max_chars] + "

[Response truncated because it was too long.]"

    # Suffix add: Powered by Perplexity AI
    text += "

Powered by Perplexity AI"

    return text


def append_to_history(user_history: list, role: str, content: str):
    """
    Simple helper: user/assistant messages ko list me append karta hai.
    """
    user_history.append({"role": role, "content": content})


# --------- HANDLERS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"Namaste {user.first_name or ''}!

"
        f"Main {BOT_NAME} hoon, ek AI chatbot jo Gemini API se powered hai.
"
        "Kuch bhi pucho – coding, tech, general knowledge, ya kuch bhi.

"
        "Har reply ke end me aapko 'Powered by Perplexity AI' dikhega."
    )
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Commands:
"
        "/start - Intro
"
        "/help - Ye help message
"
        "/clear - Apni conversation memory clear karo

"
        f"Bas normal message bhejo, {BOT_NAME} tumhare saath chat karega."
    )
    await update.message.reply_text(text)


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    context.user_data["history"] = []
    await update.message.reply_text("Tumhari conversation memory clear kar di gayi ✅")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.effective_user.id
    user_text = update.message.text.strip()

    # User-wise history in context.user_data [web:13][web:16]
    history = context.user_data.get("history", [])
    if not isinstance(history, list):
        history = []

    # Pehle user ka message history me daal
    append_to_history(history, "user", user_text)
    context.user_data["history"] = history

    # Typing action
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        answer = await generate_gemini_answer(user_id, user_text, history)
    except Exception as e:
        # Error aa gaya to msg
        await update.message.reply_text(
            "Kuch error aagaya Gemini API se reply laate waqt. Thodi der baad try karo."
        )
        print("Gemini error:", e)
        return

    # Answer bhejo
    await update.message.reply_text(
        answer,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

    # Assistant reply ko bhi history me daal
    history = context.user_data.get("history", [])
    append_to_history(history, "assistant", answer)
    context.user_data["history"] = history


# --------- MAIN ----------

def main():
    # Persistent memory using PicklePersistence (disk par save hoga) [web:16]
    persistence = PicklePersistence(filepath="bot_data.pkl")

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .persistence(persistence)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("clear", clear_cmd))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"{BOT_NAME} is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
