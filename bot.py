"""
🤖 Telegram Advanced Game & Casino Bot
Developed for Render Web Service (Anti-Sleep Integrated)
Database: PostgreSQL
"""

import os
import random
import logging
import threading
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, filters, ContextTypes
)

# ==================== تنظیمات و لاگ‌ها ====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.getenv('BOT_TOKEN', '8949103823:AAHFzGSkqwY72yCLDZuDMBJacs8TBvirg-Q')
ADMIN_ID = int(os.getenv('ADMIN_ID', '7903625318'))
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://telegram_bot_db_7mx4_user:03C0t0vnZvGT5k9FmUqtx01L9HCW1Ng0@dpg-dahjf6u7bikc73eevhgg-a/telegram_bot_db_7mx4')

# استیت‌های گفتگو (Conversation States)
(
    WAITING_ADMIN_CHANNEL, WAITING_ADMIN_GIVE_COIN_ID, WAITING_ADMIN_GIVE_COIN_AMT,
    WAITING_ADMIN_PRICE_GAME, WAITING_ADMIN_PRICE_VAL, WAITING_ADMIN_LOTTERY,
    WAITING_ADMIN_SET_WELCOME, WAITING_ADMIN_SET_RULES, WAITING_TRANSFER_REPLY
) = range(9)

