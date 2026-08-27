import os
import asyncio
import sqlite3
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))
WEB_APP_URL = "https://demuge.github.io/Kdjebr/"
DB_FILE = "users.db"

OWNER_IDS = {8958072114, 8140798671}

SPAM_MARKERS = (
    "Бот сделан в PuzzleBot",
    "Создай Чат-бот и Мини-приложение с 0",
    "Бесплатный курс",
)

dp = Dispatcher()


def db_connect():
    return sqlite3.connect(DB_FILE)


def init_db():
    conn = db_connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            plan TEXT,
            expires_at INTEGER,
            payment_id TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = db_connect()
    row = conn.execute(
        "SELECT telegram_id, username, plan, expires_at, payment_id FROM users WHERE telegram_id = ?",
        (user_id,)
    ).fetchone()
    conn.close()
    return row


def save_access(user_id, username, plan, expires_at, payment_id):
    conn = db_connect()
    conn.execute("""
        INSERT INTO users (telegram_id, username, plan, expires_at, payment_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id) DO UPDATE SET
            username = excluded.username,
            plan = excluded.plan,
            expires_at = excluded.expires_at,
            payment_id = excluded.payment_id
    """, (user_id, username, plan, expires_at, payment_id))
    conn.commit()
    conn.close()


def is_owner(user_id):
    try:
        return int(user_id) in OWNER_IDS
    except Exception:
        return False


def has_access(user_id):
    if is_owner(user_id):
        return True
    user = get_user(user_id)
    if not user:
        return False
    expires_at = user[3]
    if expires_at == 0:
        return True
    return expires_at > int(time.time())


def validate_init_data(init_data):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = data.pop("hash", None)
        if not received_hash:
            return None

        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc_hash = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(calc_hash, received_hash):
            return None

        auth_date = int(data.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            return None

        user = json.loads(data.get("user", "{}"))
        if not user.get("id"):
            return None
        return user
    except Exception as e:
        print("initData validation fail:", e)
        return None


PLANS = {
    "plan_day": {
        "name": "Premium — 1 день",
        "description": "Доступ к SAVE SNOSER на 24 часа.",
        "price": 50,
        "duration": 86400,
    },
    "plan_week": {
        "name": "Premium — 7 дней",
        "description": "Доступ к SAVE SNOSER на 7 дней.",
        "price": 100,
        "duration": 604800,
    },
    "plan_forever": {
        "name": "Premium — навсегда",
        "description": "Пожизненный доступ к SAVE SNOSER.",
        "price": 200,
        "duration": 0,
    },
}


def mini_app_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Открыть SAVE SNOSER", web_app={"url": WEB_APP_URL})
    ]])


def premium_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ 50 — 1 день", callback_data="plan_day")],
        [InlineKeyboardButton(text="⭐ 100 — 7 дней", callback_data="plan_week")],
        [InlineKeyboardButton(text="👑 200 — НАВСЕГДА", callback_data="plan_forever")],
    ])


def is_spam(text):
    if not text:
        return False
    return all(m in text for m in SPAM_MARKERS)


@dp.message(F.chat.type == "private", F.text)
async def spam_filter(message: Message):
    if not is_spam(message.text):
        return
    try:
        await message.delete()
        print(f"spam deleted: {message.from_user.id}")
    except Exception as e:
        print("delete failed:", e)


@dp.message(CommandStart())
async def start_handler(message: Message):
    uid = message.from_user.id
    print(f"/start {uid}")

    if is_owner(uid):
        await message.answer(
            "👑 <b>SAVE SNOSER</b>\n\n"
            "Твой аккаунт имеет бесплатный доступ.\n\n"
            "🚀 Открывай Mini App:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )
        return

    if has_access(uid):
        await message.answer(
            "✅ <b>Premium активен.</b>\n\n"
            "🚀 Открывай SAVE SNOSER:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )
        return

    await message.answer(
        "✨ <b>SAVE SNOSER</b>\n\n"
        "Для доступа к Mini App необходимо приобрести Premium.\n\n"
        "Выбери тариф:",
        reply_markup=premium_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.in_(PLANS.keys()))
async def select_plan(callback):
    plan = PLANS.get(callback.data)
    if not plan:
        await callback.answer("Тариф не найден.", show_alert=True)
        return
    try:
        await callback.message.answer_invoice(
            title=plan["name"],
            description=plan["description"],
            payload=f"premium:{callback.data}",
            currency="XTR",
            prices=[LabeledPrice(label=plan["name"], amount=plan["price"])],
            provider_token="",
        )
        await callback.answer()
    except Exception as e:
        print("invoice error:", e)
        await callback.answer("Не удалось создать оплату.", show_alert=True)


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    print("precheckout", query.from_user.id, query.invoice_payload)
    try:
        await query.answer(ok=True)
    except Exception as e:
        print("precheckout err:", e)


@dp.message(F.successful_payment)
async def on_payment(message: Message):
    try:
        payment = message.successful_payment
        if not payment:
            return

        payload = payment.invoice_payload
        print("payment ok", message.from_user.id, payload)

        if not payload.startswith("premium:"):
            return

        plan_id = payload.split("premium:", 1)[1]
        if plan_id not in PLANS:
            print("unknown plan", plan_id)
            return

        plan = PLANS[plan_id]
        uid = message.from_user.id
        username = message.from_user.username or ""
        now = int(time.time())

        old = get_user(uid)
        old_exp = old[3] if old else 0

        if plan["duration"] == 0:
            expires = 0
        else:
            start = old_exp if old_exp > now else now
            expires = start + plan["duration"]

        save_access(uid, username, plan_id, expires, payment.telegram_payment_charge_id)

        await message.answer(
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            "✅ Premium активирован.\n\n"
            "Теперь тебе доступен SAVE SNOSER:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )
        print(f"access given {uid} until {expires}")
    except Exception as e:
        print("payment handler fail:", e)


async def check_access(request):
    try:
        body = await request.json()
        user = validate_init_data(body.get("initData"))

        if not user:
            return web.json_response({
                "ok": False,
                "access": False,
                "owner": False,
                "message": "Недействительная авторизация Telegram."
            }, status=401)

        uid = int(user["id"])
        print("access check", uid)

        if is_owner(uid):
            return web.json_response({
                "ok": True,
                "access": True,
                "owner": True,
                "expires_at": 0
            })

        if not has_access(uid):
            return web.json_response({
                "ok": True,
                "access": False,
                "owner": False,
                "message": "Необходимо приобрести Premium."
            })

        row = get_user(uid)
        expires = row[3] if row else 0

        return web.json_response({
            "ok": True,
            "access": True,
            "owner": False,
            "expires_at": expires
        })
    except Exception as e:
        print("access api error:", e)
        return web.json_response({
            "ok": False,
            "access": False,
            "message": "Ошибка сервера."
        }, status=500)


async def health(_):
    return web.json_response({"ok": True, "service": "SAVE SNOSER backend", "bot": "polling"})


async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    app.router.add_post("/api/access", check_access)

    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    print(f"http on :{PORT}")
    return runner


async def start_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing")

    bot = Bot(token=BOT_TOKEN)

    await bot.delete_webhook(drop_pending_updates=False)
    me = await bot.get_me()
    print(f"bot started @{me.username} id={me.id}")
    print(f"owners={OWNER_IDS}")
    print(f"webapp={WEB_APP_URL}")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


async def main():
    init_db()
    runner = await start_web()
    try:
        await start_bot()
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("stopped")
