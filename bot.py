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

# =====================================================
# ENV
# =====================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))

# =====================================================
# URL
# =====================================================

WEB_APP_URL = "https://demuge.github.io/Kdjebr/"

RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    "https://kdjebr.onrender.com"
).rstrip("/")

# =====================================================
# OWNERS
# =====================================================

OWNER_IDS = {
    8958072114,
    8140798671,
}

BOT_USERNAME = "savesnoser_bot"

DB_FILE = "users.db"

dp = Dispatcher()


# =====================================================
# CORS
# =====================================================

ALLOWED_ORIGIN = "https://demuge.github.io"


def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


async def options_access(request):
    response = web.Response(status=204)
    return add_cors_headers(response)


# =====================================================
# DATABASE
# =====================================================

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


def save_access(
    user_id,
    username,
    plan,
    expires_at,
    payment_id
):
    conn = db_connect()

    conn.execute("""
        INSERT INTO users
        (
            telegram_id,
            username,
            plan,
            expires_at,
            payment_id
        )
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
        SELECT
            telegram_id,
            username,
            plan,
            expires_at
        FROM users
        WHERE telegram_id = ?
    """, (
        user_id,
    )).fetchone()

    conn.close()

    return row


# =====================================================
# ACCESS
# =====================================================

def is_owner(user_id):

    try:
        return int(user_id) in OWNER_IDS

    except Exception:
        return False


def has_access(user_id):

    # Два владельца всегда имеют доступ
    if is_owner(user_id):
        return True

    user = get_user(user_id)

    if not user:
        return False

    expires_at = user[3]

    # 0 = навсегда
    if expires_at == 0:
        return True

    return expires_at > int(time.time())


# =====================================================
# TELEGRAM INIT DATA
# =====================================================

def validate_init_data(init_data):

    if not init_data:
        print("InitData: empty")
        return None

    if not BOT_TOKEN:
        print("InitData: BOT_TOKEN missing")
        return None

    try:

        data = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = data.pop(
            "hash",
            None
        )

        if not received_hash:
            print("InitData: hash missing")
            return None

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(data.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            print("InitData: invalid hash")
            return None

        auth_date = int(
            data.get(
                "auth_date",
                "0"
            )
        )

        # initData не старше 24 часов
        if int(time.time()) - auth_date > 86400:
            print("InitData: expired")
            return None

        user = json.loads(
            data.get(
                "user",
                "{}"
            )
        )

        if not user.get("id"):
            print("InitData: user id missing")
            return None

        return user

    except Exception as e:

        print(
            "InitData error:",
            e
        )

        return None


# =====================================================
# PLANS
# =====================================================

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
    },

}


# =====================================================
# KEYBOARDS
# =====================================================

def premium_keyboard():

    return InlineKeyboardMarkup(
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
            ],

        ]
    )


def mini_app_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="🚀 Открыть SAVE SNOSER",
                    web_app={
                        "url": WEB_APP_URL
                    }
                )
            ]

        ]
    )


# =====================================================
# /START
# =====================================================

@dp.message(CommandStart())
async def start(message: Message):

    user_id = message.from_user.id

    if is_owner(user_id):

        await message.answer(

            "👑 <b>SAVE SNOSER</b>\n\n"
            "Ты владелец бота.\n"
            "Доступ к Mini App всегда бесплатный.\n\n"
            "🚀 Нажми кнопку ниже.",

            reply_markup=mini_app_keyboard(),

            parse_mode="HTML"
        )

        return

    if has_access(user_id):

        await message.answer(

            "✅ <b>Premium активен.</b>\n\n"
            "Ты можешь открыть SAVE SNOSER.",

            reply_markup=mini_app_keyboard(),

            parse_mode="HTML"
        )

        return

    await message.answer(

        "✨ <b>SAVE SNOSER — PREMIUM ACCESS</b>\n\n"
        "Для открытия Mini App необходимо "
        "активировать Premium.\n\n"
        "Выбери тариф:",

        reply_markup=premium_keyboard(),

        parse_mode="HTML"
    )


# =====================================================
# PAYMENT
# =====================================================

@dp.callback_query(
    F.data.in_(PLANS.keys())
)
async def select_plan(callback):

    plan = PLANS[callback.data]

    await callback.message.answer_invoice(

        title=plan["name"],

        description=plan["description"],

        payload=f"premium:{callback.data}",

        currency="XTR",

        prices=[
            LabeledPrice(
                label=plan["name"],
                amount=plan["price"]
            )
        ],

        provider_token=""
    )

    await callback.answer()


