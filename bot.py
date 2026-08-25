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

# Render URL of this service.
WEB_APP_URL = os.getenv(
    "WEB_APP_URL",
    "https://kdjebr.onrender.com/"
).rstrip("/") + "/"

# =====================================================
# OWNERS
# =====================================================
# Все ID из этого списка имеют полный бесплатный доступ.
OWNER_IDS = {
    8958072114,  # основной владелец
    8140798671,  # @Savevirt
}

DB_FILE = "users.db"

dp = Dispatcher()


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
        SELECT
            telegram_id,
            username,
            plan,
            expires_at
        FROM users
        WHERE telegram_id = ?
    """, (user_id,)).fetchone()

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

    # Все владельцы всегда имеют доступ.
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
# TELEGRAM WEB APP AUTH
# =====================================================

def validate_init_data(init_data):

    if not init_data or not BOT_TOKEN:
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

        auth_date = int(
            data.get(
                "auth_date",
                "0"
            )
        )

        if int(time.time()) - auth_date > 86400:
            return None

        user_data = json.loads(
            data.get(
                "user",
                "{}"
            )
        )

        if not user_data.get("id"):
            return None

        return user_data

    except Exception as e:

        print(
            "InitData validation error:",
            e
        )

        return None


# =====================================================
# TARIFFS
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
# START
# =====================================================

@dp.message(CommandStart())
async def start(message: Message):

    user_id = message.from_user.id

    # =================================================
    # OWNER
    # =================================================

    if is_owner(user_id):

        await message.answer(

            "👑 <b>SAVE SNOSER</b>\n\n"

            "Ты владелец бота.\n"

            "Доступ к Mini App для тебя "
            "всегда бесплатный.\n\n"

            "🚀 Можешь использовать все функции "
            "без оплаты.",

            reply_markup=mini_app_keyboard(),

            parse_mode="HTML"
        )

        return

    # =================================================
    # Обычный пользователь
    # =================================================

    await message.answer(

        "✨ <b>SAVE SNOSER — PREMIUM ACCESS</b>\n\n"

        "Выбери тариф для доступа к Mini App:\n\n"

        "⭐ <b>50 Stars</b> — 1 день\n"
        "⭐ <b>100 Stars</b> — 7 дней\n"
        "👑 <b>200 Stars</b> — навсегда",

        reply_markup=premium_keyboard(),

        parse_mode="HTML"
    )


# =====================================================
# INVOICES
# =====================================================

async def send_invoice(
    callback,
    plan_id
):

    plan = PLANS[plan_id]

    await callback.message.answer_invoice(

        title=plan["name"],

        description=plan["description"],

        payload=f"premium:{plan_id}",

        currency="XTR",

        prices=[
            LabeledPrice(
                label=plan["name"],
                amount=plan["price"]
            )
        ],

        provider_token=""
    )


@dp.callback_query(
    F.data.in_(PLANS.keys())
)
async def select_plan(callback):

    await callback.answer()

    await send_invoice(
        callback,
        callback.data
    )


# =====================================================
# PRE-CHECKOUT
# =====================================================

@dp.pre_checkout_query()
async def pre_checkout(
    pre_checkout_query: PreCheckoutQuery
):

    await pre_checkout_query.answer(
        ok=True
    )


# =====================================================
# SUCCESSFUL PAYMENT
# =====================================================

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

    now = int(time.time())

    old_user = get_user(user_id)

    old_expiration = (
        old_user[3]
        if old_user
        else 0
    )

    if plan["duration"] == 0:

        expires_at = 0

    else:

        start_time = (
            old_expiration
            if old_expiration
            and old_expiration > now
            else now
        )

        expires_at = (
            start_time +
            plan["duration"]
        )

    save_access(

        user_id=user_id,

        username=username,

        plan=plan_id,

        expires_at=expires_at,

        payment_id=(
            payment.telegram_payment_charge_id
        )

    )

    access_text = (

        "♾️ Доступ: <b>НАВСЕГДА</b>"

        if plan["duration"] == 0

        else (

            "⏳ Доступ активен "
            "на <b>1 день</b>."

            if plan["duration"] == 86400

            else

            "⏳ Доступ активен "
            "на <b>7 дней</b>."
        )

    )

    await message.answer(

        "🎉 <b>Оплата прошла успешно!</b>\n\n"

        f"👑 Тариф: <b>{plan['name']}</b>\n"

        f"{access_text}\n\n"

        "Теперь Mini App доступен:",

        reply_markup=mini_app_keyboard(),

        parse_mode="HTML"
    )


# =====================================================
# WEBHOOK
# =====================================================

async def handle_webhook(request):

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
            text="Error"
        )


# =====================================================
# MINI APP ACCESS API
# =====================================================

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
                    "message":
                        "Недействительная "
                        "авторизация Telegram."
                },

                status=401
            )

        user_id = int(
            user["id"]
        )

        # =================================================
        # OWNER ACCESS
        # =================================================

        if is_owner(user_id):

            return web.json_response(

                {
                    "ok": True,
                    "access": True,
                    "owner": True,
                    "expires_at": 0,
                    "expires_text":
                        "Владелец — навсегда"
                }
            )

        # =================================================
        # PREMIUM ACCESS
        # =================================================

        if not has_access(user_id):

            return web.json_response(

                {
                    "ok": True,
                    "access": False,
                    "message":
                        "Доступ не оплачен "
                        "или срок действия закончился."
                }
            )

        db_user = get_user(
            user_id
        )

        expires_at = db_user[3]

        return web.json_response(

            {
                "ok": True,
                "access": True,
                "owner": False,
                "expires_at": expires_at,
                "expires_text": (

                    "Навсегда"

                    if expires_at == 0

                    else str(expires_at)

                )
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
                "message":
                    "Ошибка проверки доступа."
            },

            status=500
        )


# =====================================================
# SERVE INDEX.HTML
# =====================================================

async def index(request):

    return web.FileResponse(
        "index.html"
    )


async def health(request):

    return web.Response(
        text="Premium Bot is running"
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

        render_url = WEB_APP_URL.rstrip("/")

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

    print(
        "Mini App:",
        WEB_APP_URL
    )

    print(
        "Owners:",
        OWNER_IDS
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
            "BOT_TOKEN не задан"
        )

    init_db()

    bot = Bot(
        BOT_TOKEN
    )

    app = web.Application()

    app["bot"] = bot

    # Mini App
    app.router.add_get(
        "/",
        index
    )

    app.router.add_get(
        "/health",
        health
    )

    # Telegram webhook
    app.router.add_post(
        "/telegram-webhook",
        handle_webhook
    )

    # Mini App access
    app.router.add_post(
        "/api/access",
        check_access
    )

    # Optional /app/
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

    asyncio.run(main())
