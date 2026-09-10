import os
import asyncio
import logging
import uvicorn
from datetime import datetime
from threading import Thread

# FastAPI برای Keep-Alive (نسخه مدرن و سازگار با Async)
from fastapi import FastAPI
# Telegram Bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
# Database
from motor.motor_asyncio import AsyncIOMotorClient

# تنظیمات اولیه
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تنظیمات ---
BOT_TOKEN = "8575157179:AAHH_YvQhD5b7-ywiJt32A7w_Od0GcIV9Ig"
ADMIN_ID = 7903625318
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://your_username:your_password@cluster.mongodb.net/myDatabase")

# --- FastAPI Setup (جایگزین Flask برای جلوگیری از ارور) ---
app = FastAPI()

@app.get("/")
async def root():
    return {"status": "alive", "timestamp": datetime.now().isoformat()}

def run_web_server():
    # اجرای FastAPI با uvicorn در یک ترد جداگانه
    port = int(os.environ.get('PORT', 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")

# --- Database Logic ---
class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        try:
            self.client = AsyncIOMotorClient(MONGO_URI)
            self.db = self.client.bot_database
            print("✅ Connected to MongoDB")
        except Exception as e:
            print(f"❌ MongoDB Connection Error: {e}")

    async def get_user(self, user_id):
        return await self.db.users.find_one({"user_id": user_id})

    async def update_user(self, user_id, data):
        await self.db.users.update_one({"user_id": user_id}, {"$set": data}, upsert=True)

    async def add_coins(self, user_id, amount):
        await self.db.users.update_one({"user_id": user_id}, {"$inc": {"coins": amount}}, upsert=True)

db = Database()

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = await db.get_user(user.id)
    if not user_data:
        await db.update_user(user.id, {"user_id": user.id, "username": user.username, "coins": 100, "level": 1, "exp": 0})
        await update.message.reply_text(f"👋 خوش آمدی {user.first_name}!\n💰 ۱۰۰ سکه هدیه گرفتی.")
    else:
        await update.message.reply_text(f"👋 دوباره خوش آمدی {user.first_name}!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = await db.get_user(user_id)
    if not user_data:
        await update.message.reply_text("اول /start را بزن.")
        return
    msg = (f"👤 **پروفایل**\n\n"
           f"💰 سکه: {user_data.get('coins', 0)}\n"
           f"📈 لول: {user_data.get('level', 1)}")
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "تف" in update.message.text:
        user_id = update.effective_user.id
        user_data = await db.get_user(user_id)
        level = user_data.get('level', 1) if user_data else 1
        reward = 5 * level
        await db.add_coins(user_id, reward)
        await update.message.reply_text(f"🎰 {reward} سکه برنده شدی!")

# --- Main ---
async def main():
    # ۱. اتصال دیتابیس
    await db.connect()

    # ۲. ساخت ربات
    application = Application.builder().token(BOT_TOKEN).build()

    # ۳. هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ۴. اجرای وب‌سرور (FastAPI) در یک ترد جداگانه
    # این بخش باعث می‌شود Render فکر کند برنامه در حال کار است و آن را نمی‌بندد
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("🌐 FastAPI web server started.")

    # ۵. اجرای ربات
    print("🤖 Bot is starting...")
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        print("🚀 Bot is ONLINE and keeping alive!")
        
        # جلوگیری از بسته شدن برنامه
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"❌ Critical Error: {e}")
