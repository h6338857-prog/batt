"""
🎮 Telegram Game Bot - نسخه 2.0 با کانال قابل تغییر
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ConversationHandler, MessageHandler, filters, ContextTypes
)
from datetime import datetime, timedelta
import random
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

# ============ تنظیمات ============
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv('BOT_TOKEN', '8949103823:AAHFzGSkqwY72yCLDZuDMBJacs8TBvirg-Q')
ADMIN_ID = int(os.getenv('7903625318', '0'))
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://telegram_bot_db_7mx4_user:03C0t0vnZvGT5k9FmUqtx01L9HCW1Ng0@dpg-dahjf6u7bikc73eevhgg-a/telegram_bot_db_7mx4')

# تنظیمات بازی
TAF_REWARD_MIN = 10
TAF_REWARD_MAX = 25
SLOT_COST = 10
DICE_COST = 20
COIN_COST = 15
NICKNAME_COST = 5000
BROADCAST_COST = 50000

# States
GIFT_USER, GIFT_AMOUNT = range(2)
TRANSFER_USER, TRANSFER_AMOUNT = range(2)
SET_CHANNEL_NAME, SET_CHANNEL_ID = range(2)

# ============ کلاس دیتابیس ============

class GameDB:
    def __init__(self, db_url):
        self.db_url = db_url
    
    def get_connection(self):
        return psycopg2.connect(self.db_url)
    
    def init_tables(self):
        """ساخت جداول"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
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
                coins BIGINT DEFAULT 1000,
                xp BIGINT DEFAULT 0,
                level INT DEFAULT 1,
                taf_level INT DEFAULT 1,
                taf_reward INT DEFAULT 10,
                taf_upgrade_cost INT DEFAULT 100,
                nickname VARCHAR(255),
                joined_mandatory_channel BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                last_daily_reward TIMESTAMP,
                banned BOOLEAN DEFAULT FALSE
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS game_results (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                game_type VARCHAR(50),
                bet INT,
                won BOOLEAN,
                reward INT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                from_user BIGINT REFERENCES users(user_id),
                to_user BIGINT REFERENCES users(user_id),
                amount BIGINT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS admin_logs (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT,
                action VARCHAR(255),
                target_user BIGINT,
                amount INT,
                timestamp TIMESTAMP DEFAULT NOW()
            );
            """
        ]
        
        for query in queries:
            try:
                cursor.execute(query)
            except psycopg2.Error:
                pass
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # اضافه کردن تنظیمات پیش‌فرض
        self.set_setting("mandatory_channel", "@default_channel")
        self.set_setting("mandatory_channel_id", "-100123456789")
        self.set_setting("bot_enabled", "true")
    
    def set_setting(self, key, value):
        """ذخیره تنظیمات"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
            (key, value, value)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
    
    def get_setting(self, key, default=None):
        """دریافت تنظیمات"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return result[0] if result else default
    
    def get_or_create_user(self, user_id, username=None):
        """دریافت یا ایجاد کاربر"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            cursor.execute(
                "INSERT INTO users (user_id, username) VALUES (%s, %s) RETURNING *",
                (user_id, username)
            )
            user = cursor.fetchone()
            conn.commit()
        
        cursor.close()
        conn.close()
        return dict(user) if user else None
    
    def add_coins(self, user_id, amount):
        """افزودن سکه"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET coins = coins + %s WHERE user_id = %s", (amount, user_id))
        conn.commit()
        cursor.close()
        conn.close()
    
    def remove_coins(self, user_id, amount):
        """کاهش سکه"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT coins FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        
        if result and result[0] >= amount:
            cursor.execute("UPDATE users SET coins = coins - %s WHERE user_id = %s", (amount, user_id))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        
        cursor.close()
        conn.close()
        return False
    
    def add_xp(self, user_id, amount):
        """افزودن XP"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT xp FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if user:
            new_xp = user[0] + amount
            new_level = 1
            if new_xp >= 500:
                new_level = 2
            if new_xp >= 1500:
                new_level = 3
            if new_xp >= 3500:
                new_level = 4
            
            cursor.execute("UPDATE users SET xp = %s, level = %s WHERE user_id = %s", 
                          (new_xp, new_level, user_id))
            conn.commit()
        
        cursor.close()
        conn.close()
    
    def upgrade_taf(self, user_id):
        """ارتقاء تف"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT taf_level, taf_upgrade_cost, coins FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if user and user[2] >= user[1]:
            new_taf_level = user[0] + 1
            new_reward = 10 + (new_taf_level * 5)
            new_cost = user[1] + 50
            
            cursor.execute(
                "UPDATE users SET taf_level = %s, taf_reward = %s, taf_upgrade_cost = %s, coins = coins - %s WHERE user_id = %s",
                (new_taf_level, new_reward, new_cost, user[1], user_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            return True
        
        cursor.close()
        conn.close()
        return False
    
    def get_leaderboard(self, limit=10):
        """دریافت لیدربورد"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute(
            "SELECT user_id, username, coins, level, xp FROM users WHERE banned = FALSE ORDER BY coins DESC LIMIT %s",
            (limit,)
        )
        
        result = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return result
    
    def record_game(self, user_id, game_type, bet, won, reward):
        """ثبت نتیجه بازی"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO game_results (user_id, game_type, bet, won, reward) VALUES (%s, %s, %s, %s, %s)",
            (user_id, game_type, bet, won, reward)
        )
        conn.commit()
        cursor.close()
        conn.close()
    
    def transfer_coins(self, from_user, to_user, amount):
        """انتقال سکه"""
        if not self.remove_coins(from_user, amount):
            return False
        
        self.add_coins(to_user, amount)
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO transactions (from_user, to_user, amount) VALUES (%s, %s, %s)",
            (from_user, to_user, amount)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    
    def get_stats(self, user_id):
        """دریافت آمار کاربر"""
        conn = self.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        cursor.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN won THEN 1 ELSE 0 END) as wins FROM game_results WHERE user_id = %s",
            (user_id,)
        )
        games = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return {
            "user": dict(user) if user else None,
            "games": dict(games) if games else {"total": 0, "wins": 0}
        }
    
    def admin_give_coins(self, admin_id, target_user, amount):
        """ادمین هدیه سکه می‌دهد"""
        self.add_coins(target_user, amount)
        
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admin_logs (admin_id, action, target_user, amount) VALUES (%s, %s, %s, %s)",
            (admin_id, "give_coins", target_user, amount)
        )
        conn.commit()
        cursor.close()
        conn.close()
    
    def mark_channel_joined(self, user_id):
        """علامت‌گذاری جوین کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET joined_mandatory_channel = TRUE WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
    
    def has_joined_channel(self, user_id):
        """بررسی جوین کردن به کانال"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT joined_mandatory_channel FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else False

