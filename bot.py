import os
import asyncio
import logging

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatAction,
    MessageEntity,
    ParseMode,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# Gemini SDK (OFFICIAL)
from google import genai
from google.genai import types

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ------------ ENV VARS ------------
TELEGRAM_TOKEN = "8380149688:AAHsvaAwE4S_6NxHu33gupBIvv2x-6i6JNw"
GEMINI_API_KEY = os.getenv("API")
MODEL = "gemini-2.5-flash"

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN required")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY required")

# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)
agen = client.aio

LAST_RESPONSES = {}

# ------------ HELPERS ------------
def mention_html(user):
    if user.username:
        return f"@{user.username}"
    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

async def call_gemini(prompt: str):
    try:
        res = await agen.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=500
            )
        )
        if hasattr(res, "text") and res.text:
            return res.text.strip()

        # fallback
        parts = []
        for p in getattr(res, "parts", []) or []:
            if p.text:
                parts.append(p.text)
        return "\n".join(parts).strip()

    except Exception as e:
        logger.exception("Gemini error")
        return f"⚠️ Gemini Error: {e}"

# ------------ THINKING + EDIT ANSWER ------------
async def send_and_edit(chat_id, mention, prompt, context):
    sent = await context.bot.send_message(chat_id, "thinking... 💭")

    answer = await call_gemini(prompt)

    if mention:
        answer = f"{mention}\n\n{answer}"

    await context.bot.edit_message_text(
        chat_id=chat_id,
        message_id=sent.message_id,
        text=answer,
        parse_mode=ParseMode.HTML
    )

    return answer

# ------------ COMMAND HANDLERS ------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hey! 😊\n"
        "DM me anything & I’ll answer.\n"
        "In groups, mention me to get a reply."
    )

# ------------ PRIVATE CHAT ------------
async def private_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    prompt = msg.text or ""
    chat_id = msg.chat_id

    LAST_RESPONSES[chat_id] = {"prompt": prompt}

    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    await send_and_edit(chat_id, "", prompt, context)

# ------------ GROUP LOGIC ------------
async def group_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = msg.text or ""
    chat_id = msg.chat_id
    bot_username = context.bot.username

    mention_found = False
    if msg.entities:
        for e in msg.entities:
            if e.type in [MessageEntity.MENTION, MessageEntity.TEXT_MENTION]:
                ent = text[e.offset: e.offset + e.length]
                if f"@{bot_username}" in ent:
                    mention_found = True

    reply_to_bot = False
    if msg.reply_to_message:
        if msg.reply_to_message.from_user and msg.reply_to_message.from_user.is_bot:
            reply_to_bot = True

    if not (mention_found or reply_to_bot):
        return  # ignore normal group msgs

    prompt = text.replace(f"@{bot_username}", "").strip()

    # if user only tagged bot without text, use replied message text
    if not prompt and msg.reply_to_message:
        prompt = msg.reply_to_message.text or ""

    if not prompt:
        await msg.reply_text("Ask something 😄")
        return

    user_ment = mention_html(update.effective_user)

    LAST_RESPONSES[chat_id] = {"prompt": prompt}

    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    await send_and_edit(chat_id, user_ment, prompt, context)

# ------------ REGENERATE BUTTON ------------
async def regen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id

    last = LAST_RESPONSES.get(chat_id)
    if not last:
        await q.edit_message_text("No previous message!")
        return

    prompt = last["prompt"]
    user_mention = "" if q.message.chat.type == "private" else mention_html(q.from_user)

    await send_and_edit(chat_id, user_mention, prompt, context)

# ------------ ROUTER ------------
async def message_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await private_msg(update, context)
    else:
        await group_msg(update, context)

# ------------ MAIN ------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(regen, pattern="^regen$"))
    app.add_handler(MessageHandler(filters.TEXT | filters.Caption, message_router))

    print("Bot running in polling mode…")
    app.run_polling()

if __name__ == "__main__":
    main()