# ==================== ۱. وب‌سرور Render (Keep-Alive) ====================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot status: ONLINE (24/7 Render Active)", 200

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ==================== ۲. مدیریت دیتابیس PostgreSQL ====================
class Database:
    def __init__(self, db_url):
        self.db_url = db_url

    def get_conn(self):
        return psycopg2.connect(self.db_url)

    def init_tables(self):
        queries = [
            """
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(255) PRIMARY KEY,
                value TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                first_name VARCHAR(255),
                coins BIGINT DEFAULT 100,
                msg_count BIGINT DEFAULT 0,
                taf_level INT DEFAULT 1,
                title VARCHAR(255) DEFAULT 'بدون لقب',
                banned BOOLEAN DEFAULT FALSE,
                last_active TIMESTAMP DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS lotteries (
                id SERIAL PRIMARY KEY,
                prize BIGINT,
                winner_id BIGINT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS lottery_participants (
                lottery_id INT,
                user_id BIGINT,
                PRIMARY KEY(lottery_id, user_id)
            );
            """
        ]
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                for q in queries:
                    cur.execute(q)

        # مقادیر پیش‌فرض تنظیمات
        defaults = {
            "mandatory_channel": "@YourChannel",
            "bot_status": "on",
            "welcome_msg": "سلام به ربات بازی و کازینو خوش آمدید!",
            "rules_msg": "قوانین ربات:\n۱. احترام به کاربران\n۲. عدم استفاده از ابزارهای تقلب",
            "cost_slot": "10",
            "cost_dice": "20",
            "cost_coin": "15",
            "cost_broadcast_perm": "50000"
        }
        for k, v in defaults.items():
            if not self.get_setting(k):
                self.set_setting(k, v)

    def set_setting(self, key, value):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
                    (key, str(value), str(value))
                )

    def get_setting(self, key, default=""):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                res = cur.fetchone()
                return res[0] if res else default

    def get_or_create_user(self, user_id, username="", first_name=""):
        with self.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                u = cur.fetchone()
                if not u:
                    cur.execute(
                        "INSERT INTO users (user_id, username, first_name) VALUES (%s, %s, %s) RETURNING *",
                        (user_id, username, first_name)
                    )
                    u = cur.fetchone()
                else:
                    cur.execute("UPDATE users SET last_active = NOW() WHERE user_id = %s", (user_id,))
                return dict(u)

    def inc_msg_count(self, user_id):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET msg_count = msg_count + 1, last_active = NOW() WHERE user_id = %s", (user_id,))

    def add_coins(self, user_id, amount):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET coins = coins + %s WHERE user_id = %s", (amount, user_id))

    def remove_coins(self, user_id, amount):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT coins FROM users WHERE user_id = %s", (user_id,))
                c = cur.fetchone()
                if c and c[0] >= amount:
                    cur.execute("UPDATE users SET coins = coins - %s WHERE user_id = %s", (amount, user_id))
                    return True
                return False

    def get_user_rank(self, user_id):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT rank FROM (
                        SELECT user_id, RANK() OVER (ORDER BY coins DESC) as rank FROM users
                    ) as ranked WHERE user_id = %s
                """, (user_id,))
                res = cur.fetchone()
                return res[0] if res else 0

    def get_stats(self):
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*), SUM(coins) FROM users")
                total_users, total_coins = cur.fetchone()

                now = datetime.now()
                cur.execute("SELECT COUNT(*) FROM users WHERE last_active >= %s", (now - timedelta(days=1),))
                daily = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM users WHERE last_active >= %s", (now - timedelta(days=7),))
                weekly = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM users WHERE last_active >= %s", (now - timedelta(days=30),))
                monthly = cur.fetchone()[0]

                return {
                    "total_users": total_users or 0,
                    "total_coins": total_coins or 0,
                    "daily": daily,
                    "weekly": weekly,
                    "monthly": monthly
                }

db = Database(DATABASE_URL)

# ==================== ۳. ابزارهای کمکی ====================
async def check_channel_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    channel = db.get_setting("mandatory_channel")
    if not channel or channel == "OFF":
        return True
    try:
        m = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        return m.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

def get_user_level(coins: int) -> str:
    if coins >= 100000: return "💎 الماس"
    if coins >= 25000: return "🥇 طلایی"
    if coins >= 5000: return "🥈 نقره‌ای"
    return "🥉 برنزی"

# ==================== ۴. کیبوردها ====================
def main_kb(user_id):
    kb = [
        [InlineKeyboardButton("👤 پروفایل", callback_data="profile"), InlineKeyboardButton("🎰 کازینو", callback_data="casino")],
        [InlineKeyboardButton("🛍️ فروشگاه", callback_data="shop"), InlineKeyboardButton("🏆 لیدربورد", callback_data="leaderboard")],
        [InlineKeyboardButton("📜 راهنما", callback_data="help"), InlineKeyboardButton("📜 قوانین", callback_data="rules")]
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 پنل مدیریت ادمین", callback_data="admin_main")])
    return InlineKeyboardMarkup(kb)

def admin_kb():
    bot_status = db.get_setting("bot_status", "on")
    status_icon = "🟢 روشن" if bot_status == "on" else "🔴 خاموش"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار جامع", callback_data="admin_stats"), InlineKeyboardButton(f"وضعیت ربات: {status_icon}", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton("🎁 اهدا سکه دستی", callback_data="admin_give_coins"), InlineKeyboardButton("📢 تنظیم کانال اجباری", callback_data="admin_set_channel")],
        [InlineKeyboardButton("⚙️ قیمت بازی‌ها", callback_data="admin_set_prices"), InlineKeyboardButton("🎉 مدیریت قرعه‌کشی", callback_data="admin_lottery")],
        [InlineKeyboardButton("✏️ پیام خوش‌آمد", callback_data="admin_set_welcome"), InlineKeyboardButton("✏️ متن قوانین", callback_data="admin_set_rules")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")]
    ])

# ==================== ۵. هندرها و پردازش اصلی ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)

    if db.get_setting("bot_status") == "off" and user.id != ADMIN_ID:
        await update.message.reply_text("🔴 ربات در حال حاضر جهت بروزرسانی خاموش می‌باشد.")
        return

    if not await check_channel_member(context, user.id):
        ch = db.get_setting("mandatory_channel")
        url = f"https://t.me/{ch.replace('@', '')}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📢 جوین در کانال", url=url)],
            [InlineKeyboardButton("✅ جوین شدم (تایید)", callback_data="check_join")]
        ])
        await update.message.reply_text("⚠️ **برای استفاده از ربات باید در کانال رسمی ما عضو باشید:**", reply_markup=kb, parse_mode="Markdown")
        return

    welcome_msg = db.get_setting("welcome_msg")
    await update.message.reply_text(f"{welcome_msg}\n\nاز منوی زیر استفاده کنید:", reply_markup=main_kb(user.id))

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user
    
    # چک خاموش بودن ربات
    if db.get_setting("bot_status") == "off" and user.id != ADMIN_ID:
        return

    # شمارش پیام‌ها
    db.inc_msg_count(user.id)

    # چک عضویت در کانال جهت اعطای امتیاز
    is_member = await check_channel_member(context, user.id)

    # ۱. پردازش کلمه "پروفایل"
    if text.strip() == "پروفایل":
        u = db.get_or_create_user(user.id)
        rank = db.get_user_rank(user.id)
        level = get_user_level(u['coins'])
        profile_text = f"""
