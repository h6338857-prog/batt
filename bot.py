import logging
import os
import asyncio
import random
from datetime import datetime
from flask import Flask
from threading import Thread

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from motor.motor_asyncio import AsyncIOMotorClient

# --- تنظیمات اولیه ---
# در Render، این مقادیر را از Environment Variables تنظیم کن
BOT_TOKEN = os.getenv("BOT_TOKEN", "8575157179:AAHH_YvQhD5b7-ywiJt32A7w_Od0GcIV9Ig")
ADMIN_ID = int(os.getenv("7903625318", "0")) 
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://<db_username>:Bu3QZCFmeH3gPgrW@cluster0.uy2uzj3.mongodb.net/?appName=Cluster0")

# راه‌اندازی Flask برای جلوگیری از Sleep شدن در Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

# --- تنظیمات دیتابیس ---
client = AsyncIOMotorClient(MONGO_URI)
db = client.bot_taf_db
users_col = db.users

# --- توابع کمکی دیتابیس ---
async def get_user(user_id):
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        user = {
            "user_id": user_id,
            "coins": 10,
            "level": 1,
            "last_taf": 0,
            "is_premium": False,
            "title": None,
            "joined_at": datetime.now()
        }
        await users_col.insert_one(user)
    return user

async def update_user(user_id, data):
    await users_col.update_one({"user_id": user_id}, {"$set": data})

# --- منطق اصلی ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    text = (f"👋 خوش آمدید!\n\n"
            f"💰 سکه شما: {user['coins']}\n"
            f"📈 لول شما: {user['level']}\n"
            f"🏷 لقب: {user['title'] if user['title'] else 'ندارد'}\n\n"
            f"برای بازی یا استفاده از دستورات، از من استفاده کنید.")
    await update.message.reply_text(text)

# --- سیستم "تف" ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    user = await get_user(user_id)

    if "تف" in text:
        # چک کردن قابلیت ریپلای یا تگ
        target_id = None
        if update.message.reply_to_message:
            try:
                target_id = update.message.reply_to_message.from_user.id
            except: pass
        
        if target_id:
            # پاداش بر اساس لول: 10 + (level * 2) تا حداکثر 25
            reward = min(10 + (user['level'] * 2), 25)
            await update_user(user_id, {"coins": user['coins'] + reward})
            await update.message.reply_text(f"🎯 تف موفقیت‌آمیز! {reward} سکه دریافت کردید.")
            
            # آپدیت کردن کاربر هدف (اختیاری - مثلا برای کاهش سکه یا فقط نمایش)
            # در اینجا فقط کاربر خودش سکه می‌گیرد
        else:
            await update.message.reply_text("⚠️ برای 'تف' کردن روی کسی، باید روی پیام او ریپلای کنید!")

# --- پنل ادمین ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
        [InlineKeyboardButton("🎁 هدیه دادن به کاربر", callback_data="admin_gift")],
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="admin_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛠 پنل مدیریت ادمین:", reply_markup=reply_markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_gift":
        await query.edit_message_text("📥 لطفاً ID کاربر و مبلغ را به این صورت بفرستید:\n\n`ID مبلغ`\nمثال: `12345678 5000`", parse_mode="Markdown")
        context.user_data['awaiting_gift'] = True
    
    elif query.data == "admin_stats":
        count = await users_col.count_documents({})
        await query.edit_message_text(f"📊 تعداد کل کاربران: {count}")

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # این بخش مدیریت ورودی‌های ادمین (مثل هدیه دادن) را بر عهده دارد
    if context.user_data.get('awaiting_gift') and update.effective_user.id == ADMIN_ID:
        try:
            parts = update.message.text.split()
            target_id = int(parts[0])
            amount = int(parts[1])
            
            target_user = await get_user(target_id)
            await update_user(target_id, {"coins": target_user['coins'] + amount})
            
            await update.message.reply_text(f"✅ مبلغ {amount} سکه به کاربر {target_id} هدیه داده شد.")
            context.user_data['awaiting_gift'] = False
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در فرمت! دوباره امتحان کنید.\nخطا: {e}")

# --- اجرای اصلی ---
async def main():
    # شروع Flask در یک Thread جداگانه
    Thread(target=run_flask, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    # هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(admin_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & filters.Chat(ADMIN_ID), handle_admin_input))

    print("Bot is starting...")
    await application.run_polling()

if __name__ == '__main__':
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.run(main())
