import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID")

orchestrator = Orchestrator()
obsidian = ObsidianWriter()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    msg = (f"🧠 Cognitive OS Online.\n"
           f"Your User ID is: `{user_id}`\n\n"
           f"If this is your first time, please add this ID to `ALLOWED_TELEGRAM_USER_ID` in your `.env` file and restart the bot.")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    # Security Check
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Unauthorized user. You do not have access to this Cognitive OS.")
        return

    user_input = update.message.text
    chat_id = update.effective_chat.id
    loop = asyncio.get_running_loop()
    
    # Sync callback to send messages from the background thread
    def progress_callback(msg: str):
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id=chat_id, text=msg),
            loop
        )

    # Run the heavy orchestrator in a background thread so we don't block the bot
    def run_orchestrator():
        try:
            # 1. Process via Council
            result = orchestrator.process_request(user_input, progress_callback=progress_callback)
            
            # 2. Write to Obsidian
            pattern = orchestrator.sentry.classify_request(user_input)["pattern"]
            title_preview = user_input[:30] + "..." if len(user_input) > 30 else user_input
            task_id = orchestrator.memory.generate_task_id(user_input)
            
            obsidian.write_note(
                title=f"Mobile Request - {title_preview}",
                content=result,
                pattern_used=pattern,
                task_id=task_id
            )
            
            # 3. Send final result back to phone
            # Telegram has a 4096 char limit, so we chunk it if necessary
            if len(result) > 4000:
                chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
                for chunk in chunks:
                    progress_callback(chunk)
            else:
                progress_callback(result)
                
            progress_callback("✅ Saved to Obsidian Vault.")
            
        except Exception as e:
            progress_callback(f"❌ Error during execution: {str(e)}")

    await update.message.reply_text("⚙️ Request received. Pinging the Council...")
    # Fire and forget in a background thread using create_task
    asyncio.create_task(asyncio.to_thread(run_orchestrator))

def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env file.")
        return
        
    print("📱 Starting Telegram Bot Interface...")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot is polling. Send a message to your bot on Telegram!")
    app.run_polling()

if __name__ == "__main__":
    main()
