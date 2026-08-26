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
# MINI APP
# =====================================================

WEB_APP_URL = "https://demuge.github.io/Kdjebr/"

# =====================================================
# OWNERS
# =====================================================

# ЭТИМ ДВУМ АККАУНТАМ ДОСТУП ВСЕГДА БЕСПЛАТНЫЙ

OWNER_IDS = {
    8958072114,
    8140798671,
}

# =====================================================
# DATABASE
# =====================================================

DB_FILE = "users.db"

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


def save_access(
    user_id,
    username,
    plan,
    expires_at,
    payment_id
):
    conn = db_connect()

    conn.execute("""
        INSERT INTO users (
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
            expires_at,
            payment_id
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

    # ДВА ВЛАДЕЛЬЦА — БЕЗ ОПЛАТЫ
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
        print("INIT DATA EMPTY")
        return None

    if not BOT_TOKEN:
        print("BOT_TOKEN EMPTY")
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
            print("HASH NOT FOUND")
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
            print("INVALID TELEGRAM HASH")
            return None

        auth_date = int(
            data.get(
                "auth_date",
                "0"
            )
        )

        # initData не старше 24 часов
        if int(time.time()) - auth_date > 86400:

            print("INIT DATA EXPIRED")

            return None

        user = json.loads(
            data.get(
                "user",
                "{}"
            )
        )

        if not user.get("id"):

            print("USER ID NOT FOUND")

            return None

        return user

    except Exception as e:

        print(
            "InitData validation error:",
            e
        )

        return None


# =====================================================
# PLANS
# =====================================================

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


# =====================================================
# PAYMENT KEYBOARD
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


# =====================================================
# MINI APP BUTTON
# =====================================================

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

    username = (
        message.from_user.username
        or ""
    )

    print(
        f"/start from user: {user_id} @{username}"
    )

    # =================================================
    # OWNER
    # =================================================

    if is_owner(user_id):

        await message.answer(
            "👑 <b>SAVE SNOSER</b>\n\n"
            "Твой аккаунт имеет бесплатный доступ.\n"
            "Оплата не требуется.\n\n"
            "Нажми кнопку ниже, чтобы открыть приложение.",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # =================================================
    # PREMIUM USER
    # =================================================

    if has_access(user_id):

        await message.answer(
            "✅ <b>Premium активен!</b>\n\n"
            "Тебе доступен SAVE SNOSER.",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # =================================================
    # NO ACCESS
    # =================================================

    await message.answer(
        "✨ <b>SAVE SNOSER</b>\n\n"
        "Для доступа к приложению необходимо "
        "активировать Premium.\n\n"
        "Выбери подходящий тариф:",
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

    plan_id = callback.data

    plan = PLANS.get(plan_id)

    if not plan:

        await callback.answer(
            "Тариф не найден.",
            show_alert=True
        )

        return

    try:

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

        await callback.answer()

    except Exception as e:

        print(
            "Invoice error:",
            e
        )

        await callback.answer(
            "Не удалось создать оплату.",
            show_alert=True
        )


# =====================================================
# PRE CHECKOUT
# =====================================================

@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):

    try:

        await query.answer(
            ok=True
        )

    except Exception as e:

        print(
            "PreCheckout error:",
            e
        )


# =====================================================
# SUCCESSFUL PAYMENT
# =====================================================

@dp.message(
    F.successful_payment
)
async def successful_payment(
    message: Message
):

    payment = message.successful_payment

    if not payment:
        return

    payload = payment.invoice_payload

    if not payload.startswith(
        "premium:"
    ):
        return

    plan_id = payload.split(
        "premium:",
        1
    )[1]

    if plan_id not in PLANS:

        await message.answer(
            "Ошибка: тариф не найден."
        )

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

    # Навсегда
    if plan["duration"] == 0:

        expires_at = 0

    else:

        if (
            old_expiration
            and old_expiration > now
        ):

            start_time = old_expiration

        else:

            start_time = now

        expires_at = (
            start_time +
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
        "Premium активирован.\n"
        "Теперь ты можешь открыть SAVE SNOSER.",
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML"
    )

    print(
        f"PAYMENT SUCCESS: "
        f"user={user_id}, "
        f"plan={plan_id}, "
        f"expires={expires_at}"
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

        if not init_data:

            return web.json_response(
                {
                    "ok": False,
                    "access": False,
                    "message":
                        "Telegram authorization data отсутствует."
                },
                status=401
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
                        "Недействительная авторизация Telegram."
                },
                status=401
            )

        user_id = int(
            user["id"]
        )

        print(
            f"ACCESS CHECK: user={user_id}"
        )

        # =================================================
        # OWNER ACCESS
        # =================================================

        if is_owner(user_id):

            print(
                f"OWNER ACCESS GRANTED: {user_id}"
            )

            return web.json_response(
                {
                    "ok": True,
                    "access": True,
                    "owner": True,
                    "expires_at": 0
                }
            )

        # =================================================
        # PREMIUM ACCESS
        # =================================================

        if not has_access(user_id):

            print(
                f"ACCESS DENIED: {user_id}"
            )

            return web.json_response(
                {
                    "ok": True,
                    "access": False,
                    "owner": False,
                    "message":
                        "Для использования SAVE SNOSER "
                        "необходимо активировать Premium."
                }
            )

        user_db = get_user(
            user_id
        )

        expires_at = (
            user_db[3]
            if user_db
            else 0
        )

        print(
            f"PREMIUM ACCESS GRANTED: "
            f"{user_id}"
        )

        return web.json_response(
            {
                "ok": True,
                "access": True,
                "owner": False,
                "expires_at": expires_at
            }
        )

    except Exception as e:

        print(
            "ACCESS API ERROR:",
            e
        )

        return web.json_response(
            {
                "ok": False,
                "access": False,
                "message":
                    "Ошибка сервера."
            },
            status=500
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
            "WEBHOOK ERROR:",
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

    return web.json_response(
        {
            "ok": True,
            "service": "SAVE SNOSER backend"
        }
    )


# =====================================================
# STARTUP
# =====================================================

async def on_startup(app):

    bot = app["bot"]

    # Получаем настоящий Render URL
    render_url = os.getenv(
        "RENDER_EXTERNAL_URL"
    )

    if not render_url:

        render_url = (
            "https://kdjebr.onrender.com"
        )

    render_url = render_url.rstrip("/")

    webhook_url = (
        render_url +
        "/telegram-webhook"
    )

    print("")
    print("====================================")
    print("SAVE SNOSER BACKEND STARTING")
    print("====================================")
    print(
        "Mini App:",
        WEB_APP_URL
    )
    print(
        "Webhook:",
        webhook_url
    )
    print(
        "Owners:",
        OWNER_IDS
    )
    print("====================================")
    print("")

    try:

        await bot.delete_webhook(
            drop_pending_updates=True
        )

        await bot.set_webhook(
            webhook_url,
            drop_pending_updates=True
        )

        info = await bot.get_webhook_info()

        print(
            "Telegram webhook URL:",
            info.url
        )

        print(
            "Pending updates:",
            info.pending_update_count
        )

        print(
            "Last error:",
            info.last_error_message
        )

    except Exception as e:

        print(
            "WEBHOOK SET ERROR:",
            e
        )


# =====================================================
# CLEANUP
# =====================================================

async def on_cleanup(app):

    bot = app["bot"]

    try:

        await bot.delete_webhook()

    except Exception as e:

        print(
            "Webhook delete error:",
            e
        )

    try:

        await bot.session.close()

    except Exception:
        pass


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
        token=BOT_TOKEN
    )

    app = web.Application()

    app["bot"] = bot

    # HEALTH
    app.router.add_get(
        "/health",
        health
    )

    # TELEGRAM
    app.router.add_post(
        "/telegram-webhook",
        webhook
    )

    # MINI APP ACCESS
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

    print(
        "Starting aiohttp server..."
    )

    await web._run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        pass
