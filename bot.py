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


# ============================================================
# CONFIG
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

PORT = int(os.getenv("PORT", "10000"))

WEB_APP_URL = "https://demuge.github.io/Kdjebr/"

DB_FILE = "users.db"


# ============================================================
# ТВОИ 2 БЕСПЛАТНЫХ АККАУНТА
# ============================================================

OWNER_IDS = {
    8958072114,
    8140798671,
}


# ============================================================
# DISPATCHER
# ============================================================

dp = Dispatcher()


# ============================================================
# DATABASE
# ============================================================

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
        """
        SELECT
            telegram_id,
            username,
            plan,
            expires_at,
            payment_id
        FROM users
        WHERE telegram_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return row


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


# ============================================================
# ACCESS
# ============================================================

def is_owner(user_id):

    try:

        return int(user_id) in OWNER_IDS

    except Exception:

        return False


def has_access(user_id):

    # Твои аккаунты всегда имеют доступ
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
# MINI APP INIT DATA
# ============================================================

def validate_init_data(init_data):

    if not init_data:

        print("Mini App: initData отсутствует")

        return None

    if not BOT_TOKEN:

        print("Mini App: BOT_TOKEN отсутствует")

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

            print("Mini App: hash отсутствует")

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

            print("Mini App: неправильный hash")

            return None

        auth_date = int(
            data.get(
                "auth_date",
                "0"
            )
        )

        # InitData не старше 24 часов
        if int(time.time()) - auth_date > 86400:

            print("Mini App: initData устарела")

            return None

        user = json.loads(
            data.get(
                "user",
                "{}"
            )
        )

        if not user.get("id"):

            print("Mini App: ID пользователя отсутствует")

            return None

        return user

    except Exception as e:

        print(
            "Mini App validation error:",
            repr(e)
        )

        return None


# ============================================================
# TARIFFS
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
# MINI APP BUTTON
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
# PAYMENT BUTTONS
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
            ]

        ]
    )


# ============================================================
# /START
# ============================================================

@dp.message(CommandStart())
async def start_handler(message: Message):

    user_id = message.from_user.id

    print(
        f"/start получен от пользователя: {user_id}"
    )

    # ========================================================
    # ТВОИ ДВА АККАУНТА
    # ========================================================

    if is_owner(user_id):

        await message.answer(
            "👑 <b>SAVE SNOSER</b>\n\n"
            "Твой аккаунт имеет бесплатный доступ.\n\n"
            "🚀 Открывай Mini App:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # ========================================================
    # ЕСЛИ УЖЕ ОПЛАЧИВАЛ
    # ========================================================

    if has_access(user_id):

        await message.answer(
            "✅ <b>Premium активен.</b>\n\n"
            "🚀 Открывай SAVE SNOSER:",
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
        "Выбери тариф:",
        reply_markup=premium_keyboard(),
        parse_mode="HTML"
    )


# ============================================================
# PAYMENT
# ============================================================

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
            "Ошибка создания invoice:",
            repr(e)
        )

        await callback.answer(
            "Не удалось создать оплату.",
            show_alert=True
        )


# ============================================================
# PRE CHECKOUT
# ============================================================

@dp.pre_checkout_query()
async def pre_checkout_handler(
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
# SUCCESSFUL PAYMENT
# ============================================================

@dp.message(
    F.successful_payment
)
async def successful_payment_handler(
    message: Message
):

    try:

        payment = message.successful_payment

        if not payment:

            return

        payload = payment.invoice_payload

        print(
            "УСПЕШНАЯ ОПЛАТА:",
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
                "Неизвестный тариф:",
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

        # НАВСЕГДА
        if plan["duration"] == 0:

            expires_at = 0

        else:

            if old_expiration > now:

                start = old_expiration

            else:

                start = now

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
            "✅ Premium активирован.\n\n"
            "Теперь тебе доступен SAVE SNOSER:",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        print(
            "Доступ выдан:",
            user_id,
            "до:",
            expires_at
        )

    except Exception as e:

        print(
            "Payment handler error:",
            repr(e)
        )


# ============================================================
# MINI APP ACCESS
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
                        "Недействительная авторизация Telegram."
                },
                status=401
            )

        user_id = int(
            user["id"]
        )

        print(
            "Mini App access:",
            user_id
        )

        # ТВОИ ДВА АККАУНТА
        if is_owner(user_id):

            return web.json_response(
                {
                    "ok": True,
                    "access": True,
                    "owner": True,
                    "expires_at": 0
                }
            )

        # ОПЛАТА
        if not has_access(user_id):

            return web.json_response(
                {
                    "ok": True,
                    "access": False,
                    "owner": False,
                    "message":
                        "Необходимо приобрести Premium."
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
                    "Ошибка сервера."
            },
            status=500
        )


# ============================================================
# HEALTH
# ============================================================

async def health(request):

    return web.json_response(
        {
            "ok": True,
            "service": "SAVE SNOSER backend",
            "bot": "polling"
        }
    )


# ============================================================
# WEB SERVER
# ============================================================

async def start_web_server():

    app = web.Application()

    app.router.add_get(
        "/",
        health
    )

    app.router.add_get(
        "/health",
        health
    )

    app.router.add_post(
        "/api/access",
        check_access
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    print(
        f"HTTP server started on port {PORT}"
    )

    return runner


# ============================================================
# BOT POLLING
# ============================================================

async def start_bot():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не найден в Render Environment."
        )

    bot = Bot(
        token=BOT_TOKEN
    )

    # --------------------------------------------------------
    # УДАЛЯЕМ СТАРЫЙ WEBHOOK
    # --------------------------------------------------------
    #
    # Это очень важно.
    #
    # Если раньше у бота был webhook,
    # Telegram не даст нормально использовать polling.
    #

    print(
        "Удаляем старый webhook..."
    )

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    print(
        "Webhook удалён."
    )

    # --------------------------------------------------------
    # Проверяем бота
    # --------------------------------------------------------

    me = await bot.get_me()

    print(
        "===================================="
    )

    print(
        "SAVE SNOSER BOT STARTED"
    )

    print(
        "Bot:",
        me.username
    )

    print(
        "Bot ID:",
        me.id
    )

    print(
        "Owners:",
        OWNER_IDS
    )

    print(
        "Mini App:",
        WEB_APP_URL
    )

    print(
        "===================================="
    )

    # --------------------------------------------------------
    # POLLING
    # --------------------------------------------------------

    try:

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types()
        )

    finally:

        await bot.session.close()


# ============================================================
# MAIN
# ============================================================

async def main():

    # Database
    init_db()

    # HTTP server
    web_runner = await start_web_server()

    try:

        # Telegram polling
        await start_bot()

    finally:

        await web_runner.cleanup()


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
            "SAVE SNOSER stopped."
        )
