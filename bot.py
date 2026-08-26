import os
import asyncio
import sqlite3
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Твой Mini App
WEB_APP_URL = "https://demuge.github.io/Kdjebr/"

DB_FILE = "users.db"


# =========================================================
# ДВА БЕСПЛАТНЫХ АККАУНТА
# =========================================================

OWNER_IDS = {
    8958072114,
    8140798671,
}


# =========================================================
# ТАРИФЫ
# =========================================================

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


# =========================================================
# DISPATCHER
# =========================================================

dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

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


# =========================================================
# ACCESS
# =========================================================

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


# =========================================================
# MINI APP BUTTON
# =========================================================

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


# =========================================================
# PAYMENT BUTTONS
# =========================================================

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


# =========================================================
# /START
# =========================================================

@dp.message(CommandStart())
async def start(message: Message):

    user = message.from_user

    if not user:
        return

    user_id = user.id

    print(
        f"/start от пользователя "
        f"{user_id} "
        f"@{user.username or 'no_username'}"
    )

    # =====================================================
    # ТВОИ ДВА АККАУНТА
    # =====================================================

    if is_owner(user_id):

        await message.answer(
            "👑 <b>SAVE SNOSER</b>\n\n"
            "Тебе доступ открыт бесплатно.\n\n"
            "🚀 Нажми кнопку ниже, чтобы открыть Mini App.",
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # ОСТАЛЬНЫЕ ПОЛЬЗОВАТЕЛИ
    # =====================================================

    if has_access(user_id):

        user_db = get_user(user_id)

        expires_at = user_db[3] if user_db else 0

        if expires_at == 0:

            text = (
                "👑 <b>SAVE SNOSER PREMIUM</b>\n\n"
                "Твой доступ: <b>НАВСЕГДА</b>.\n\n"
                "🚀 Открывай Mini App."
            )

        else:

            remaining = expires_at - int(time.time())

            if remaining < 0:
                remaining = 0

            days = remaining // 86400
            hours = (remaining % 86400) // 3600

            text = (
                "⭐ <b>SAVE SNOSER PREMIUM</b>\n\n"
                f"Доступ ещё примерно: "
                f"<b>{days} д. {hours} ч.</b>\n\n"
                "🚀 Открывай Mini App."
            )

        await message.answer(
            text,
            reply_markup=mini_app_keyboard(),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # НЕТ ОПЛАТЫ
    # =====================================================

    await message.answer(
        "✨ <b>SAVE SNOSER</b>\n\n"
        "Для доступа к Mini App необходимо "
        "активировать Premium.\n\n"
        "Выбери тариф:",
        reply_markup=premium_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# ВЫБОР ТАРИФА
# =========================================================

@dp.callback_query(
    F.data.in_(PLANS.keys())
)
async def select_plan(callback):

    if not callback.from_user:
        return

    plan_id = callback.data
    plan = PLANS[plan_id]

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

            # Telegram Stars
            provider_token=""

        )

        await callback.answer()

    except Exception as e:

        print(
            "PAYMENT ERROR:",
            repr(e)
        )

        await callback.answer(
            "Ошибка создания оплаты. Попробуй ещё раз.",
            show_alert=True
        )


# =========================================================
# PRE-CHECKOUT
# =========================================================

@dp.pre_checkout_query()
async def pre_checkout(
    query: PreCheckoutQuery
):

    try:

        await query.answer(
            ok=True
        )

        print(
            "PreCheckout OK:",
            query.id
        )

    except Exception as e:

        print(
            "PRECHECKOUT ERROR:",
            repr(e)
        )


# =========================================================
# УСПЕШНАЯ ОПЛАТА
# =========================================================

@dp.message(F.successful_payment)
async def successful_payment(
    message: Message
):

    payment = message.successful_payment

    if not payment:
        return

    payload = payment.invoice_payload

    print(
        "PAYMENT:",
        payload
    )

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

    # =====================================================
    # НАВСЕГДА
    # =====================================================

    if plan["duration"] == 0:

        expires_at = 0

    # =====================================================
    # ВРЕМЕННОЙ ТАРИФ
    # =====================================================

    else:

        if old_expiration and old_expiration > now:

            start_time = old_expiration

        else:

            start_time = now

        expires_at = (
            start_time +
            plan["duration"]
        )

    save_access(
        user_id=user_id,
        username=username,
        plan=plan_id,
        expires_at=expires_at,
        payment_id=payment.telegram_payment_charge_id
    )

    # =====================================================
    # ОТПРАВЛЯЕМ MINI APP ПОСЛЕ ОПЛАТЫ
    # =====================================================

    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        "Premium активирован.\n\n"
        "Теперь тебе доступен SAVE SNOSER.",
        reply_markup=mini_app_keyboard(),
        parse_mode="HTML"
    )

    print(
        f"ACCESS GRANTED: "
        f"user={user_id}, "
        f"plan={plan_id}, "
        f"expires={expires_at}"
    )


# =========================================================
# ERROR HANDLER
# =========================================================

@dp.errors()
async def errors_handler(event):

    print(
        "BOT ERROR:",
        repr(event.exception)
    )


# =========================================================
# MAIN
# =========================================================

async def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN не найден!"
        )

    print(
        "===================================="
    )

    print(
        "SAVE SNOSER BOT"
    )

    print(
        "Starting..."
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

    # =====================================================
    # DATABASE
    # =====================================================

    init_db()

    # =====================================================
    # BOT
    # =====================================================

    bot = Bot(
        token=BOT_TOKEN
    )

    # =====================================================
    # УДАЛЯЕМ СТАРЫЙ WEBHOOK
    #
    # Это ОЧЕНЬ важно после Render.
    # Иначе Telegram может не отдавать обновления
    # через polling.
    # =====================================================

    print(
        "Removing old Telegram webhook..."
    )

    await bot.delete_webhook(
        drop_pending_updates=False
    )

    print(
        "Webhook removed."
    )

    # =====================================================
    # ПРОВЕРЯЕМ BOT
    # =====================================================

    me = await bot.get_me()

    print(
        f"Logged in as "
        f"@{me.username}"
    )

    print(
        "Polling started."
    )

    # =====================================================
    # LONG POLLING
    # =====================================================

    try:

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            polling_timeout=30
        )

    finally:

        await bot.session.close()


# =========================================================
# START
# =========================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "Bot stopped."
        )

    except Exception as e:

        print(
            "FATAL ERROR:",
            repr(e)
        )
