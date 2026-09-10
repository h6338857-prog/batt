import os
import logging
import random
import asyncio
import sqlite3
from datetime import datetime
from threading import Thread

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationError
import logging

# --- تنظیمات اولیه ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# دریافت پورت از Render (بسیار مهم)
PORT = int(os.environ.get("PORT", 8080))
BOT_TOKEN = "8575157179:AAHH_YvQhD5b7-ywiJt32A7w_Od0GcIV9Ig"  # توکن خود را اینجا بگذارید
ADMIN_ID = 7903625318  # آیدی عددی ادمین را اینجا بگذارید

# --- بخش Flask برای جلوگیری از Sleep شدن در Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running smoothly! ✅"

def run_flask():
    app.run(host='0.0.0.0', port=PORT)

# --- دیتابیس (SQLite) ---
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    # جدول کاربران
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, coins INTEGER DEFAULT 0, 
                  tef_level INTEGER DEFAULT 1, messages INTEGER DEFAULT 0, 
                  title TEXT, rank TEXT DEFAULT 'برنزی')''')
    # جدول تنظیمات ادمین
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (key TEXT PRIMARY KEY, value TEXT)''')
    # جدول قرعه‌کشی
    c.execute('''CREATE TABLE IF NOT EXISTS lotteries 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, prize TEXT, end_date TEXT)''')
    conn.commit()
    conn.close()

def db_query(query, params=(), fetchall=False):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute(query, params)
    if fetchall:
        res = c.fetchall()
    else:
        res = c.fetchone()
    conn.commit()
    conn.close()
    return res

# --- منطق‌های اقتصادی ---
def get_tef_reward(level):
    # با افزایش لول، بازه جایزه بیشتر می‌شود
    min_reward = 10 + (level * 2)
    max_reward = 25 + (level * 5)
    return random.randint(min_reward, max_reward)

def get_tef_upgrade_cost(level):
    # هزینه ارتقا به صورت تصاعدی
    return int(100 * (1.6 ** level))

# --- دستورات و هندلرهای ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # ثبت کاربر در دیتابیس اگر وجود نداشت
    user = db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not user:
        db_query("INSERT INTO users (user_id) VALUES (?)", (user_id,))
    
    welcome_msg = "👋 به ربات تف خوش آمدید!\n\nاستفاده از دستورات:\n/پروفایل - مشاهده اطلاعات\n/فروشگاه - خرید و ارتقا\n/کازینو - بازی‌های شانس\n/راهنما - لیست دستورات"
    await update.message.reply_text(welcome_msg)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = db_query("SELECT coins, tef_level, messages, title, rank FROM users WHERE user_id = ?", (user_id,))
    
    if user:
        coins, tef_lvl, msgs, title, rank = user
        display_title = f" لقب: {title}" if title else ""
        msg = (f"👤 **پروفایل کاربر**\n\n"
               f"💰 موجودی: {coins} سکه\n"
               f"🆙 سطح تف: {tef_lvl}\n"
               f"✉️ پیام‌های ارسالی: {msgs}\n"
               f"🎖 رتبه: {rank}\n"
               f"{display_title}")
        await update.message.reply_text(msg, parse_mode='Markdown')

async def tef_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id
    
    if "تف" in text:
        # بررسی ریپلای
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            target_id = target_user.id
            target_name = target_user.first_name
            msg = f"💥 کاربر {user_id} روی {target_name} ({target_id}) تف کرد!"
        else:
            msg = f"✨ کاربر {user_id} تف کرد! (بدون هدف)"

        # پاداش دادن
        user = db_query("SELECT tef_level FROM users WHERE user_id = ?", (user_id,))
        lvl = user[0] if user else 1
        reward = get_tef_reward(lvl)
        
        db_query("UPDATE users SET coins = coins + ?, messages = messages + 1 WHERE user_id = ?", (reward, user_id))
        await update.message.reply_text(f"{msg}\n💰 جایزه شما: {reward} سکه")

async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🆙 ارتقای تف", callback_data='shop_upgrade')],
        [InlineKeyboardButton("✨ خرید لقب (5k)", callback_data='shop_title')],
        [InlineKeyboardButton("💸 انتقال سکه", callback_data='shop_transfer')],
        [InlineKeyboardButton("📢 خرید پیام همگانی (50k)", callback_data='shop_broadcast')],
        [InlineKeyboardButton("🔙 بازگشت", callback_data='shop_back')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🛒 **فروشگاه ربات**\nلطفاً گزینه مورد نظر را انتخاب کنید:", reply_markup=reply_markup, parse_mode='Markdown')

# --- مدیریت دکمه‌های شیشه‌ای (Callback Queries) ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'shop_upgrade':
        user = db_query("SELECT tef_level, coins FROM users WHERE user_id = ?", (user_id,))
        lvl, coins = user
        cost = get_tef_upgrade_cost(lvl)
        
        if coins >= cost:
            db_query("UPDATE users SET tef_level = tef_level + 1, coins = coins - ? WHERE user_id = ?", (cost, user_id))
            await query.edit_message_text(f"✅ تبریک! سطح تف شما به {lvl+1} رسید.\nهزینه کسر شد: {cost}")
        else:
            await query.edit_message_text(f"❌ سکه کافی ندارید! قیمت ارتقا: {cost}")

    elif query.data == 'shop_broadcast':
        user = db_query("SELECT coins FROM users WHERE user_id = ?", (user_id,))
        if user[0] >= 50000:
            db_query("UPDATE users SET coins = coins - 50000 WHERE user_id = ?", (user_id,))
            # ارسال به ادمین
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 خرید پیام همگانی توسط کاربر:\nID: {user_id}")
            await query.edit_message_text("✅ خرید موفقیت‌آمیز بود. ادمین در جریان قرار گرفت.")
        else:
            await query.edit_message_text("❌ سکه کافی ندارید! قیمت: 50,000 سکه")

# --- تابع اصلی اجرا ---
def main():
    # ۱. شروع سرور Flask در یک Thread جداگانه
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    print(f"🚀 Flask Server started on port {PORT}")

    # ۲. مقداردهی اولیه دیتابیس
    init_db()

    # ۳. راه‌اندازی ربات تلگرام
    application = Application.builder().token(BOT_TOKEN).build()

    # هندلرها
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("پروفایل", profile))
    application.add_handler(CommandHandler("فروشگاه", shop))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tef_logic))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
