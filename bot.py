import os
import asyncio

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

PRICE_STARS = 10

WEB_APP_URL = "https://kdjebr.onrender.com/"

PORT = int(os.getenv("PORT", "10000"))

dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"⭐ Оплатить {PRICE_STARS} Stars",
                    callback_data="buy_access"
                )
            ]
        ]
    )

    await message.answer(
        "🔒 Доступ к Mini App закрыт.\n\n"
        f"Стоимость доступа: {PRICE_STARS} ⭐ Stars.\n\n"
        "Оплати доступ, после чего появится кнопка для открытия Mini App.",
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "buy_access")
async def buy_access(callback):
    await callback.answer()

    prices = [
        LabeledPrice(
            label="Доступ к Mini App",
            amount=PRICE_STARS
        )
    ]

    await callback.message.answer_invoice(
        title="Доступ к Mini App",
        description="Доступ к Mini App после оплаты.",
        payload="mini_app_access",
        currency="XTR",
        prices=prices,
        provider_token=""
    )


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment

    if payment.invoice_payload != "mini_app_access":
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Открыть Mini App",
                    web_app={
                        "url": WEB_APP_URL
                    }
                )
            ]
        ]
    )

    await message.answer(
        "✅ Оплата прошла успешно!\n\n"
        "Доступ к Mini App получен.",
        reply_markup=keyboard
    )


async def handle_webhook(request):
    try:
        data = await request.json()
        update = Update.model_validate(data)

        bot = request.app["bot"]

        await dp.feed_update(
            bot,
            update
        )

        return web.Response(text="OK")

    except Exception as e:
        print("Webhook error:", e)
        return web.Response(
            status=500,
            text="Error"
        )


async def health(request):
    return web.Response(
        text="Bot is running"
    )


async def on_startup(app):
    bot = app["bot"]

    render_url = os.getenv("RENDER_EXTERNAL_URL")

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


async def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан"
        )

    bot = Bot(BOT_TOKEN)

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