👤 **پروفایل کاربری**
───────────────
🏷️ نام/لقب: **{u['title']}**
💰 سکه‌ها: **{u['coins']:,}**
🏅 سطح: **{level}**
📊 تعداد پیام‌ها: **{u['msg_count']:,}**
🏆 رتبه در لیدربورد: **#{rank}**
        """
        await update.message.reply_text(profile_text, parse_mode="Markdown")
        return

    # ۲. پردازش کلمه "تف"
    if "تف" in text:
        if not is_member:
            await update.message.reply_text("❌ برای دریافت سکه از طریق کلمه «تف» باید در کانال اجباری جوین باشید!")
            return

        u = db.get_or_create_user(user.id)
        taf_level = u['taf_level']
        
        # محاسبه سکه: پایه ۱۰ الی ۲۵ + ضریب ارتقا
        base_coins = random.randint(10, 25)
        earned_coins = base_coins + ((taf_level - 1) * 5)
        
        db.add_coins(user.id, earned_coins)
        await update.message.reply_text(f"💦 **تف!** شما **{earned_coins}** سکه به دست آوردید! (سطح تف: {taf_level})")

async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    data = query.data
    await query.answer()

    if data == "check_join":
        if await check_channel_member(context, user.id):
            await query.message.edit_text("✅ عضویت شما تایید شد!", reply_markup=main_kb(user.id))
        else:
            await query.answer("❌ هنوز در کانال عضو نشده‌اید!", show_alert=True)
        return

    if data == "main_menu":
        await query.message.edit_text("📌 **منوی اصلی:**", reply_markup=main_kb(user.id), parse_mode="Markdown")

    elif data == "profile":
        u = db.get_or_create_user(user.id)
        rank = db.get_user_rank(user.id)
        level = get_user_level(u['coins'])
        p_text = f"👤 **پروفایل شما**\n\n🏷️ لقب: {u['title']}\n💰 سکه‌ها: {u['coins']:,}\n🏅 سطح: {level}\n📊 پیام‌ها: {u['msg_count']}\n🏆 رتبه: #{rank}"
        await query.message.edit_text(p_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    elif data == "help":
        help_text = """
📜 **راهنمای کامل کلمات و دستورات:**

