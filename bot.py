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
    Update,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

WEB_APP_URL = "https://kdjebr.onrender.com/"

DB_FILE = "users.db"

dp = Dispatcher()


# =========================
# DATABASE
# =========================

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


def save_access(user_id, username, plan, expires_at, payment_id):
    conn = db_connect()

    conn.execute("""
        INSERT INTO users
        (telegram_id, username, plan, expires_at, payment_id)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(telegram_id)
        DO UPDATE SET
            username = excluded.username,
            plan = excluded.plan,
            expires_at = excluded.expires_at,
            payment_id = excluded.payment_id
    """, (
        user_id,
        username,
        plan,
        expires_at,
        payment_id
    ))

    conn.commit()
    conn.close()


def get_user(user_id):
    conn = db_connect()

    row = conn.execute("""
        SELECT telegram_id, username, plan, expires_at
        FROM users
        WHERE telegram_id = ?
    """, (user_id,)).fetchone()

    conn.close()

    return row


# =========================
# ACCESS CHECK
# =========================

def has_access(user_id):
    user = get_user(user_id)

    if not user:
        return False

    expires_at = user[3]

    # 0 = forever
    if expires_at == 0:
        return True

    return expires_at > int(time.time())


# =========================
# TELEGRAM WEB APP AUTH
# =========================

def validate_init_data(init_data):
    if not init_data:
        return None

    try:
        data = dict(parse_qsl(init_data, keep_blank_values=True))

        received_hash = data.pop("hash", None)

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        # Telegram initData should be fresh.
        auth_date = int(data.get("auth_date", "0"))

        if int(time.time()) - auth_date > 86400:
            return None

        user_data = json.loads(data.get("user", "{}"))

        if not user_data.get("id"):
            return None

        return user_data

    except Exception as e:
        print("InitData validation error:", e)
        return None


# =========================
# START
# =========================

@dp.message(CommandStart())
async def start(message: Message):

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ 50 — 1 день",
                    callback_data="plan_day"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐ 100 — 7 дней",
                    callback_data="plan_week"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👑 200 — НАВСЕГДА",
                    callback_data="plan_forever"
                )
            ]
        ]
    )

    await message.answer(
        "✨ <b>PREMIUM ACCESS</b>\n\n"
        "Получи доступ к Mini App.\n\n"
        "⭐ <b>50 Stars</b> — 1 день\n"
        "⭐ <b>100 Stars</b> — 7 дней\n"
        "👑 <b>200 Stars</b> — навсегда\n\n"
        "Выбери подходящий тариф ниже:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# =========================
# TARIFFS
# =========================

PLANS = {
    "plan_day": {
        "name": "Premium — 1 день",
        "description": "Доступ к Mini App на 24 часа.",
        "price": 50,
        "duration": 86400,
    },

    "plan_week": {
        "name": "Premium — 7 дней",
        "description": "Доступ к Mini App на 7 дней.",
        "price": 100,
        "duration": 604800,
    },

    "plan_forever": {
        "name": "Premium — навсегда",
        "description": "Пожизненный доступ к Mini App.",
        "price": 200,
        "duration": 0,
    }
}


async def send_invoice(callback, plan_id):

    plan = PLANS[plan_id]

    prices = [
        LabeledPrice(
            label=plan["name"],
            amount=plan["price"]
        )
    ]

    payload = f"premium:{plan_id}"

    await callback.message.answer_invoice(
        title=plan["name"],
        description=plan["description"],
        payload=payload,
        currency="XTR",
        prices=prices,
        provider_token=""
    )


@dp.callback_query(F.data.in_(PLANS.keys()))
async def select_plan(callback):

    await callback.answer()

    plan_id = callback.data
    plan = PLANS[plan_id]

    await send_invoice(
        callback,
        plan_id
    )


# =========================
# PRE-CHECKOUT
# =========================

@dp.pre_checkout_query()
async def pre_checkout(
    pre_checkout_query: PreCheckoutQuery
):

    await pre_checkout_query.answer(
        ok=True
    )


# =========================
# SUCCESSFUL PAYMENT
# =========================

@dp.message(F.successful_payment)
async def successful_payment(message: Message):

    payment = message.successful_payment

    payload = payment.invoice_payload

    if not payload.startswith("premium:"):
        return

    plan_id = payload.split(
        "premium:",
        1
    )[1]

    if plan_id not in PLANS:
        return

    plan = PLANS[plan_id]

    user_id = message.from_user.id

    username = message.from_user.username or ""

    now = int(time.time())

    old_user = get_user(user_id)

    old_expiration = 0

    if old_user:
        old_expiration = old_user[3]

    # Forever
    if plan["duration"] == 0:
        expires_at = 0

    else:
        start_time = now

        # Extend existing active subscription
        if old_expiration and old_expiration > now:
            start_time = old_expiration

        expires_at = start_time + plan["duration"]

    save_access(
        user_id=user_id,
        username=username,
        plan=plan_id,
        expires_at=expires_at,
        payment_id=payment.telegram_payment_charge_id
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть Premium Mini App",
                    web_app={
                        "url": WEB_APP_URL
                    }
                )
            ]
        ]
    )

    if plan["duration"] == 0:
        access_text = "♾️ Доступ: НАВСЕГДА"
    else:
        access_text = (
            f"⏳ Доступ активен на "
            f"{'1 день' if plan['duration'] == 86400 else '7 дней'}."
        )

    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        f"👑 Тариф: <b>{plan['name']}</b>\n"
        f"{access_text}\n\n"
        "Теперь Mini App доступен тебе:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# =========================
