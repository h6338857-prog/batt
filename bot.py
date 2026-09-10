import os
import asyncio
import logging
from datetime import datetime
from threading import Thread

# Flask برای Keep-Alive (بیدار نگه داشتن ربات در Render)
from flask import Flask
# Telegram Bot
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
# Database
from motor.motor_asyncio import AsyncIOMotorClient
# Fix for Asyncio conflicts
import nest_asyncio

# تنظیمات اولیه
nest_asyncio.apply()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تنظیمات امنیتی (می‌توانی اینجا تغییر دهی) ---
BOT_TOKEN = "8575157179:AAHH_YvQhD5b7-ywiJt32A7w_Od0GcIV9Ig"
ADMIN_ID = 7903625318
# حتماً لینک MongoDB خود را در قسمت زیر جایگزین کن
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://your_username:your_password@cluster.mongodb.net/myDatabase?retryWrites=true&w=majority")

# --- Flask Setup (Keep-Alive) ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Bot is running smoothly!", 200

def run_flask():
    # استفاده از پورت محیطی Render
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- Database Logic ---
class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client.bot_database
        print("✅ Connected to MongoDB")

    async def get_user(self, user_id):
        return await self.db.users.find_one({"user_id": user_id})

    async def update_user(self, user_id, data):
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$set": data},
            upsert=True
        )

    async def add_coins(self, user_id, amount):
        await self.db.users.update_one(
            {"user_id": user_id},
            {"$inc": {"coins": amount}},
            upsert=True
        )

db = Database()

# --- Bot Logic ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = await db.get_user(user.id)
    
    if not user_data:
        await db.update_user(user.id, {
            "user_id": user.id,
            "username": user.username,
            "coins": 100,
            "level": 1,
            "exp": 0
        })
        text = f"👋 خوش آمدی {user.first_name}!\n\n💰 ۱۰۰ سکه هدیه گرفتی.\nاز دستور /profile برای مشاهده وضعیت استفاده کن."
    else:
        text = f"👋 دوباره خوش آمدی {user.first_name}!"

    await update.message.reply_text(text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = await db.get_user(user.id)
    
    if not user_data:
        await update.message.reply_text("اول دستور /start را بزن!")
        return

    msg = (
        f"👤 **پروفایل کاربر**\n\n"
        f"🆔 آیدی: `{user.id}`\n"
        f"💰 موجودی: {user_data.get('coins', 0)} سکه\n"
        f"📈 لول: {user_data.get('level', 1)}\n"
        f"✨ تجربه: {user_data.get('exp', 0)}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # سیستم شناسایی کلمه "تف"
    if "تف" in text:
        # محاسبه پاداش بر اساس لول (مثال ساده)
        user_data = await db.get_user(user_id)
        level = user_data.get('level', 1) if user_data else 1
        reward = 5 * level 
        
        await db.add_coins(user_id, reward)
        await update.message.reply_text(f"🎰 شما {reward} سکه برنده شدید!")

# --- Admin Panel ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
        [InlineKeyboardButton("📊 آمار کلی", callback_data='stats')],
        [InlineKeyboardButton("🎁 ارسال هدیه", callback_data='give_gift')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠 پنل مدیریت:", reply_markup=reply_markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'stats':
        # اینجا می‌توانی آمار واقعی از دیتابیس بگیری
        await query.edit_message_text("📊 آمار: در حال دریافت...")
    elif query.data == 'give_gift':
        await query.edit_message_text("💰 برای ارسال هدیه، آیدی کاربر و مقدار را بفرست.")

# --- Main Entry Point ---

async def main():
    # ۱. اتصال به دیتابیس
    await db.connect()

    # ۲. ساخت Application ربات
    application = Application.builder().token(BOT_TOKEN).build()

    # ۳. اضافه کردن هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ۴. استارت کردن Flask در یک ترد جداگانه
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 Flask server running for Keep-Alive.")

    # ۵. اجرای ربات با استفاده از ساختار مدیریت شده
    print("🤖 Bot is starting...")
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        print("🚀 Bot is LIVE!")
        
        # نگه داشتن برنامه در حالت اجرا
        while True:
            await asyncio.sleep(3600) # هر یک ساعت یک بار بیدار می‌ماند

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("🛑 Bot stopped.")
    except Exception as e:
        print(f"❌ Critical Error: {e}")