# ============ کتابخانه صفحه کلید ============

def main_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👤 پروفایل", callback_data="profile"),
            InlineKeyboardButton("🎮 بازی‌ها", callback_data="games")
        ],
        [
            InlineKeyboardButton("🛍️ فروشگاه", callback_data="shop"),
            InlineKeyboardButton("🏆 لیدربورد", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton("🎁 جوایز روزانه", callback_data="daily_reward"),
            InlineKeyboardButton("ℹ️ راهنما", callback_data="help")
        ]
    ])

def games_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"🎰 گردونه ({SLOT_COST})", callback_data="play_slot"),
            InlineKeyboardButton(f"🎲 تاس ({DICE_COST})", callback_data="play_dice")
        ],
        [InlineKeyboardButton(f"🪙 شیر/خط ({COIN_COST})", callback_data="play_coin")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
    ])

def shop_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬆️ ارتقاء تف", callback_data="upgrade_taf"),
            InlineKeyboardButton("✨ لقب خاص", callback_data="buy_nickname")
        ],
        [
            InlineKeyboardButton("💸 انتقال سکه", callback_data="transfer_coins"),
            InlineKeyboardButton("📢 پیام همگانی", callback_data="broadcast_msg")
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
    ])

def admin_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎁 هدیه سکه", callback_data="admin_gift"),
            InlineKeyboardButton("📊 آمار", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings"),
            InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")
        ]
    ])

def settings_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 تغییر کانال", callback_data="change_channel")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panel")]
    ])

def channel_keyboard():
    channel = db.get_setting("mandatory_channel", "@channel").replace("@", "")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 جوین کانال", url=f"https://t.me/{channel}")]
    ])

# ============ Handler ها ============

