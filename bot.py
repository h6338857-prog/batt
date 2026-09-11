"""
🤖 Telegram Advanced Game & Casino Bot
Integrated Configs & Anti-Sleep Web Server
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

# ==================== تنظیمات مستقیم و لاگ‌ها ====================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# اطلاعات قرار داده شده توسط کاربر
BOT_TOKEN = "8949103823:AAHFzGSkqwY72yCLDZuDMBJacs8TBvirg-Q"
ADMIN_ID = 7903625318
DATABASE_URL = "postgresql://telegram_bot_db_7mx4_user:03C0t0vnZvGT5k9FmUqtx01L9HCW1Ng0@dpg-dahjf6u7bikc73eevhgg-a/telegram_bot_db_7mx4"

# اصلاح احتمالی پروتکل postgres برای psycopg2
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# استیت‌های گفتگو (Conversation States)
(
    WAITING_ADMIN_CHANNEL, WAITING_ADMIN_GIVE_COIN_ID, WAITING_ADMIN_GIVE_COIN_AMT
) = range(3)

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
                last_daily TIMESTAMP DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        ]
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                for q in queries:
                    cur.execute(q)

        defaults = {
            "mandatory_channel": "OFF",
            "bot_status": "on",
            "welcome_msg": "سلام! به ربات پیشرفته بازی و کازینو خوش آمدید!",
            "rules_msg": "قوانین ربات:\n۱. احترام به سایر کاربران\n۲. عدم استفاده از ابزارهای تقلب یا اسپم",
            "cost_slot": "10",
            "cost_dice": "20",
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

    def upgrade_taf(self, user_id, cost):
        if self.remove_coins(user_id, cost):
            with self.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE users SET taf_level = taf_level + 1 WHERE user_id = %s", (user_id,))
            return True
        return False

    def claim_daily(self, user_id):
        u = self.get_or_create_user(user_id)
        last_d = u['last_daily']
        now = datetime.now()
        if last_d and (now - last_d) < timedelta(hours=24):
            remaining = timedelta(hours=24) - (now - last_d)
            hours, remainder = divmod(remaining.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            return False, f"{hours} ساعت و {minutes} دقیقه"
        
        bonus = random.randint(100, 300)
        with self.get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET coins = coins + %s, last_daily = NOW() WHERE user_id = %s", (bonus, user_id))
        return True, bonus

    def get_top_users(self, limit=10):
        with self.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT first_name, coins FROM users ORDER BY coins DESC LIMIT %s", (limit,))
                return cur.fetchall()

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
                return {
                    "total_users": total_users or 0,
                    "total_coins": total_coins or 0,
                    "daily": daily
                }

db = None

# ==================== ۳. ابزارهای کمکی ====================
async def check_channel_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    channel = db.get_setting("mandatory_channel", "OFF")
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
        [InlineKeyboardButton("🎁 پاداش روزانه", callback_data="daily_bonus"), InlineKeyboardButton("🎮 سرگرمی‌ها", callback_data="mini_games")],
        [InlineKeyboardButton("📜 راهنما", callback_data="help"), InlineKeyboardButton("📜 قوانین", callback_data="rules")]
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton("👑 پنل مدیریت ادمین", callback_data="admin_main")])
    return InlineKeyboardMarkup(kb)

def admin_kb():
    bot_status = db.get_setting("bot_status", "on")
    channel = db.get_setting("mandatory_channel", "OFF")
    status_icon = "🟢 روشن" if bot_status == "on" else "🔴 خاموش"
    ch_text = channel if channel != "OFF" else "🔴 غیرفعال"
    
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 آمار جامع", callback_data="admin_stats"), InlineKeyboardButton(f"وضعیت ربات: {status_icon}", callback_data="admin_toggle_bot")],
        [InlineKeyboardButton(f"📢 کانال اجباری: {ch_text}", callback_data="admin_set_channel_start")],
        [InlineKeyboardButton("🎁 اهدا سکه دستی", callback_data="admin_give_coins")],
        [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="main_menu")]
    ])

# ==================== ۵. هندرها ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.get_or_create_user(user.id, user.username, user.first_name)

    if db.get_setting("bot_status") == "off" and user.id != ADMIN_ID:
        await update.message.reply_text("🔴 ربات در حال حاضر جهت بروزرسانی خاموش می‌باشد.")
        return

    welcome_msg = db.get_setting("welcome_msg")
    await update.message.reply_text(f"{welcome_msg}\n\nاز منوی زیر استفاده کنید:", reply_markup=main_kb(user.id))

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    
    if db.get_setting("bot_status") == "off" and user.id != ADMIN_ID:
        return

    db.inc_msg_count(user.id)

    if text == "پروفایل":
        u = db.get_or_create_user(user.id)
        rank = db.get_user_rank(user.id)
        level = get_user_level(u['coins'])
        profile_text = (
            f"👤 **پروفایل کاربری**\n───────────────\n"
            f"🏷️ نام/لقب: **{u['first_name']}**\n"
            f"💰 سکه‌ها: **{u['coins']:,}**\n"
            f"🏅 سطح: **{level}**\n"
            f"📊 تعداد پیام‌ها: **{u['msg_count']:,}**\n"
            f"🏆 رتبه شما: **#{rank}**"
        )
        await update.message.reply_text(profile_text, parse_mode="Markdown")
        return

    if "تف" in text:
        if not await check_channel_member(context, user.id):
            ch = db.get_setting("mandatory_channel")
            url = f"https://t.me/{ch.replace('@', '')}"
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 جوین در کانال", url=url)],
                [InlineKeyboardButton("✅ جوین شدم", callback_data="check_join")]
            ])
                await update.message.reply_text(f"⚠️ **برای دریافت سکه رایگان باید ابتدا در کانال زیر عضو شوید:**\n{ch}", reply_markup=kb, parse_mode="Markdown")
            return

        u = db.get_or_create_user(user.id)
        taf_level = u['taf_level']
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
            await query.message.edit_text("✅ عضویت شما تایید شد! حالا می‌توانید کلمه «تف» را بفرستید.", reply_markup=main_kb(user.id))
        else:
            await query.answer("❌ هنوز در کانال عضو نشده‌اید!", show_alert=True)
        return

    if data == "main_menu":
        await query.message.edit_text("📌 **منوی اصلی:**", reply_markup=main_kb(user.id), parse_mode="Markdown")

    elif data == "profile":
        u = db.get_or_create_user(user.id)
        rank = db.get_user_rank(user.id)
        level = get_user_level(u['coins'])
        p_text = f"👤 **پروفایل شما**\n\n🏷️ نام: {u['first_name']}\n💰 سکه‌ها: {u['coins']:,}\n🏅 سطح: {level}\n📊 پیام‌ها: {u['msg_count']}\n🏆 رتبه: #{rank}"
        await query.message.edit_text(p_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    elif data == "daily_bonus":
        success, res = db.claim_daily(user.id)
        if success:
            await query.message.edit_text(f"🎁 **پاداش روزانه:**\n\nتبریک! شما **{res}** سکه پاداش دریافت کردید.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))
        else:
            await query.message.edit_text(f"⏳ **پاداش روزانه:**\n\nشما قبلاً پاداش امروز را گرفته‌اید.\nزمان باقی‌مانده: **{res}**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    elif data == "leaderboard":
        top_users = db.get_top_users(10)
        txt = "🏆 **جدول ۱۰ کاربر برتر بر اساس سکه:**\n\n"
        for idx, u in enumerate(top_users, 1):
            txt += f"{idx}. {u['first_name']} — 💰 **{u['coins']:,}** سکه\n"
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]), parse_mode="Markdown")

    elif data == "mini_games":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎲 تاس شانس", callback_data="play_dice")],
            [InlineKeyboardButton("🪙 شیر یا خط", callback_data="play_coin_flip")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ])
        await query.message.edit_text("🎮 **بخش بازی‌ها و سرگرمی:**", reply_markup=kb)

    elif data == "play_coin_flip":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🪙 شیر", callback_data="flip_head"), InlineKeyboardButton("🪙 خط", callback_data="flip_tail")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="mini_games")]
        ])
        await query.message.edit_text("🎯 **پیش‌بینی کنید:** (هزینه هر بار: ۱۵ سکه)", reply_markup=kb)

    elif data in ["flip_head", "flip_tail"]:
        if not db.remove_coins(user.id, 15):
            await query.answer("❌ سکه کافی ندارید! (هزینه: ۱۵ سکه)", show_alert=True)
            return
        
        choice = "شیر" if data == "flip_head" else "خط"
        outcome = random.choice(["شیر", "خط"])
        won = (choice == outcome)
        
        if won:
            db.add_coins(user.id, 30)
            txt = f"🎉 سکه چرخید و روی **{outcome}** آمد!\nشما برنده **۳۰** سکه شدید!"
        else:
            txt = f"❌ سکه چرخید و روی **{outcome}** آمد!\nمتاسفانه باختید."
            
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 دوباره", callback_data="play_coin_flip"), InlineKeyboardButton("🔙 بازگشت", callback_data="mini_games")]]), parse_mode="Markdown")

    elif data == "help":
        help_text = "📜 **راهنمای ربات:**\n\n• ارسال کلمه **تف** -> دریافت سکه رایگان\n• ارسال کلمه **پروفایل** -> مشاهده آمار کاربر\n• **پاداش روزانه** -> دریافت سکه رایگان هر ۲۴ ساعت\n• **کازینو و بازی‌ها** -> شرط‌بندی و افزایش سکه‌ها"
        await query.message.edit_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    elif data == "rules":
        r = db.get_setting("rules_msg")
        await query.message.edit_text(f"📜 **قوانین ربات:**\n\n{r}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]]))

    elif data == "shop":
        u = db.get_or_create_user(user.id)
        taf_lvl = u['taf_level']
        taf_cost = taf_lvl * 100
        bc_cost = int(db.get_setting("cost_broadcast_perm", "50000"))

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💦 ارتقای تف (سطح {taf_lvl+1}) - {taf_cost} سکه", callback_data="upgrade_taf")],
            [InlineKeyboardButton(f"📢 مجوز ارسال همگانی ({bc_cost:,} سکه)", callback_data="buy_broadcast")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ])
        await query.message.edit_text("🛍️ **به فروشگاه خوش آمدید!**", reply_markup=kb)

    elif data == "upgrade_taf":
        u = db.get_or_create_user(user.id)
        taf_cost = u['taf_level'] * 100
        if db.upgrade_taf(user.id, taf_cost):
            await query.answer("✅ سطح تف شما با موفقیت ارتقا یافت!", show_alert=True)
            await callback_router(update, context) # Refresh shop page
        else:
            await query.answer("❌ سکه کافی ندارید!", show_alert=True)

    elif data == "casino":
        c_slot = db.get_setting("cost_slot", "10")
        c_dice = db.get_setting("cost_dice", "20")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎰 اسلات ماشین ({c_slot} سکه)", callback_data="play_slot")],
            [InlineKeyboardButton(f"🎲 تاس شانس ({c_dice} سکه)", callback_data="play_dice_casino")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ])
        await query.message.edit_text("🎰 **به کازینو خوش آمدید!**", reply_markup=kb)

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

        txt = f"🎰 **گردونه چرخید:**\n\n{' | '.join(res)}\n\n" + (f"🎉 شما **{prize}** سکه برنده شدید!" if won else "❌ باختید.")
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 دوباره", callback_data="play_slot"), InlineKeyboardButton("🔙 بازگشت", callback_data="casino")]]))

    elif data == "play_dice_casino":
        cost = int(db.get_setting("cost_dice", "20"))
        if not db.remove_coins(user.id, cost):
            await query.answer("❌ سکه کافی ندارید!", show_alert=True)
            return
            
        user_dice = random.randint(1, 6)
        bot_dice = random.randint(1, 6)
        
        if user_dice > bot_dice:
            prize = cost * 2
            db.add_coins(user.id, prize)
            res_txt = f"🎉 شما برنده شدید و **{prize}** سکه گرفتید!"
        elif user_dice < bot_dice:
            res_txt = "❌ شما باختید."
        else:
            db.add_coins(user.id, cost)
            res_txt = "🤝 مساوی شدید! سکه شما بازگردانده شد."

        txt = f"🎲 **بازی تاس:**\n\n🎲 تاس شما: **{user_dice}**\n🎲 تاس ربات: **{bot_dice}**\n\n{res_txt}"
        await query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 دوباره", callback_data="play_dice_casino"), InlineKeyboardButton("🔙 بازگشت", callback_data="casino")]]), parse_mode="Markdown")

    # ========= دسترسی اختصاصی ادمین بدون هیچ تغییری =========
    elif data == "admin_main" and user.id == ADMIN_ID:
        await query.message.edit_text("👑 **پنل مدیریت ادمین:**", reply_markup=admin_kb(), parse_mode="Markdown")

    elif data == "admin_stats" and user.id == ADMIN_ID:
        st = db.get_stats()
        txt = f"📊 **آمار:**\n\n👤 کاربران: **{st['total_users']:,}**\n💰 کل سکه‌ها: **{st['total_coins']:,}**\n🟢 فعال ۲۴ ساعت گذشته: **{st['daily']:,}**"
        await query.message.edit_text(txt, reply_markup=admin_kb(), parse_mode="Markdown")

    elif data == "admin_toggle_bot" and user.id == ADMIN_ID:
        curr = db.get_setting("bot_status", "on")
        new_s = "off" if curr == "on" else "on"
        db.set_setting("bot_status", new_s)
        await query.answer(f"وضعیت ربات: {new_s}", show_alert=True)
        await query.message.edit_text("👑 **پنل مدیریت ادمین:**", reply_markup=admin_kb())

# ============ ۶. گفتگوهای ادمین ============
async def admin_set_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.answer()
    
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("❌ غیرفعال کردن جوین اجباری", callback_data="admin_disable_channel")]])
    await q.message.edit_text("📢 **آیدی کانال را با @ بفرستید** (مثال: `@MyChannel`):\n\nبرای خاموش کردن، دکمه زیر را بزنید:", reply_markup=kb, parse_mode="Markdown")
    return WAITING_ADMIN_CHANNEL

async def admin_set_channel_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ch = update.message.text.strip()
    if not ch.startswith("@"):
        await update.message.reply_text("❌ آیدی کانال باید با @ شروع شود! دوباره بفرستید:")
        return WAITING_ADMIN_CHANNEL
        
    db.set_setting("mandatory_channel", ch)
    await update.message.reply_text(f"✅ کانال اجباری روی **{ch}** تنظیم شد.\n⚠️ مطمئن شوید ربات در این کانال **ادمین (Admin)** باشد.", reply_markup=admin_kb(), parse_mode="Markdown")
    return ConversationHandler.END

async def admin_disable_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    db.set_setting("mandatory_channel", "OFF")
    await q.message.edit_text("✅ قابلیت جوین اجباری غیرفعال شد.", reply_markup=admin_kb())
    return ConversationHandler.END

async def admin_give_coins_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: return ConversationHandler.END
    await q.answer()
    await q.message.edit_text("🎁 شناسه عددی (User ID) کاربر را بفرستید:")
    return WAITING_ADMIN_GIVE_COIN_ID

async def admin_give_coins_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['target_user'] = int(update.message.text.strip())
        await update.message.reply_text("💰 چه تعداد سکه می‌خواهید اعطا کنید؟:")
        return WAITING_ADMIN_GIVE_COIN_AMT
    except ValueError:
        await update.message.reply_text("❌ لطفاً یک شناسه عددی معتبر بفرستید:")
        return WAITING_ADMIN_GIVE_COIN_ID

async def admin_give_coins_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amt = int(update.message.text.strip())
        uid = context.user_data['target_user']
        db.add_coins(uid, amt)
        await update.message.reply_text(f"✅ تعداد **{amt:,}** سکه به کاربر `{uid}` اعطا شد.", reply_markup=admin_kb(), parse_mode="Markdown")
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ لطفاً تعداد سکه را به صورت عدد بفرستید:")
        return WAITING_ADMIN_GIVE_COIN_AMT

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ عملیات لغو شد.")
    return ConversationHandler.END

# ============ ۷. اجرای اصلی ============
def main():
    global db
    db = Database(DATABASE_URL)
    db.init_tables()

    # وب سرور همزمان در ترپ مستقل
    threading.Thread(target=run_web_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    # گفتگوی تنظیم کانال ادمین
    set_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_set_channel_start, pattern="^admin_set_channel_start$")],
        states={
            WAITING_ADMIN_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_channel_save),
                CallbackQueryHandler(admin_disable_channel, pattern="^admin_disable_channel$")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    # گفتگوی اهدا سکه ادمین
    give_coin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_give_coins_start, pattern="^admin_give_coins$")],
        states={
            WAITING_ADMIN_GIVE_COIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_coins_id)],
            WAITING_ADMIN_GIVE_COIN_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_give_coins_amt)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conv)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(set_channel_conv)
    app.add_handler(give_coin_conv)
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    print("🚀 Bot is running successfully...")
    app.run_polling()

if __name__ == "__main__":
    main()
