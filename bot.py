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


# ============================================================
# НАСТРОЙКИ
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

PORT = int(os.getenv("PORT", "10000"))

# GitHub Pages Mini App
WEB_APP_URL = "https://demuge.github.io/Kdjebr/"

# Render
RENDER_URL = os.getenv(
    "RENDER_EXTERNAL_URL",
    "https://kdjebr.onrender.com"
).rstrip("/")


# ============================================================
# БЕСПЛАТНЫЕ АККАУНТЫ
# ============================================================

OWNER_IDS = {
    8958072114,
    8140798671,
}


# ============================================================
# DATABASE
# ============================================================

DB_FILE = "users.db"


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


# ============================================================
# ACCESS
# ============================================================

def is_owner(user_id):

    try:
        return int(user_id) in OWNER_IDS
    except Exception:
        return False


def has_access(user_id):

    # Два твоих аккаунта всегда имеют доступ
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


# ============================================================
# TELEGRAM MINI APP INIT DATA
# ============================================================

def validate_init_data(init_data):

    if not init_data:
        print("INIT DATA: empty")
        return None

    if not BOT_TOKEN:
        print("BOT_TOKEN is missing")
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
            print("INIT DATA: hash missing")
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
            print("INIT DATA: invalid hash")
            return None

        auth_date = int(
            data.get("auth_date", "0")
        )

        # InitData действительна 24 часа
        if int(time.time()) - auth_date > 86400:
            print("INIT DATA: expired")
            return None

        user_json = data.get(
            "user",
            "{}"
        )

        user = json.loads(user_json)

        if not user.get("id"):
            print("INIT DATA: user id missing")
            return None

        return user

    except Exception as e:

        print(
            "InitData validation error:",
            repr(e)
        )

        return None


# ============================================================
# ТАРИФЫ
# ============================================================

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


# ============================================================
# КНОПКА MINI APP
# ============================================================

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


# ============================================================
# КНОПКИ ОПЛАТЫ
# ============================================================

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


# ============================================================
# START
# ============================================================

@dp.message(CommandStart())
async def start(message: Message):

    user_id = message.from_user.id

    print(
        f"/start from user {user_id}"
    )

    # ========================================================
    # ТВОИ ДВА АККАУНТА
    # ========================================================

    if is_owner(user_id):

        await message.answer(
            "👑 <b>SAVE SNOSER</b>\n\n"
            "Твой аккаунт имеет бесплатный доступ.\n"
            "Оплата не требуется.\n\n"
            "🚀 Можешь открыть Mini App:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # ========================================================
    # ВСЕ ОСТАЛЬНЫЕ
    # ========================================================

    if has_access(user_id):

        await message.answer(
            "✅ <b>У тебя уже есть активный Premium.</b>\n\n"
            "Можешь открыть SAVE SNOSER:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # ========================================================
    # НОВЫЙ ПОЛЬЗОВАТЕЛЬ
    # ========================================================

    await message.answer(
        "✨ <b>SAVE SNOSER</b>\n\n"
        "Для доступа к Mini App необходимо приобрести Premium.\n\n"
        "Выбери подходящий тариф:",
        reply_markup=premium_keyboard(),
        parse_mode="HTML"
    )


# ============================================================
# ВЫБОР ТАРИФА
# ============================================================

@dp.callback_query(
    F.data.in_(PLANS.keys())
)
async def select_plan(callback):

    try:

        plan_id = callback.data

        plan = PLANS.get(plan_id)

        if not plan:

            await callback.answer(
                "Тариф не найден.",
                show_alert=True
            )

            return

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
            repr(e)
        )

        await callback.answer(
            "Ошибка создания оплаты.",
            show_alert=True
        )


# ============================================================
# PRE-CHECKOUT
# ============================================================

@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):

    print(
        "PreCheckout:",
        query.from_user.id,
        query.invoice_payload
    )

    try:

        await query.answer(
            ok=True
        )

    except Exception as e:

        print(
            "PreCheckout error:",
            repr(e)
        )


# ============================================================
# УСПЕШНАЯ ОПЛАТА
# ============================================================

