# bot.py
import os
import logging
from telegram import Update, MessageEntity
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from google import genai

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ENV
TELEGRAM_TOKEN = "8380149688:AAHsvaAwE4S_6NxHu33gupBIvv2x-6i6JNw"
GEMINI_API_KEY = os.getenv("API")
MODEL = "gemini-1.5-flash"

if not TELEGRAM_TOKEN:
    raise RuntimeError("Missing TELEGRAM_TOKEN")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY")

# Gemini Client
client = genai.Client(api_key=GEMINI_API_KEY)
agen = client.aio

LAST_RESPONSES = {}


# --- Helpers ---
def mention_html(user):
    if user.username:
        return f"@{user.username}"
    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"


async def gemini_answer(prompt: str):
    """Call Gemini API"""
    try:
        res = await agen.models.generate_content(
            model=MODEL,
            contents=prompt,
        )
        if hasattr(res, "text"):
            return res.text.strip()

        return "\n".join([p.text for p in res.parts]).strip()

    except Exception as e:
        logger.error(e)
        return f"⚠️ Gemini Error: {e}"


async def send_thinking_and_edit(chat_id, mention, prompt, ctx):
    """Send thinking… message -> edit with Gemini answer"""
    msg = await ctx.bot.send_message(chat_id, "thinking... 💭")

    answer = await gemini_answer(prompt)

    if mention:
        answer = f"{mention}\n\n{answer}"

    await ctx.bot.edit_message_text(
        chat_id=chat_id,
        message_id=msg.message_id,
        text=answer,
        parse_mode=ParseMode.HTML,
    )

    return answer


# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! DM me anything.\n"
        "In groups, mention me to get an answer."
    )


# --- Private chat ---
async def private_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = msg.text or ""

    LAST_RESPONSES[msg.chat_id] = {"prompt": text}

    await context.bot.send_chat_action(msg.chat_id, ChatAction.TYPING)

    await send_thinking_and_edit(msg.chat_id, "", text, context)


# --- Group logic ---
async def group_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = msg.text or ""
    bot_username = context.bot.username
    chat_id = msg.chat_id

    mention = False

    # Detect @botname mention
    if msg.entities:
        for e in msg.entities:
            if e.type == MessageEntity.MENTION:
                part = text[e.offset: e.offset + e.length]
                if part == f"@{bot_username}":
                    mention = True

    # Detect replying to bot
    reply_to_bot = (
        msg.reply_to_message
        and msg.reply_to_message.from_user
        and msg.reply_to_message.from_user.is_bot
    )

    if not (mention or reply_to_bot):
        return

    # Clean bot name from text
    clean = text.replace(f"@{bot_username}", "").strip()

    # If empty, take replied text
    if not clean and msg.reply_to_message:
        clean = msg.reply_to_message.text or ""

    if not clean:
        await msg.reply_text("Ask something 🙂")
        return

    m = mention_html(update.effective_user)

    LAST_RESPONSES[chat_id] = {"prompt": clean}

    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    await send_thinking_and_edit(chat_id, m, clean, context)


# --- Callback (regen) ---
async def regen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    chat_id = q.message.chat_id
    last = LAST_RESPONSES.get(chat_id)

    if not last:
        await q.edit_message_text("No previous prompt.")
        return

    prompt = last["prompt"]
    m = "" if q.message.chat.type == "private" else mention_html(q.from_user)

    await send_thinking_and_edit(chat_id, m, prompt, context)


# --- Router ---
async def msg_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await private_msg(update, context)
    else:
        await group_msg(update, context)


# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(regen, pattern="^regen$"))
    app.add_handler(MessageHandler(filters.TEXT, msg_router))

    print("Bot running in polling mode…")
    app.run_polling()


if __name__ == "__main__":
    main()
