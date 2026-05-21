import os
import asyncio
import base64
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from src.orchestrator import Orchestrator
from src.obsidian_writer import ObsidianWriter

# Container Lifecycle: Test Features
from src.improvements.test.telegram_enhancements import TelegramEnhancementManager

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("ALLOWED_TELEGRAM_USER_ID")

orchestrator = Orchestrator()
obsidian = ObsidianWriter()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    msg = (f"🧠 Cognitive OS Online (v2).\n"
           f"Your User ID is: `{user_id}`\n\n"
           f"Security Status: {'✅ Authorized' if (not ALLOWED_USER_ID or user_id == ALLOWED_USER_ID) else '⛔ Unauthorized'}")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    
    # Convert to base64 for Orchestrator
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    caption = update.message.caption or "Analyze this image."
    
    await process_request(update, context, caption, image_base64)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return
        
    await update.message.reply_text("🎤 Voice note received. Transcribing...")
    
    # Download the voice note
    voice_file = await update.message.voice.get_file()
    
    import tempfile
    import os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
        audio_path = tmp.name
        
    await voice_file.download_to_drive(audio_path)
    
    # Process transcription via containerized feature
    transcription = TelegramEnhancementManager.process_voice_note(audio_path)
    os.remove(audio_path)
    
    await update.message.reply_text(f"📝 Transcription complete. Sending to Council:\n_{transcription}_", parse_mode="Markdown")
    
    # Send transcribed text to orchestrator
    await process_request(update, context, transcription)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    # Check for YouTube links via containerized feature
    processed_text = TelegramEnhancementManager.extract_youtube_transcript(update.message.text)
    
    await process_request(update, context, processed_text)

async def process_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str, image_base64: str = None):
    chat_id = update.effective_chat.id
    loop = asyncio.get_running_loop()
    
    def progress_callback(msg: str):
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id=chat_id, text=msg),
            loop
        )

    def run_orchestrator():
        try:
            result = orchestrator.process_request(user_input, image_base64=image_base64, progress_callback=progress_callback)
            
            # Write to Obsidian
            pattern = orchestrator.sentry.classify_request(user_input)["pattern"]
            
            import re
            keywords = "_".join(re.findall(r'\w+', user_input)[:5])
            task_id = orchestrator.memory.generate_task_id(user_input)
            
            file_path = obsidian.write_note(
                title=f"TG_R_{keywords}",
                content=result,
                pattern_used=pattern,
                task_id=task_id
            )

            import os
            report_name = os.path.basename(file_path).replace('.md', '') if file_path else f"TG_R_{keywords}"
            task_data = orchestrator.memory.get_task_data(task_id)
            obsidian.save_memory_log(task_id, task_data, report_name)
            
            if len(result) > 4000:
                chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
                for chunk in chunks: progress_callback(chunk)
            else:
                progress_callback(result)
                
            progress_callback("✅ Saved to Obsidian Vault.")
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"🚨 FATAL THREAD ERROR:\n{error_trace}")
            progress_callback(f"❌ Error during execution:\n```\n{error_trace}\n```")

    await update.message.reply_text("⚙️ Request received. Pinging the Council...")
    asyncio.create_task(asyncio.to_thread(run_orchestrator))

async def search_vault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("🔍 Please provide a search query. Usage: `/search [term]`")
        return

    await update.message.reply_text(f"🔍 Searching vault for: `{query}`...")
    results = obsidian.search_vault(query)
    
    if not results:
        await update.message.reply_text("❌ No results found in the vault.")
        return

    response = "📝 **Search Results:**\n\n"
    for r in results:
        response += f"📄 **{r['title']}**\n_{r['snippet']}_\n\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')

def main():
    if not TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found in .env file.")
        return
        
    print("📱 Starting Telegram Bot Interface v2...")
    app = Application.builder().token(TOKEN).build()
    
    # Development Lifecycle Handler
    async def dev_proposal(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
            await update.message.reply_text("⛔ Unauthorized.")
            return
        
        user_input = " ".join(context.args) if context.args else ""
        if not user_input:
            await update.message.reply_text("📝 Usage: `/dev <proposal>`\nExample: `/dev Add new Telegram command handler`")
            return
        
        await update.message.reply_text(f"🚀 Starting Development Lifecycle for:\n_{user_input}_", parse_mode="Markdown")
        
        # Start dev lifecycle workflow
        def run_dev_lifecycle():
            try:
                def progress_callback(msg):
                    asyncio.run_coroutine_threadsafe(
                        context.bot.send_message(chat_id=chat_id, text=msg),
                        loop
                    )
                
                result = orchestrator.execute_development_lifecycle(user_input, progress_callback=progress_callback)

                # Dev proposals go to dev/proposals via DevRouteManager, NOT to AI-Help/cognitive-os
                # No need to write to Obsidian vault here

                if len(result) > 4000:
                    chunks = [result[i:i+4000] for i in range(0, len(result), 4000)]
                    for chunk in chunks: progress_callback(chunk)
                else:
                    progress_callback(result)
                    
                progress_callback("✅ Development lifecycle complete! Proposal saved to Obsidian.")
                
            except Exception as e:
                import traceback
                error_msg = f"❌ Dev Lifecycle Error:\n```\n{traceback.format_exc()}\n```"
                progress_callback(error_msg)
        
        chat_id = update.effective_chat.id
        loop = asyncio.get_running_loop()
        await asyncio.to_thread(run_dev_lifecycle)
    
    # Generic wrapper for slash commands to route them through standard process
    async def route_command(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str):
        user_id = str(update.effective_user.id)
        if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
            await update.message.reply_text("⛔ Unauthorized.")
            return
            
        user_input = " ".join(context.args) if context.args else ""
        if not user_input:
            await update.message.reply_text(f"📝 Usage: `/{prefix} <your prompt>`")
            return
            
        # Reconstruct the prompt with the prefix so SentryRouter catches it
        full_prompt = f"#{prefix} {user_input}"
        await process_request(update, context, full_prompt)

    async def design_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await route_command(update, context, "design")
        
    async def tech_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await route_command(update, context, "technical")
        
    async def boardroom_meeting(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await route_command(update, context, "boardroom")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_vault))
    app.add_handler(CommandHandler("dev", dev_proposal))
    app.add_handler(CommandHandler("design", design_meeting))
    app.add_handler(CommandHandler("technical", tech_meeting))
    app.add_handler(CommandHandler("boardroom", boardroom_meeting))
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot is polling. Send a message to your bot on Telegram!")
    app.run_polling()

if __name__ == "__main__":
    main()