@dp.message(
    F.successful_payment
)
async def successful_payment(
    message: Message
):

    try:

        payment = message.successful_payment

        if not payment:
            return

        payload = payment.invoice_payload

        print(
            "Successful payment:",
            message.from_user.id,
            payload
        )

        if not payload.startswith(
            "premium:"
        ):
            return

        plan_id = payload.split(
            "premium:",
            1
        )[1]

        if plan_id not in PLANS:

            print(
                "Unknown plan:",
                plan_id
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

            # Если старый Premium ещё действует,
            # добавляем новый срок к нему.
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
            user_id=user_id,
            username=username,
            plan=plan_id,
            expires_at=expires_at,
            payment_id=payment.telegram_payment_charge_id
        )

        await message.answer(
            "🎉 <b>Оплата прошла успешно!</b>\n\n"
            "✅ Premium активирован.\n\n"
            "Теперь можешь открыть SAVE SNOSER:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

    except Exception as e:

        print(
            "Successful payment error:",
            repr(e)
        )

        await message.answer(
            "Оплата получена, но произошла ошибка "
            "при выдаче доступа. Обратись к владельцу."
        )


# ============================================================
# MINI APP ACCESS API
# ============================================================

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
                    "owner": False,
                    "message":
                        "Недействительная "
                        "авторизация Telegram."
                },
                status=401
            )

        user_id = int(
            user["id"]
        )

        print(
            f"Mini App access check: {user_id}"
        )

        # ====================================================
        # ТВОИ ДВА АККАУНТА
        # ====================================================

        if is_owner(user_id):

            return web.json_response(
                {
                    "ok": True,
                    "access": True,
                    "owner": True,
                    "expires_at": 0
                }
            )

        # ====================================================
        # ОСТАЛЬНЫЕ
        # ====================================================

        if not has_access(user_id):

            return web.json_response(
                {
                    "ok": True,
                    "access": False,
                    "owner": False,
                    "message":
                        "Для использования "
                        "SAVE SNOSER необходимо "
                        "приобрести Premium."
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
            "Access API error:",
            repr(e)
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


# ============================================================
# WEBHOOK TELEGRAM
# ============================================================

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
            repr(e)
        )

        return web.Response(
            status=500,
            text="ERROR"
        )


# ============================================================
# HEALTH
# ============================================================

async def health(request):

    return web.json_response(
        {
            "ok": True,
            "service":
                "SAVE SNOSER backend"
        }
    )


# ============================================================
# STARTUP
# ============================================================

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

    print(
        "======================================"
    )

    print(
        "SAVE SNOSER STARTING"
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
        "======================================"
    )

    try:

        await bot.set_webhook(
            webhook_url,
            drop_pending_updates=True
        )

        print(
            "Telegram webhook successfully set."
        )

    except Exception as e:

        print(
            "Webhook setup error:",
            repr(e)
        )

        raise


# ============================================================
# CLEANUP
# ============================================================

async def on_cleanup(app):

    bot = app["bot"]

    try:

        await bot.delete_webhook()

    except Exception as e:

        print(
            "Delete webhook error:",
            repr(e)
        )

    try:

        await bot.session.close()

    except Exception as e:

        print(
            "Bot session close error:",
            repr(e)
        )


# ============================================================
# MAIN
# ============================================================

async def main():

    # ========================================================
    # ПРОВЕРКА BOT_TOKEN
    # ========================================================

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не найден. "
            "Добавь BOT_TOKEN в Render Environment Variables."
        )

    # ========================================================
    # DATABASE
    # ========================================================

    init_db()

    # ========================================================
    # BOT
    # ========================================================

    bot = Bot(
        token=BOT_TOKEN
    )

    # ========================================================
    # WEB APP
    # ========================================================

    app = web.Application()

    app["bot"] = bot

    # ========================================================
    # ROUTES
    # ========================================================

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
        webhook
    )

    app.router.add_post(
        "/api/access",
        check_access
    )

    # ========================================================
    # EVENTS
    # ========================================================

    app.on_startup.append(
        on_startup
    )

    app.on_cleanup.append(
        on_cleanup
    )

    # ========================================================
    # START SERVER
    # ========================================================

    print(
        f"Starting server on port {PORT}"
    )

    await web._run_app(
        app,
        host="0.0.0.0",
        port=PORT
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    try:
        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print(
            "Bot stopped."
        )
