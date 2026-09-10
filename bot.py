import logging
import sqlite3
import random
import os
from flask import Flask
from threading import Thread
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- تنظیمات ---
TOKEN = '8980372812:AAGRIkvh4HeZOkU2E2UaiSkwL5ePM_LGfjQ'  # توکن ربات
ADMIN_ID = 7903625318    # آیدی ادمین
DB_NAME = "bot_data.db"

# --- راه اندازی سرور Flask برای Render ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- دیتابیس ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, points INTEGER, last_casino TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels (link TEXT)''')
    conn.commit()
    conn.close()

# --- توابع کمکی ---
def get_user_points(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE id=?", (user_id,))
    res = c.fetchone()
    conn.close()
    return res[0] if res else 0

# --- هندلرها ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id, points) VALUES (?, 0)", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("به ربات خوش اومدی! هر ۱ دقیقه کلمه 'تف' رو بفرست امتیاز بگیر.")

async def handle_taf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # چک کردن عضویت در کانال (ساده شده)
    if "تف" in update.message.text:
        user_id = update.effective_user.id
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("UPDATE users SET points = points + 10 WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
        await update.message.reply_text("۱۰ امتیاز گرفتی! 💧")

# دستور جدید: لیدربرد
async def top_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, points FROM users ORDER BY points DESC LIMIT 5")
    data = c.fetchall()
    msg = "🏆 **۵ نفر برتر:**\n\n"
    for i, user in enumerate(data, 1):
        msg += f"{i}. کاربر {user[0]}: {user[1]} امتیاز\n"
    await update.message.reply_text(msg, parse_mode='Markdown')
    conn.close()

# --- اجرای ربات ---
if __name__ == '__main__':
    init_db()
    # شروع سرور وب در یک ترد جداگانه (برای Render)
    Thread(target=run_web).start()
    
    app_bot = Application.builder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("top", top_users))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_taf))
    
    print("Bot is running...")
    app_bot.run_polling()

