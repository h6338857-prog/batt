import json
import logging
import os
import random
import threading
import time
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== تنظیمات وب‌سرور برای Render ====================
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Taf Bot is running online 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port)

# ==================== تنظیمات ربات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8598701713:AAHslvNMyv5DQ8J1p7mZ8haAOGef9QVRxB4") # توکن یا از محیط سیستم خوانده می‌شود یا اینجا ست کنید
INITIAL_ADMIN_ID = int(os.environ.get("ADMIN_ID", 987654321)) # آیدی عددی ادمین اصلی

DB_FILE = "taf_bot_db.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ==================== مدیریت دیتابیس ====================
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "users": {},           # {user_id: {"name": str, "points": int, "last_taf": float, "last_casino": float, "last_daily": float}}
        "admins": [INITIAL_ADMIN_ID],
        "mandatory_channels": [],
        "groups": [],
        "bot_active": True
    }

def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

db = load_data()

# ==================== توابع کمکی ====================
async def check_mandatory_join(user_id: int, bot) -> bool:
    if not db.get("mandatory_channels"):
        return True
    for channel in db["mandatory_channels"]:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logging.warning(f"کسب وضعیت کاربر در کانال {channel} ناموفق بود: {e}")
            return False
    return True

def format_time(seconds: int) -> str:
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours > 0:
        return f"{hours} ساعت و {mins} دقیقه"
    elif mins > 0:
        return f"{mins} دقیقه و {secs} ثانیه"
    return f"{secs} ثانیه"

