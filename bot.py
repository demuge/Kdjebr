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
# CONFIG
# =====================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

PORT = int(
    os.getenv(
        "PORT",
        "10000"
    )
)

# GitHub Pages Mini App
WEB_APP_URL = (
    "https://demuge.github.io/Kdjebr/"
)

# Твой Render backend
RENDER_URL = (
    "https://kdjebr.onrender.com"
)


# =====================================================
# OWNERS
# =====================================================

# ЭТИМ ДВУМ АККАУНТАМ ДОСТУП БЕСПЛАТНО НАВСЕГДА

OWNER_IDS = {
    8958072114,
    8140798671,
}


# =====================================================
# DATABASE
# =====================================================

DB_FILE = "users.db"


def db_connect():

    return sqlite3.connect(
        DB_FILE
    )


def init_db():

    conn = db_connect()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (

            telegram_id INTEGER PRIMARY KEY,

            username TEXT,

            plan TEXT,

            expires_at INTEGER,

            payment_id TEXT

        )
        """
    )

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

    conn.execute(
        """
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
        """,
        (
            user_id,
            username,
            plan,
            expires_at,
            payment_id
        )
    )

    conn.commit()

    conn.close()


def get_user(
    user_id
):

    conn = db_connect()

    row = conn.execute(
        """
        SELECT
            telegram_id,
            username,
            plan,
            expires_at
        FROM users
        WHERE telegram_id = ?
        """,
        (
            user_id,
        )
    ).fetchone()

    conn.close()

    return row


# =====================================================
# ACCESS
# =====================================================

def is_owner(
    user_id
):

    try:

        return (
            int(user_id)
            in OWNER_IDS
        )

    except Exception:

        return False


def has_access(
    user_id
):

    # Владельцы всегда имеют доступ
    if is_owner(user_id):

        return True

    user = get_user(
        user_id
    )

    if not user:

        return False

    expires_at = user[3]

    # 0 = навсегда
    if expires_at == 0:

        return True

    return (
        expires_at
        > int(time.time())
    )


# =====================================================
# TELEGRAM INIT DATA
# =====================================================

def validate_init_data(
    init_data
):

    if (
        not init_data
        or not BOT_TOKEN
    ):

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
            for key, value
            in sorted(
                data.items()
            )
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

            print(
                "❌ Invalid Telegram initData hash"
            )

            return None

        auth_date = int(
            data.get(
                "auth_date",
                "0"
            )
        )

        # initData не старше 24 часов
        if (
            int(time.time())
            - auth_date
            > 86400
        ):

            print(
                "❌ Telegram initData expired"
            )

            return None

        user = json.loads(
            data.get(
                "user",
                "{}"
            )
        )

        if not user.get("id"):

            return None

        return user

    except Exception as e:

        print(
            "❌ InitData error:",
            repr(e)
        )

        return None


# =====================================================
# PLANS
# =====================================================

PLANS = {

    "plan_day": {

        "name":
            "Premium — 1 день",

        "description":
            "Доступ к SAVE SNOSER на 24 часа.",

        "price":
            50,

        "duration":
            86400,

    },

    "plan_week": {

        "name":
            "Premium — 7 дней",

        "description":
            "Доступ к SAVE SNOSER на 7 дней.",

        "price":
            100,

        "duration":
            604800,

    },

    "plan_forever": {

        "name":
            "Premium — навсегда",

        "description":
            "Пожизненный доступ к SAVE SNOSER.",

        "price":
            200,

        "duration":
            0,

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

                    text=
                        "🚀 Открыть SAVE SNOSER",

                    web_app={
                        "url":
                            WEB_APP_URL
                    }

                )

            ]

        ]

    )


# =====================================================
# /START
# =====================================================

@dp.message(
    CommandStart()
)
async def start(
    message: Message
):

    user = message.from_user

    if not user:

        return

    user_id = user.id

    username = (
        user.username
        or ""
    )

    print(
        "================================"
    )

    print(
        "🔥 /start RECEIVED"
    )

    print(
        "User ID:",
        user_id
    )

    print(
        "Username:",
        username
    )

    print(
        "Owner:",
        is_owner(user_id)
    )

    print(
        "================================"
    )


    # =================================================
    # OWNER
    # =================================================

    if is_owner(
        user_id
    ):

        await message.answer(

            "👑 <b>SAVE SNOSER</b>\n\n"

            "У тебя бесплатный доступ "
            "как у владельца.\n\n"

            "🚀 Открой приложение:",

            reply_markup=
                mini_app_keyboard(),

            parse_mode=
                "HTML"

        )

        return


    # =================================================
    # УЖЕ ЕСТЬ PREMIUM
    # =================================================

    if has_access(
        user_id
    ):

        user_db = get_user(
            user_id
        )

        expires_at = (
            user_db[3]
            if user_db
            else 0
        )


        if expires_at == 0:

            text = (

                "👑 <b>SAVE SNOSER PREMIUM</b>\n\n"

                "У тебя активирован "
                "<b>пожизненный доступ</b>.\n\n"

                "🚀 Можешь открыть Mini App:"
            )

        else:

            remaining = max(
                0,
                expires_at
                - int(time.time())
            )

            hours = (
                remaining
                // 3600
            )

            text = (

                "⭐ <b>SAVE SNOSER PREMIUM</b>\n\n"

                f"Доступ активен.\n"
                f"Осталось примерно: "
                f"<b>{hours} ч.</b>\n\n"

                "🚀 Можешь открыть Mini App:"
            )


        await message.answer(

            text,

            reply_markup=
                mini_app_keyboard(),

            parse_mode=
                "HTML"

        )

        return


    # =================================================
    # НЕТ PREMIUM
    # =================================================

    await message.answer(

        "✨ <b>SAVE SNOSER</b>\n\n"

        "Для доступа к Mini App "
        "необходимо активировать Premium.\n\n"

        "Выбери подходящий тариф:",

        reply_markup=
            premium_keyboard(),

        parse_mode=
            "HTML"

    )


# =====================================================
# PLAN SELECT
# =====================================================

@dp.callback_query(
    F.data.in_(
        PLANS.keys()
    )
)
async def select_plan(
    callback
):

    plan_id = callback.data

    plan = PLANS.get(
        plan_id
    )

    if not plan:

        await callback.answer(
            "Тариф не найден.",
            show_alert=True
        )

        return


    print(
        "💳 PLAN SELECTED:",
        plan_id,
        "USER:",
        callback.from_user.id
    )


    try:

        await callback.message.answer_invoice(

            title=
                plan["name"],

            description=
                plan["description"],

            payload=
                f"premium:{plan_id}",

            currency=
                "XTR",

            prices=[

                LabeledPrice(

                    label=
                        plan["name"],

                    amount=
                        plan["price"]

                )

            ],

            provider_token=""

        )

        await callback.answer()

    except Exception as e:

        print(
            "❌ Invoice error:",
            repr(e)
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

    print(
        "💳 PRE-CHECKOUT:",
        query.from_user.id
    )

    try:

        await query.answer(
            ok=True
        )

    except Exception as e:

        print(
            "❌ PreCheckout error:",
            repr(e)
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

    payment = (
        message.successful_payment
    )

    if not payment:

        return


    print(
        "================================"
    )

    print(
        "💰 PAYMENT RECEIVED"
    )

    print(
        "USER:",
        message.from_user.id
    )

    print(
        "PAYMENT ID:",
        payment.telegram_payment_charge_id
    )

    print(
        "PAYLOAD:",
        payment.invoice_payload
    )

    print(
        "================================"
    )


    payload = (
        payment.invoice_payload
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
            "❌ Unknown plan:",
            plan_id
        )

        return


    plan = PLANS[
        plan_id
    ]


    user_id = (
        message.from_user.id
    )

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


    # =================================================
    # НОВАЯ ДАТА ОКОНЧАНИЯ
    # =================================================

    if plan["duration"] == 0:

        # Навсегда
        expires_at = 0

    else:

        if (
            old_expiration
            and
            old_expiration > now
        ):

            start_time = (
                old_expiration
            )

        else:

            start_time = now


        expires_at = (
            start_time
            +
            plan["duration"]
        )


    # =================================================
    # SAVE
    # =================================================

    save_access(

        user_id=
            user_id,

        username=
            username,

        plan=
            plan_id,

        expires_at=
            expires_at,

        payment_id=
            payment.telegram_payment_charge_id

    )


    # =================================================
    # SEND MINI APP
    # =================================================

    await message.answer(

        "🎉 <b>Оплата прошла успешно!</b>\n\n"

        "Premium активирован.\n\n"

        "Теперь тебе доступен "
        "<b>SAVE SNOSER</b>.\n\n"

        "🚀 Нажми кнопку ниже, "
        "чтобы открыть Mini App.",

        reply_markup=
            mini_app_keyboard(),

        parse_mode=
            "HTML"

    )


# =====================================================
# MINI APP ACCESS API
# =====================================================

async def check_access(
    request
):

    try:

        data = await request.json()

        init_data = data.get(
            "initData"
        )


        print(
            "🌐 ACCESS CHECK"
        )


        user = validate_init_data(
            init_data
        )


        if not user:

            print(
                "❌ ACCESS DENIED: "
                "invalid initData"
            )

            return web.json_response(

                {
                    "ok":
                        False,

                    "access":
                        False,

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
            "Mini App user:",
            user_id
        )


        # =================================================
        # OWNER
        # =================================================

        if is_owner(
            user_id
        ):

            print(
                "👑 OWNER ACCESS:",
                user_id
            )

            return web.json_response(

                {

                    "ok":
                        True,

                    "access":
                        True,

                    "owner":
                        True,

                    "expires_at":
                        0

                }

            )


        # =================================================
        # PREMIUM
        # =================================================

        if not has_access(
            user_id
        ):

            print(
                "❌ PREMIUM REQUIRED:",
                user_id
            )

            return web.json_response(

                {

                    "ok":
                        True,

                    "access":
                        False,

                    "owner":
                        False,

                    "message":
                        "Для использования "
                        "SAVE SNOSER необходимо "
                        "активировать Premium."

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
            "✅ PREMIUM ACCESS:",
            user_id
        )


        return web.json_response(

            {

                "ok":
                    True,

                "access":
                    True,

                "owner":
                    False,

                "expires_at":
                    expires_at

            }

        )


    except Exception as e:

        print(
            "❌ ACCESS API ERROR:",
            repr(e)
        )


        return web.json_response(

            {

                "ok":
                    False,

                "access":
                    False,

                "message":
                    "Ошибка проверки доступа."

            },

            status=500

        )


# =====================================================
# TELEGRAM WEBHOOK
# =====================================================

async def webhook(
    request
):

    try:

        data = await request.json()


        print(
            "================================"
        )

        print(
            "🔥 TELEGRAM UPDATE RECEIVED"
        )

        print(
            json.dumps(
                data,
                ensure_ascii=False
            )
        )

        print(
            "================================"
        )


        update = (
            Update.model_validate(
                data
            )
        )


        bot = request.app[
            "bot"
        ]


        await dp.feed_update(

            bot,

            update

        )


        return web.Response(
            text="OK"
        )


    except Exception as e:

        print(
            "❌ WEBHOOK ERROR:",
            repr(e)
        )


        return web.Response(

            status=500,

            text="ERROR"

        )


# =====================================================
# HEALTH
# =====================================================

async def health(
    request
):

    return web.json_response(

        {

            "ok":
                True,

            "service":
                "SAVE SNOSER backend"

        }

    )


# =====================================================
# WEBHOOK INFO
# =====================================================

async def webhook_info(
    request
):

    try:

        bot = request.app[
            "bot"
        ]

        info = (
            await bot.get_webhook_info()
        )


        return web.json_response(

            {

                "url":
                    info.url,

                "pending_update_count":
                    info.pending_update_count,

                "last_error_date":
                    info.last_error_date,

                "last_error_message":
                    info.last_error_message,

                "max_connections":
                    info.max_connections

            }

        )


    except Exception as e:

        return web.json_response(

            {

                "error":
                    str(e)

            },

            status=500

        )


# =====================================================
# STARTUP
# =====================================================

async def on_startup(
    app
):

    bot = app[
        "bot"
    ]


    webhook_url = (

        RENDER_URL.rstrip("/")

        +
        "/telegram-webhook"

    )


    print(
        "================================"
    )

    print(
        "🚀 SAVE SNOSER STARTING"
    )

    print(
        "WEBHOOK:",
        webhook_url
    )

    print(
        "MINI APP:",
        WEB_APP_URL
    )

    print(
        "OWNERS:",
        OWNER_IDS
    )

    print(
        "================================"
    )


    try:

        # Удаляем старый webhook
        await bot.delete_webhook(
            drop_pending_updates=True
        )

        print(
            "Old webhook deleted"
        )


        # Ставим новый
        await bot.set_webhook(

            url=
                webhook_url,

            drop_pending_updates=True

        )


        print(
            "New webhook set"
        )


        info = (
            await bot.get_webhook_info()
        )


        print(
            "================================"
        )

        print(
            "TELEGRAM WEBHOOK INFO"
        )

        print(
            "URL:",
            info.url
        )

        print(
            "PENDING:",
            info.pending_update_count
        )

        print(
            "LAST ERROR:",
            info.last_error_message
        )

        print(
            "================================"
        )


    except Exception as e:

        print(
            "❌ WEBHOOK SET ERROR:",
            repr(e)
        )


# =====================================================
# CLEANUP
# =====================================================

async def on_cleanup(
    app
):

    bot = app[
        "bot"
    ]


    try:

        await bot.delete_webhook()

    except Exception as e:

        print(
            "Webhook delete error:",
            repr(e)
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

            "BOT_TOKEN не найден "
            "в Environment Variables."

        )


    print(
        "BOT TOKEN FOUND"
    )


    init_db()


    bot = Bot(
        BOT_TOKEN
    )


    # =================================================
    # DISPATCHER
    # =================================================

    global dp


    # =================================================
    # WEB APP
    # =================================================

    app = web.Application()


    app["bot"] = bot


    # Health
    app.router.add_get(

        "/health",

        health

    )


    # Webhook
    app.router.add_post(

        "/telegram-webhook",

        webhook

    )


    # Mini App access
    app.router.add_post(

        "/api/access",

        check_access

    )


    # Webhook information
    app.router.add_get(

        "/webhook-info",

        webhook_info

    )


    # Startup
    app.on_startup.append(

        on_startup

    )


    # Cleanup
    app.on_cleanup.append(

        on_cleanup

    )


    print(
        "================================"
    )

    print(
        "SERVER STARTING"
    )

    print(
        "PORT:",
        PORT
    )

    print(
        "================================"
    )


    await web._run_app(

        app,

        host=
            "0.0.0.0",

        port=
            PORT

    )


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