@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):

    await query.answer(
        ok=True
    )


@dp.message(F.successful_payment)
async def successful_payment(
    message: Message
):

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

    username = (
        message.from_user.username
        or ""
    )

    now = int(
        time.time()
    )

    old_user = get_user(
        user_id
    )

    old_expiration = (
        old_user[3]
        if old_user
        else 0
    )

    if plan["duration"] == 0:

        expires_at = 0

    else:

        start = (
            old_expiration
            if old_expiration > now
            else now
        )

        expires_at = (
            start +
            plan["duration"]
        )

    save_access(
        user_id,
        username,
        plan_id,
        expires_at,
        payment.telegram_payment_charge_id
    )

    await message.answer(

        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "Теперь тебе доступен SAVE SNOSER.",

        reply_markup=mini_app_keyboard(),

        parse_mode="HTML"
    )


# =====================================================
# MINI APP ACCESS
# =====================================================

async def check_access(request):

    if request.method == "OPTIONS":

        return await options_access(
            request
        )

    try:

        data = await request.json()

        init_data = data.get(
            "initData"
        )

        user = validate_init_data(
            init_data
        )

        if not user:

            response = web.json_response(
                {
                    "ok": False,
                    "access": False,
                    "message":
                        "Недействительная "
                        "авторизация Telegram."
                },
                status=401
            )

            return add_cors_headers(
                response
            )

        user_id = int(
            user["id"]
        )

        # =================================================
        # OWNER
        # =================================================

        if is_owner(user_id):

            response = web.json_response(
                {
                    "ok": True,
                    "access": True,
                    "owner": True,
                    "telegram_id": user_id,
                    "expires_at": 0
                }
            )

            return add_cors_headers(
                response
            )

        # =================================================
        # PREMIUM
        # =================================================

        if not has_access(user_id):

            response = web.json_response(
                {
                    "ok": True,
                    "access": False,
                    "owner": False,
                    "telegram_id": user_id,
                    "message":
                        "Для использования "
                        "SAVE SNOSER необходимо "
                        "активировать Premium."
                }
            )

            return add_cors_headers(
                response
            )

        user_db = get_user(
            user_id
        )

        expires_at = (
            user_db[3]
            if user_db
            else 0
        )

        response = web.json_response(
            {
                "ok": True,
                "access": True,
                "owner": False,
                "telegram_id": user_id,
                "expires_at": expires_at
            }
        )

        return add_cors_headers(
            response
        )

    except Exception as e:

        print(
            "Access error:",
            e
        )

        response = web.json_response(
            {
                "ok": False,
                "access": False,
                "message":
                    "Ошибка проверки доступа."
            },
            status=500
        )

        return add_cors_headers(
            response
        )


# =====================================================
# WEBHOOK
# =====================================================

async def webhook(request):

    try:

        data = await request.json()

        update = Update.model_validate(
            data
        )

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
            text="ERROR"
        )


# =====================================================
# HEALTH
# =====================================================

async def health(request):

    return web.Response(
        text="SAVE SNOSER backend is running"
    )


# =====================================================
# STARTUP
# =====================================================

async def on_startup(app):

    bot = app["bot"]

    render_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )

    if not render_url:

        render_url = RENDER_URL

    webhook_url = (
        render_url.rstrip("/")
        + "/telegram-webhook"
    )

    await bot.set_webhook(
        webhook_url,
        drop_pending_updates=True
    )

    print(
        "================================"
    )

    print(
        "SAVE SNOSER BACKEND STARTED"
    )

    print(
        "Webhook:",
        webhook_url
    )

    print(
        "Mini App:",
        WEB_APP_URL
    )

    print(
        "Owners:",
        OWNER_IDS
    )

    print(
        "================================"
    )


async def on_cleanup(app):

    bot = app["bot"]

    try:

        await bot.delete_webhook()

    finally:

        await bot.session.close()


# =====================================================
# MAIN
# =====================================================

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не найден в Environment."
        )

    init_db()

    bot = Bot(
        BOT_TOKEN
    )

    app = web.Application()

    app["bot"] = bot

    # Health
    app.router.add_get(
        "/health",
        health
    )

    # Telegram webhook
    app.router.add_post(
        "/telegram-webhook",
        webhook
    )

    # Mini App access
    app.router.add_options(
        "/api/access",
        options_access
    )

    app.router.add_post(
        "/api/access",
        check_access
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
    asyncio.run(main())