# WEBHOOK
# =========================

async def handle_webhook(request):

    try:
        data = await request.json()

        update = Update.model_validate(data)

        bot = request.app["bot"]

        await dp.feed_update(
            bot,
            update
        )

        return web.Response(
            text="OK"
        )

    except Exception as e:

        print(
            "Webhook error:",
            e
        )

        return web.Response(
            status=500,
            text="Error"
        )


# =========================
# MINI APP ACCESS API
# =========================

async def check_access(request):

    try:
        data = await request.json()

        init_data = data.get(
            "initData"
        )

        user = validate_init_data(
            init_data
        )

        if not user:

            return web.json_response(
                {
                    "ok": False,
                    "access": False,
                    "message": "Недействительная авторизация Telegram."
                },
                status=401
            )

        user_id = user["id"]

        if not has_access(user_id):

            return web.json_response(
                {
                    "ok": True,
                    "access": False,
                    "message": "Доступ не оплачен или срок действия закончился."
                }
            )

        db_user = get_user(user_id)

        expires_at = db_user[3]

        if expires_at == 0:

            expires_text = "Навсегда"

        else:

            expires_text = str(
                expires_at
            )

        return web.json_response(
            {
                "ok": True,
                "access": True,
                "expires_at": expires_at,
                "expires_text": expires_text
            }
        )

    except Exception as e:

        print(
            "Access check error:",
            e
        )

        return web.json_response(
            {
                "ok": False,
                "access": False,
                "message": "Ошибка проверки доступа."
            },
            status=500
        )


# =========================
# HEALTH
# =========================

async def health(request):

    return web.Response(
        text="Premium Bot is running"
    )


# =========================
# STARTUP
# =========================

async def on_startup(app):

    bot = app["bot"]

    render_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )

    if not render_url:

        raise RuntimeError(
            "RENDER_EXTERNAL_URL не найден"
        )

    webhook_url = (
        render_url.rstrip("/")
        + "/telegram-webhook"
    )

    await bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True
    )

    print(
        "Webhook установлен:",
        webhook_url
    )


async def on_cleanup(app):

    bot = app["bot"]

    await bot.delete_webhook()

    await bot.session.close()


# =========================
# MAIN
# =========================

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не задан"
        )

    init_db()

    bot = Bot(
        BOT_TOKEN
    )

    app = web.Application()

    app["bot"] = bot

    app.router.add_get(
        "/",
        health
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_post(
        "/telegram-webhook",
        handle_webhook
    )

    app.router.add_post(
        "/api/access",
        check_access
    )

    app.router.add_static(
        "/app/",
        ".",
        show_index=True
    )

    app.on_startup.append(
        on_startup
    )

    app.on_cleanup.append(
        on_cleanup
    )

    await web._run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


if __name__ == "__main__":

    asyncio.run(
        main()
    )