🔸 **پروفایل**: مشاهده آمار کامل سکه، سطح و رتبه شما.
🔸 **تف**: ارسال کلمه تف در هر جمله‌ای باعث دریافت ۱۰ الی ۲۵ سکه (بستگی به سطح ارتقا) می‌شود.
🎰 **کازینو**: بازی‌های گردونه، تاس و شیر یا خط برای دوبرابر کردن سکه‌ها.
🛍️ **فروشگاه**: ارتقای قدرت تف، خرید لقب خاص، انتقال سکه و خرید مجوز ارسال همگانی!
        """
        await query.message.edit_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    elif data == "rules":
        r = db.get_setting("rules_msg")
        await query.message.edit_text(f"📜 **قوانین ربات:**\n\n{r}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    # 🛍️ بخش فروشگاه
    elif data == "shop":
        u = db.get_or_create_user(user.id)
        taf_lvl = u['taf_level']
        taf_cost = taf_lvl * 100
        bc_cost = int(db.get_setting("cost_broadcast_perm", "50000"))

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💦 ارتقای تف (سطح {taf_lvl+1}) - {taf_cost} سکه", callback_data="upgrade_taf")],
            [InlineKeyboardButton("💸 انتقال سکه (با ریپلای)", callback_data="shop_transfer")],
            [InlineKeyboardButton(f"📢 مجوز ارسال همگانی ({bc_cost:,} سکه)", callback_data="buy_broadcast")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ])
        await query.message.edit_text("🛍️ **به فروشگاه خوش آمدید!**\nگزینه مورد نظر را انتخاب کنید:", reply_markup=kb)

    elif data == "upgrade_taf":
        u = db.get_or_create_user(user.id)
        cost = u['taf_level'] * 100
        if db.remove_coins(user.id, cost):
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET taf_level = taf_level + 1 WHERE user_id = %s", (user.id,))
            await query.answer("🎉 ارتقا با موفقیت انجام شد!", show_alert=True)
            await callback_router(update, context) # Reload shop
        else:
            await query.answer("❌ سکه کافی ندارید!", show_alert=True)

    elif data == "buy_broadcast":
        cost = int(db.get_setting("cost_broadcast_perm", "50000"))
        if db.remove_coins(user.id, cost):
            # ارسال پیام به ادمین جهت خریدار همگانی
            await context.bot.send_message(
                ADMIN_ID,
                f"🚨 **خریدار جدید مجوز همگانی!**\n\n👤 کاربر: {user.first_name} (@{user.username})\n🆔 شناسه: `{user.id}`\n💰 مبلغ پرداخت شده: {cost:,} سکه"
            )
            await query.answer("✅ خرید موفقیت‌آمیز بود! اطلاعات شما برای ادمین ارسال شد.", show_alert=True)
        else:
            await query.answer("❌ سکه کافی برای خرید مجوز همگانی ندارید!", show_alert=True)

    elif data == "shop_transfer":
        await query.message.edit_text(
            "💸 **نحوه انتقال سکه:**\n\nروی پیام کاربر مورد نظر **ریپلای (Reply)** کنید و بنویسید:\n`انتقال 100`\n(به جای 100 مقدار سکه دلخواه را بزنید)",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به فروشگاه", callback_data="shop")]])
        )

    # 🎰 بخش کازینو
    elif data == "casino":
        c_slot = db.get_setting("cost_slot", "10")
        c_dice = db.get_setting("cost_dice", "20")
        c_coin = db.get_setting("cost_coin", "15")
        
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎰 گردونه شانس ({c_slot} سکه)", callback_data="play_slot")],
            [InlineKeyboardButton(f"🎲 انداختن تاس ({c_dice} سکه)", callback_data="play_dice")],
            [InlineKeyboardButton(f"🪙 شیر یا خط ({c_coin} سکه)", callback_data="play_coin")],
            [InlineKeyboardButton("🎟️ ورود به قرعه‌کشی فعال", callback_data="join_lottery")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ])
        await query.message.edit_text("🎰 **به کازینو خوش آمدید!**\nشانس خود را امتحان کنید:", reply_markup=kb)

    elif data == "play_slot":
        cost = int(db.get_setting("cost_slot", "10"))
        if not db.remove_coins(user.id, cost):
            await query.answer("❌ سکه کافی ندارید!", show_alert=True)
            return
        
        items = ["🍎", "🍋", "💎", "7️⃣"]
        res = [random.choice(items) for _ in range(3)]
        won = (res[0] == res[1] == res[2])
        prize = cost * 5 if won else 0
        if won: db.add_coins(user.id, prize)

        txt = f"🎰 **گردونه چرخید:**\n\n{' | '.join(res)}\n\n" + (f"🎉 فوق‌العاده! شما **{prize}** سکه برنده شدید!" if won else "❌ متاسفانه شانس با شما یار نبود.")
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 دوباره", callback_data="play_slot"), InlineKeyboardButton("🔙 بازگشت", callback_data="casino")]]))

    # 👑 بخش ادمین
    elif data == "admin_main" and user.id == ADMIN_ID:
        await query.message.edit_text("👑 **پنل مدیریت پیشرفته ادمین:**", reply_markup=admin_kb(), parse_mode="Markdown")

    elif data == "admin_stats" and user.id == ADMIN_ID:
        st = db.get_stats()
        txt = f"""
