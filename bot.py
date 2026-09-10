import os
import asyncio
import logging
import uvicorn
import random
from datetime import datetime, timedelta
from threading import Thread
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from motor.motor_asyncio import AsyncIOMotorClient

# --- تنظیمات لاگ ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- تنظیمات اصلی ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8575157179:AAHH_YvQhD5b7-ywiJt32A7w_Od0GcIV9Ig")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 7903625318))
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://your_user:your_pass@cluster.mongodb.net/db")

# --- FastAPI برای Keep-Alive ---
app = FastAPI()
@app.get("/")
async def root(): return {"status": "online"}

def run_web_server():
    port = int(os.environ.get('PORT', 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)

# --- دیتابیس و مدل‌ها ---
class Database:
    def __init__(self):
        self.client = None
        self.db = None

    async def connect(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client.taf_bot_db
        print("✅ MongoDB Connected")

    async def get_user(self, uid): return await self.db.users.find_one({"user_id": uid})
    async def update_user(self, uid, data): await self.db.users.update_one({"user_id": uid}, {"$set": data}, upsert=True)
    async def add_coins(self, uid, amount): await self.db.users.update_one({"user_id": uid}, {"$inc": {"coins": amount}}, upsert=True)
    async def add_exp(self, uid, amount):
        user = await self.get_user(uid)
        new_exp = user.get('exp', 0) + amount
        new_lvl = (new_exp // 500) + 1
        await self.update_user(uid, {"exp": new_exp, "level": new_lvl})
        return new_lvl

db = Database()

# --- سیستم‌های جانبی (Helper Functions) ---
async def get_reward_multiplier(user_id):
    user = await db.get_user(user_id)
    return user.get('level', 1) if user else 1

# --- هندلرها: دستورات کاربر ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_data = await db.get_user(user.id)
    if not user_data:
        await db.update_user(user.id, {"user_id": user.id, "username": user.username, "coins": 100, "level": 1, "exp": 0, "title": "مهمان"})
        await update.message.reply_text(f"👋 خوش آمدی {user.first_name}!\n💰 ۱۰۰ سکه هدیه گرفتی.\n\nبرای مشاهده وضعیت خود از /profile استفاده کن.")
    else:
        await update.message.reply_text(f"👋 خوش برگشتی {user.first_name}!")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user: return
    
    text = (f"👤 **پروفایل شما**\n\n"
            f"🆔 آیدی: `{user_id}`\n"
            f"🏷 عنوان: {user.get('title', 'مهمان')}\n"
            f"💰 سکه: {user.get('coins', 0)}\n"
            f"📈 لول: {user.get('level', 1)}\n"
            f"✨ تجربه: {user.get('exp', 0)}")
    
    keyboard = [[InlineKeyboardButton("🛒 فروشگاه", callback_data="shop"), 
                 InlineKeyboardButton("🎲 شانس", callback_data="casino")]]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_taf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or "تف" not in update.message.text: return
    uid = update.effective_user.id
    mult = await get_reward_multiplier(uid)
    reward = random.randint(5, 15) * mult
    await db.add_coins(uid, reward)
    await db.add_exp(uid, 20)
    await update.message.reply_text(f"🎰 ماشالله! {reward} سکه برنده شدی! 🎉")

# --- هندلرها: شانس (Casino) ---

async def casino_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🎲 تاس", callback_data="game_dice"), InlineKeyboardButton("🪙 سکه", callback_data="game_coin")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_profile")]
    ]
    await query.edit_message_text("🎲 به بخش شانس خوش آمدی! بازی خود را انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    game_type = query.data.split("_")[1]
    user = await db.get_user(uid)
    
    bet = 50 # مبلغ پیش‌فرض شرط
    if user['coins'] < bet:
        await query.answer("💰 سکه کافی نداری!", show_alert=True)
        return

    win = False
    if game_type == "dice":
        res = random.randint(1, 6)
        win = res >= 4
    else: # coin
        win = random.choice([True, False])

    if win:
        await db.add_coins(uid, bet)
        await query.edit_message_text(f"🎊 برنده شدی! {bet} سکه به حساب اضافه شد.")
    else:
        await db.update_user(uid, {"coins": user['coins'] - bet})
        await query.edit_message_text(f"❌ باختی! {bet} سکه از دست دادی.")

# --- هندلرها: فروشگاه (Shop) ---

async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🏷 خرید عنوان (50k)", callback_data="buy_title")],
        [InlineKeyboardButton("📈 ارتقای تف (10k)", callback_data="buy_upgrade")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_profile")]
    ]
    await query.edit_message_text("🛒 به فروشگاه خوش آمدی! آیتم خود را انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    item = query.data
    user = await db.get_user(uid)

    if item == "buy_title" and user['coins'] >= 50000:
        await db.update_user(uid, {"title": "👑 سلطان"})
        await db.add_coins(uid, -50000)
        await query.answer("✅ عنوان با موفقیت خریداری شد!")
    elif item == "buy_upgrade" and user['coins'] >= 10000:
        # منطق ارتقای ضریب در اینجا قرار می‌گیرد
        await db.add_coins(uid, -10000)
        await query.answer("✅ ارتقا انجام شد!")
    else:
        await query.answer("❌ موجودی کافی نیست!", show_alert=True)

# --- پنل ادمین (Admin Panel) ---

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text("🛠 پنل مدیریت ادمین:\n/stats - آمار ربات\n/broadcast [text] - ارسال پیام")

async def bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    count = await db.db.users.count_documents({})
    await update.message.reply_text(f"📊 آمار کلی:\nتعداد کاربران: {count}")

# --- اجرای اصلی ---

async def main():
    await db.connect()
    application = Application.builder().token(BOT_TOKEN).build()

    # دستورات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("stats", bot_stats))
    
    # هندلرها
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_taf))
    application.add_handler(CallbackQueryHandler(casino_menu, pattern="^casino$"))
    application.add_handler(CallbackQueryHandler(shop_menu, pattern="^shop$"))
    application.add_handler(CallbackQueryHandler(play_game, pattern="^game_"))
    application.add_handler(CallbackQueryHandler(buy_item, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(lambda u, c: profile(u, c), pattern="^back_to_profile$"))

    # وب‌سرور برای Render
    web_thread = Thread(target=run_web_server, daemon=True)
    web_thread.start()

    print("🚀 BOT IS FULLY ACTIVE!")
    async with application:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"FATAL: {e}")
