import os
import asyncio

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

# Сколько Stars стоит доступ
PRICE_STARS = 10

# СЮДА ПОТОМ ПОСТАВИМ ССЫЛКУ НА ТВОЙ MINI APP
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://YOUR-APP.onrender.com")

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
        f"Чтобы получить доступ, оплати {PRICE_STARS} Stars.",
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
                    web_app={"url": WEB_APP_URL}
                )
            ]
        ]
    )

    await message.answer(
        "✅ Оплата прошла успешно!\n\n"
        "Теперь тебе доступен Mini App:",
        reply_markup=keyboard
    )


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в Environment Variables")

    bot = Bot(BOT_TOKEN)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