📊 **آمار و گزارشات ربات:**
───────────────
👤 کل کاربران: **{st['total_users']:,}**
💰 کل سکه‌های در گردش: **{st['total_coins']:,}**

📈 **کاربران فعال:**
├ 24 ساعت گذشته: **{st['daily']:,}**
├ 7 روز گذشته: **{st['weekly']:,}**
└ 30 روز گذشته: **{st['monthly']:,}**
        """
        await query.message.edit_text(txt, reply_markup=admin_kb(), parse_mode="Markdown")

    elif data == "admin_toggle_bot" and user.id == ADMIN_ID:
        curr = db.get_setting("bot_status", "on")
        new_s = "off" if curr == "on" else "on"
        db.set_setting("bot_status", new_s)
        await query.answer(f"وضعیت ربات تغییر کرد به: {new_s}", show_alert=True)
        await query.message.edit_text("👑 **پنل مدیریت پیشرفته ادمین:**", reply_markup=admin_kb())

# ============ ۶. مدیریت انتقال سکه با ریپلای ============
async def handle_reply_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg.reply_to_message or not msg.text.startswith("انتقال"):
        return

    sender_id = msg.from_user.id
    target_id = msg.reply_to_message.from_user.id

    if sender_id == target_id:
        await msg.reply_text("❌ نمی‌توانید به خودتان سکه انتقال دهید!")
        return

    try:
        amount = int(msg.text.split()[1])
        if amount <= 0: raise ValueError
    except:
        await msg.reply_text("❌ فرمت نادرست! نمونه صحیح:\n`انتقال 100` (ریپلای روی پیام کاربر)", parse_mode="Markdown")
        return

    if db.remove_coins(sender_id, amount):
        db.add_coins(target_id, amount)
        await msg.reply_text(f"✅ مقدار **{amount:,}** سکه با موفقیت به {msg.reply_to_message.from_user.first_name} منتقل شد.")
    else:
        await msg.reply_text("❌ موجودی سکه شما کافی نیست!")

# ============ ۷. سیستم ادمین (Conversation Handlers) ============
async def admin_give_coins_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.edit_text("🎁 شناسه عددی (User ID) کاربر مورد نظر را بفرستید:")
    return WAITING_ADMIN_GIVE_COIN_ID

async def admin_give_coins_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['target_user'] = int(update.message.text.strip())
    await update.message.reply_text("💰 چه تعداد سکه می‌خواهید اعطا کنید؟ (برای کسر سکه عدد منفی بفرستید):")
    return WAITING_ADMIN_GIVE_COIN_AMT

async def admin_give_coins_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amt = int(update.message.text.strip())
    uid = context.user_data['target_user']
    db.add_coins(uid, amt)
    await update.message.reply_text(f"✅ تعداد **{amt:,}** سکه به کاربر `{uid}` اعمال شد.", reply_markup=admin_kb(), parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# ============ ۸. اجرای اصلی برنامه ============
def main():
    # ۱. اجرای وب‌سرور جهت جلوگیری از اسلیپ شدن Render
    threading.Thread(target=run_web_server, daemon=True).start()

    # ۲. راه‌اندازی دیتابیس PostgreSQL
    db.init_tables()

    # ۳. ساخت ربات تلگرام
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation Handler جهت هدیه سکه ادمین
    give_coin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_give_coins_start, pattern="^admin_give_coins$")],
        states={
            WAITING_ADMIN_GIVE_COIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_coins_id)],
            WAITING_ADMIN_GIVE_COIN_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_coins_amt)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(give_coin_conv)
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & filters.REPLY, handle_reply_transfer))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("🚀 Bot running successfully on Render Environment...")
    app.run_polling()

if __name__ == "__main__":
    main()