# ==================== پنل مدیریت شیشه‌ای ====================
def get_admin_keyboard():
    status_icon = "🟢" if db.get("bot_active", True) else "🔴"
    status_text = "خاموش کردن ربات ⛔" if db.get("bot_active", True) else "روشن کردن ربات ✅"
    
    keyboard = [
        [
            InlineKeyboardButton("🏆 ۱۰ کاربر برتر", callback_data="admin_top"),
            InlineKeyboardButton("📢 جوین اجباری", callback_data="admin_channel")
        ],
        [
            InlineKeyboardButton("📨 پیام همگانی به گروه‌ها", callback_data="admin_broadcast"),
            InlineKeyboardButton("➕ افزودن ادمین", callback_data="admin_add_admin")
        ],
        [
            InlineKeyboardButton("🎁 مدیریت امتیاز کاربر", callback_data="admin_manage_points"),
            InlineKeyboardButton(f"{status_icon} {status_text}", callback_data="admin_toggle_bot")
        ],
        [
            InlineKeyboardButton("📊 آمار کامل ربات", callback_data="admin_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== هندلرهای ربات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type

    if chat_type == "private":
        if user_id in db["admins"]:
            await update.message.reply_text(
                "👑 **سلام مدیر گرامی! به پنل مدیریت شیشه‌ای ربات تف خوش آمدید.**",
                reply_markup=get_admin_keyboard(),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "سلام! 👋\nمن ربات تف و گپ‌بازی هستم. من رو به گروهت اضافه کن تا بازی کنیم!"
            )

async def handle_group_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user = update.effective_user
    user_id = str(user.id)
    text = update.message.text.strip()

    # ثبت گروه
    if chat_id not in db["groups"]:
        db["groups"].append(chat_id)
        save_data(db)

    if not db.get("bot_active", True):
        return

    # ایجاد پروفایل کاربر در دیتابیس
    if user_id not in db["users"]:
        db["users"][user_id] = {
            "name": user.full_name,
            "points": 0,
            "last_taf": 0,
            "last_casino": 0,
            "last_daily": 0
        }
    else:
        db["users"][user_id]["name"] = user.full_name

    now = time.time()

    # ۱. سیستم تف 🤧
    if "تف" in text:
        is_joined = await check_mandatory_join(user.id, context.bot)
        if not is_joined:
            channels = "\n".join(db["mandatory_channels"])
            await update.message.reply_text(
                f"⚠️ {user.first_name} عزیز، برای دریافت امتیاز ابتدا باید در کانال‌های زیر عضو بشی:\n{channels}"
            )
            return

        last_taf = db["users"][user_id].get("last_taf", 0)
        time_diff = now - last_taf

        if time_diff < 60:
            remaining = int(60 - time_diff)
            await update.message.reply_text(f"🤧 تفاتو جمع کن! هنوز {remaining} ثانیه از تف قبلیت نگذشته.")
        else:
            earned = random.randint(10, 20)
            db["users"][user_id]["points"] += earned
            db["users"][user_id]["last_taf"] = now
            save_data(db)
            await update.message.reply_text(
                f"🤧 یک تف پربرکت انداختی!\n➕ **{earned}** امتیاز گرفتی.\n💰 مجموع امتیازات: {db['users'][user_id]['points']:,}",
                parse_mode="Markdown"
            )
        return

    # ۲. سیستم کازینو 🎰 (با کلمه متنی "کازینو" یا دستور "/casino")
    if text == "کازینو" or text.startswith("/casino"):
        is_joined = await check_mandatory_join(user.id, context.bot)
        if not is_joined:
            channels = "\n".join(db["mandatory_channels"])
            await update.message.reply_text(
                f"⚠️ {user.first_name} عزیز، برای استفاده از کازینو ابتدا عضو کانال‌های زیر شو:\n{channels}"
            )
            return

        last_casino = db["users"][user_id].get("last_casino", 0)
        time_diff = now - last_casino

        if time_diff < 86400:  # 24 ساعت
            remaining = int(86400 - time_diff)
            await update.message.reply_text(
                f"🎰 شما قبلاً از شانس ۲۴ ساعته خود استفاده کرده‌اید!\n⏳ زمان باقی‌مانده: {format_time(remaining)}"
            )
        else:
            earned = random.randint(100, 50000)
            db["users"][user_id]["points"] += earned
            db["users"][user_id]["last_casino"] = now
            save_data(db)
            await update.message.reply_text(
                f"🎰 {earned:,} امتیاز پر تف گرفتی 😋\n💰 مجموع امتیاز: {db['users'][user_id]['points']:,} امتیاز",
                parse_mode="Markdown"
            )
        return

    # ۳. هدیه روزانه 🎁
    if text == "روزانه" or text.startswith("/daily"):
        last_daily = db["users"][user_id].get("last_daily", 0)
        if now - last_daily < 86400:
            remaining = int(86400 - (now - last_daily))
            await update.message.reply_text(f"🎁 هدیه روزانه رو قبلاً گرفتی! ⏳ {format_time(remaining)} دیگه بیا.")
        else:
            earned = random.randint(50, 200)
            db["users"][user_id]["points"] += earned
            db["users"][user_id]["last_daily"] = now
            save_data(db)
            await update.message.reply_text(f"🎁 مبارکه! **{earned}** امتیاز هدیه روزانه دریافت کردی 🥳", parse_mode="Markdown")
        return

    # ۴. استعلام امتیاز 💰
    if text in ["امتیاز من", "رتبه من"] or text.startswith("/myline"):
        pts = db["users"][user_id]["points"]
        await update.message.reply_text(f"👤 **{user.first_name}** عزیز:\n💰 امتیاز فعلی شما: **{pts:,}**", parse_mode="Markdown")

# ==================== عملیات پنل ادمین ====================
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in db["admins"]:
        await query.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return

    data = query.data

    if data == "admin_top":
        sorted_users = sorted(db["users"].items(), key=lambda x: x[1].get("points", 0), reverse=True)[:10]
        if not sorted_users:
            text = "هنوز کاربری ثبت نشده است."
        else:
            text = "🏆 **۱۰ کاربر برتر تف‌انداز:**\n\n"
            for idx, (uid, info) in enumerate(sorted_users, 1):
                text += f"{idx}. {info.get('name', 'ناشناس')} 👈 `{info.get('points', 0):,}` امتیاز\n"
        await query.message.reply_text(text, parse_mode="Markdown")

    elif data == "admin_toggle_bot":
        db["bot_active"] = not db.get("bot_active", True)
        save_data(db)
        state_txt = "روشن شد ✅" if db["bot_active"] else "خاموش شد ⛔"
        await query.message.reply_text(f"وضعیت ربات تغییر کرد: ربات {state_txt}")
        await query.message.edit_reply_markup(reply_markup=get_admin_keyboard())

    elif data == "admin_channel":
        channels = "\n".join(db.get("mandatory_channels", [])) or "هیچ کانالی ثبت نشده."
        context.user_data["admin_action"] = "add_channel"
        await query.message.reply_text(
            f"📢 **کانال‌های جوین اجباری فعلی:**\n{channels}\n\n"
            f"آیدی کانال را ارسال کنید (مثال: `@mychannel`).\n"
            f"یا برای حذف کل کانال‌ها عبارت `clear` را بفرستید.",
            parse_mode="Markdown"
        )

    elif data == "admin_add_admin":
        context.user_data["admin_action"] = "add_admin"
        await query.message.reply_text("لطفاً آیدی عددی کاربر جدید را بفرستید:")

    elif data == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await query.message.reply_text("پیام عمومی برای ارسال به تمام گروه‌ها را بفرستید:")

    elif data == "admin_manage_points":
        context.user_data["admin_action"] = "change_points"
        await query.message.reply_text("آیدی عددی کاربر و مقدار امتیاز را به این شکل بفرستید:\n`123456789 +500` یا `123456789 -200`", parse_mode="Markdown")

    elif data == "admin_status":
        total_users = len(db["users"])
        total_groups = len(db["groups"])
        status = "فعال 🟢" if db.get("bot_active", True) else "غیرفعال 🔴"
        await query.message.reply_text(
            f"📊 **آمار کامل ربات:**\n\n"
            f"👤 تعداد کاربران: {total_users}\n"
            f"👥 تعداد گروه‌ها: {total_groups}\n"
            f"⚙️ وضعیت عملکرد: {status}\n"
            f"📢 تعداد کانال اجباری: {len(db.get('mandatory_channels', []))}",
            parse_mode="Markdown"
        )

async def handle_admin_inputs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in db["admins"]:
        return

    action = context.user_data.get("admin_action")
    text = update.message.text.strip()

    if action == "add_channel":
        if text.lower() == "clear":
            db["mandatory_channels"] = []
            save_data(db)
            await update.message.reply_text("✅ تمام کانال‌ها حذف شدند.")
        else:
            if not text.startswith("@"):
                text = "@" + text
            if text not in db["mandatory_channels"]:
                db["mandatory_channels"].append(text)
                save_data(db)
                await update.message.reply_text(f"✅ کانال {text} اضافه شد. (ربات باید در کانال ادمین باشد!)")
        context.user_data["admin_action"] = None

    elif action == "add_admin":
        try:
            new_admin = int(text)
            if new_admin not in db["admins"]:
                db["admins"].append(new_admin)
                save_data(db)
                await update.message.reply_text(f"✅ کاربر {new_admin} ادمین شد.")
            else:
                await update.message.reply_text("این کاربر از قبل ادمین بود.")
        except ValueError:
            await update.message.reply_text("❌ آیدی عددی معتبر نیست.")
        context.user_data["admin_action"] = None

    elif action == "broadcast":
        groups = db.get("groups", [])
        success, failed = 0, 0
        await update.message.reply_text(f"⏳ در حال ارسال به {len(groups)} گروه...")
        for gid in groups:
            try:
                await context.bot.send_message(chat_id=gid, text=text)
                success += 1
            except Exception:
                failed += 1
        await update.message.reply_text(f"✅ ارسال تمام شد.\nموفق: {success}\nناموفق: {failed}")
        context.user_data["admin_action"] = None

    elif action == "change_points":
        try:
            parts = text.split()
            target_uid = parts[0]
            change = int(parts[1])
            if target_uid in db["users"]:
                db["users"][target_uid]["points"] += change
                save_data(db)
                await update.message.reply_text(f"✅ امتیاز کاربر تغییر یافت. امتیاز جدید: {db['users'][target_uid]['points']}")
            else:
                await update.message.reply_text("❌ کاربر در سیستم پیدا نشد.")
        except Exception:
            await update.message.reply_text("❌ فرمت اشتباه است. مثال: `123456789 +100`", parse_mode="Markdown")
        context.user_data["admin_action"] = None

# ==================== اجرا ====================
def main():
    # اجرای وب سرور پورت 8080 روی یک Thread جداگانه جهت تأیید Render
    threading.Thread(target=run_flask, daemon=True).start()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_callback))
    
    # هندل کردن تمام پیام‌های گروه‌ها و سوپرگروه‌ها
    app.add_handler(MessageHandler(
        (filters.ChatType.GROUPS | filters.ChatType.SUPERGROUP) & filters.TEXT & (~filters.COMMAND),
        handle_group_messages
    ))
    
    # پیام‌های چت خصوصی ادمین
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & filters.TEXT & (~filters.COMMAND),
        handle_admin_inputs
    ))

    print("🤖 ربات با موفقیت فعال شد...")
    app.run_polling()

if __name__ == "__main__":
    main()