db = GameDB(DATABASE_URL)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فرمان /start"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    user_data = db.get_or_create_user(user.id, user.username)
    
    mandatory_channel = db.get_setting("mandatory_channel", "@channel")
    mandatory_channel_id = int(db.get_setting("mandatory_channel_id", "-100123456789"))
    
    if not db.has_joined_channel(user.id):
        text = f"""
سلام {user.first_name} 👋

برای استفاده از ربات، لازم است به کانال جوین شوی:

🔗 [{mandatory_channel}]({mandatory_channel})

بعد از جوین، دوباره /start رو بزن 🚀
"""
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=channel_keyboard(),
            parse_mode="Markdown"
        )
        
        try:
            member = await context.bot.get_chat_member(mandatory_channel_id, user.id)
            if member.status in ['member', 'administrator', 'creator']:
                db.mark_channel_joined(user.id)
        except:
            pass
        
        return
    
    text = f"""
🎮 **خوش‌آمدید!**

سلام {user.first_name}! 

💰 سکه‌های شما: {user_data['coins']}
🏅 سطح: {user_data['level']}
⭐ XP: {user_data['xp']}

بیایید شروع کنیم! 🚀
"""
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler کلی برای دکمه‌ها"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # منوی اصلی
    if query.data == "main_menu":
        text = "📌 **منوی اصلی**\n\nبه منوی اصلی خوش‌آمدی!"
        await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode="Markdown")
    
    # ادمین پنل
    elif query.data == "admin_panel" and user_id == ADMIN_ID:
        text = "⚙️ **پنل ادمین**"
        await query.edit_message_text(text, reply_markup=admin_keyboard(), parse_mode="Markdown")
    
    # تنظیمات ادمین
    elif query.data == "admin_settings" and user_id == ADMIN_ID:
        text = "⚙️ **تنظیمات**"
        await query.edit_message_text(text, reply_markup=settings_keyboard(), parse_mode="Markdown")
    
    # تغییر کانال
    elif query.data == "change_channel" and user_id == ADMIN_ID:
        context.user_data['change_channel_step'] = 1
        await query.edit_message_text("📢 **تغییر کانال**\n\nیوزرنیم کانال رو بنویس (مثل: @mychannel):")
    
    # پروفایل
    elif query.data == "profile":
        user_data = db.get_or_create_user(user_id)
        stats = db.get_stats(user_id)
        
        level_name = ["", "🥉 برنزی", "🥈 نقره‌ای", "🥇 طلایی", "💎 الماس"][user_data['level']]
        
        text = f"""
👤 **پروفایل {update.effective_user.first_name}**

💰 **سکه‌ها:** {user_data['coins']:,}
⭐ **XP:** {user_data['xp']:,}
🏅 **سطح:** {level_name}

**تف:**
├─ سطح: {user_data['taf_level']}
├─ پاداش: {user_data['taf_reward']} سکه
└─ هزینه ارتقاء: {user_data['taf_upgrade_cost']} سکه

🎮 **آمار:**
├─ کل بازی: {stats['games'].get('total', 0)}
└─ برد: {stats['games'].get('wins', 0)}
"""
        await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode="Markdown")
    
    # بازی‌ها
    elif query.data == "games":
        await query.edit_message_text("🎮 **انتخاب بازی**:", reply_markup=games_keyboard())
    
    # گردونه شانس
    elif query.data == "play_slot":
        user_data = db.get_or_create_user(user_id)
        
        if user_data['coins'] < SLOT_COST:
            await query.answer(f"❌ نیاز: {SLOT_COST} سکه", show_alert=True)
            return
        
        db.remove_coins(user_id, SLOT_COST)
        
        emojis = ["🍎", "🍊", "🍋", "🍌", "🍇"]
        result = [random.choice(emojis) for _ in range(3)]
        
        reward = 0
        won = False
        
        if result[0] == result[1] == result[2]:
            reward = SLOT_COST * 10
            won = True
        elif result[0] == result[1] or result[1] == result[2]:
            reward = SLOT_COST * 3
            won = True
        else:
            reward = SLOT_COST // 2
        
        db.add_coins(user_id, reward)
        db.record_game(user_id, "slot", SLOT_COST, won, reward)
        db.add_xp(user_id, 5)
        
        text = f"""
🎰 **نتیجه‌ی گردونه:**

{result[0]} {result[1]} {result[2]}

{'🎉 **برد!**' if won else '❌ **باخت!**'}
💰 جایزه: +{reward} سکه
"""
        await query.edit_message_text(text, reply_markup=games_keyboard(), parse_mode="Markdown")
    
    # تاس
    elif query.data == "play_dice":
        user_data = db.get_or_create_user(user_id)
        
        if user_data['coins'] < DICE_COST:
            await query.answer(f"❌ نیاز: {DICE_COST} سکه", show_alert=True)
            return
        
        db.remove_coins(user_id, DICE_COST)
        
        your_roll = random.randint(1, 6)
        bot_roll = random.randint(1, 6)
        
        reward = 0
        won = False
        
        if your_roll > bot_roll:
            reward = DICE_COST * 2
            won = True
        elif your_roll == bot_roll:
            reward = DICE_COST
            won = True
        else:
            reward = DICE_COST // 3
        
        db.add_coins(user_id, reward)
        db.record_game(user_id, "dice", DICE_COST, won, reward)
        db.add_xp(user_id, 5)
        
        text = f"""
🎲 **نتیجه‌ی تاس:**

تو: {your_roll}
ربات: {bot_roll}

{'✅ **برد!**' if your_roll > bot_roll else '❌ **باخت!**' if your_roll < bot_roll else '🤝 **مساوی!**'}
💰 جایزه: +{reward} سکه
"""
        await query.edit_message_text(text, reply_markup=games_keyboard(), parse_mode="Markdown")
    
    # شیر یا خط
    elif query.data == "play_coin":
        user_data = db.get_or_create_user(user_id)
        
        if user_data['coins'] < COIN_COST:
            await query.answer(f"❌ نیاز: {COIN_COST} سکه", show_alert=True)
            return
        
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🪙 شیر", callback_data="coin_heads"),
                InlineKeyboardButton("📄 خط", callback_data="coin_tails")
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="games")]
        ])
        
        await query.edit_message_text("🪙 **انتخاب کن:**", reply_markup=keyboard)
    
    elif query.data.startswith("coin_"):
        user_data = db.get_or_create_user(user_id)
        
        if user_data['coins'] < COIN_COST:
            await query.answer(f"❌ نیاز: {COIN_COST} سکه", show_alert=True)
            return
        
        choice = query.data.split("_")[1]
        result = random.choice(["heads", "tails"])
        
        db.remove_coins(user_id, COIN_COST)
        
        won = choice == result
        reward = COIN_COST * 2 if won else 0
        
        db.add_coins(user_id, reward)
        db.record_game(user_id, "coin", COIN_COST, won, reward)
        db.add_xp(user_id, 5)
        
        choice_emoji = "🪙 شیر" if choice == "heads" else "📄 خط"
        result_emoji = "🪙 شیر" if result == "heads" else "📄 خط"
        
        text = f"""
🪙 **نتیجه‌ی سکه:**

انتخاب تو: {choice_emoji}
نتیجه: {result_emoji}

{'✅ **برد!**' if won else '❌ **باخت!**'}
💰 جایزه: +{reward} سکه
"""
        await query.edit_message_text(text, reply_markup=games_keyboard(), parse_mode="Markdown")
    
    # فروشگاه
    elif query.data == "shop":
        await query.edit_message_text("🛍️ **فروشگاه**:", reply_markup=shop_keyboard())
    
    # ارتقاء تف
    elif query.data == "upgrade_taf":
        user_data = db.get_or_create_user(user_id)
        
        if user_data['coins'] < user_data['taf_upgrade_cost']:
            await query.answer(f"❌ نیاز: {user_data['taf_upgrade_cost']} سکه", show_alert=True)
            return
        
        if db.upgrade_taf(user_id):
            user_data = db.get_or_create_user(user_id)
            text = f"""
✅ **ارتقاء موفق!**

🔼 سطح جدید: {user_data['taf_level']}
💰 پاداش جدید: {user_data['taf_reward']} سکه
📈 هزینه ارتقاء بعدی: {user_data['taf_upgrade_cost']} سکه
"""
            await query.edit_message_text(text, reply_markup=shop_keyboard(), parse_mode="Markdown")
    
    # لیدربورد
    elif query.data == "leaderboard":
        users = db.get_leaderboard(limit=10)
        
        text = "🏆 **لیدربورد - 10 نفر برتر**\n\n"
        
        for idx, user in enumerate(users, 1):
            medal = ["🥇", "🥈", "🥉"]
            medal_emoji = medal[idx - 1] if idx <= 3 else f"#{idx}"
            
            text += f"{medal_emoji} **{user['username'] or 'کاربر'}** - {user['coins']:,} سکه\n"
        
        await query.edit_message_text(text, reply_markup=main_keyboard(), parse_mode="Markdown")
    
    # جایزه روزانه
    elif query.data == "daily_reward":
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT last_daily_reward FROM users WHERE user_id = %s", (user_id,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        last_reward = result[0] if result else None
        
        if last_reward and last_reward.date() == datetime.now().date():
            await query.answer("❌ امروز جایزه گرفتی! فردا دوباره امتحان کن", show_alert=True)
            return
        
        reward = random.randint(100, 500)
        db.add_coins(user_id, reward)
        
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_daily_reward = NOW() WHERE user_id = %s", (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        
        await query.answer(f"🎉 +{reward} سکه جایزه روزانه!", show_alert=True)
    
    # منتقل کردن سکه
    elif query.data == "transfer_coins":
        context.user_data['in_transfer'] = True
        context.user_data['transfer_step'] = 1
        await query.edit_message_text("💸 **انتقال سکه**\n\nآیدی کاربر مقصد رو بنویس:")
    
    # هدیه ادمین
    elif query.data == "admin_gift" and user_id == ADMIN_ID:
        context.user_data['gift_step'] = 1
        await query.edit_message_text("🎁 **هدیه سکه**\n\nآیدی کاربر رو بنویس:")
    
    # آمار ادمین
    elif query.data == "admin_stats" and user_id == ADMIN_ID:
        conn = db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM users WHERE banned = FALSE")
        total_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(coins) FROM users")
        total_coins = cursor.fetchone()[0] or 0
        
        cursor.close()
        conn.close()
        
        text = f"""
📊 **آمار جهانی**

👥 کاربران: {total_users}
💰 سکه‌های کل: {total_coins:,}
"""
        await query.edit_message_text(text, reply_markup=admin_keyboard(), parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler برای پیام‌های متنی"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # تغییر کانال ادمین
    if user_id == ADMIN_ID and context.user_data.get('change_channel_step') == 1:
        if text.startswith("@"):
            db.set_setting("mandatory_channel", text)
            await update.message.reply_text(f"✅ کانال به {text} تغییر یافت")
            context.user_data['change_channel_step'] = 2
            await update.message.reply_text("🔢 حالا آیدی کانال رو بنویس (مثل: -100123456789):")
        else:
            await update.message.reply_text("❌ فرمت اشتباه! با @ شروع کن")
    
    elif user_id == ADMIN_ID and context.user_data.get('change_channel_step') == 2:
        try:
            channel_id = int(text)
            db.set_setting("mandatory_channel_id", str(channel_id))
            await update.message.reply_text(f"✅ آیدی کانال به {channel_id} تغییر یافت")
            context.user_data['change_channel_step'] = 0
        except:
            await update.message.reply_text("❌ آیدی غلط!")
    
    # هدیه سکه ادمین
    elif user_id == ADMIN_ID and context.user_data.get('gift_step') == 1:
        try:
            target_user = int(text)
            context.user_data['gift_target'] = target_user
            context.user_data['gift_step'] = 2
            await update.message.reply_text("💰 **مقدار سکه** رو بنویس:")
        except:
            await update.message.reply_text("❌ آیدی غلط!")
    
    elif user_id == ADMIN_ID and context.user_data.get('gift_step') == 2:
        try:
            amount = int(text)
            target = context.user_data.get('gift_target')
            db.admin_give_coins(user_id, target, amount)
            
            await update.message.reply_text(f"✅ {amount} سکه برای {target} فرستاده شد")
            
            try:
                await context.bot.send_message(
                    chat_id=target,
                    text=f"🎁 **هدیه ادمین!**\n\n+{amount} سکه 🎉"
                )
            except:
                pass
            
            context.user_data['gift_step'] = 0
        except:
            await update.message.reply_text("❌ مقدار غلط!")
    
    # انتقال سکه
    elif context.user_data.get('transfer_step') == 1:
        try:
            target_user = int(text)
            context.user_data['transfer_target'] = target_user
            context.user_data['transfer_step'] = 2
            await update.message.reply_text("💰 **مقدار سکه** رو بنویس:")
        except:
            await update.message.reply_text("❌ آیدی غلط!")
    
    elif context.user_data.get('transfer_step') == 2:
        try:
            amount = int(text)
            target = context.user_data.get('transfer_target')
            
            if db.transfer_coins(user_id, target, amount):
                await update.message.reply_text(f"✅ {amount} سکه برای {target} منتقل شد")
                
                try:
                    await context.bot.send_message(
                        chat_id=target,
                        text=f"💰 **سکه دریافت کردی!**\n\n+{amount} سکه از {user_id}"
                    )
                except:
                    pass
            else:
                await update.message.reply_text("❌ سکه کافی ندارید!")
            
            context.user_data['transfer_step'] = 0
        except:
            await update.message.reply_text("❌ مقدار غلط!")

async def post_init(app: Application) -> None:
    """بعد از اینیشیالیزیشن"""
    db.init_tables()
    print("✅ Database initialized!")

def main():
    """اجرای ربات"""
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(button_handler))
    
    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
