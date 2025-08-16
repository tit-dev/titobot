
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
import os
import time
from datetime import datetime, timedelta
import asyncio
import json

# Простая файловая база данных как замена replit db
class SimpleDB:
    def __init__(self, filename='bot_data.json'):
        self.filename = filename
        self.data = self._load_data()

    def _load_data(self):
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_data(self):
        with open(self.filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self._save_data()

db = SimpleDB()

cards = [
    ("🟢 Обычная: Простой Манго", 12),
    ("🟢 Обычная: Денчик", 12),
    ("🟢 Обычная: Просроченная Горчица", 12),
    ("🟢 Обычная: Kanye West", 12),
    ("🔵 Необычная: Горчица", 6),
    ("🔵 Необычная: Троллфейс", 6),
    ("🔵 Необычная: Тантум Верде", 6),
    ("🔵 Необычная: Sigeon Pex", 6),
    ("🟣 Эпическая: Американский Психопат", 3.5),
    ("🟣 Эпическая: Мистер Гун", 3.5),
    ("🟣 Эпическая: Доктор Гун", 3.5),
    ("🟣 Эпическая: Открой Базу и Верни Мне БР БР Патапима", 3.5),
    ("🟠 Легендарная: Манго Марк", 2),
    ("🟠 Легендарная: Король Горчицы", 2),
    ("🟠 Легендарная: Китайский Вождь", 2),
    ("🟠 Легендарная: J_Манго", 2),
    ("🔴 Мифическая: Манго Спонсор", 0.25),
    ("🔴 Мифическая: Омни-Манго", 0.25),
    ("🔴 Мифическая: Манго Троллфейс", 0.25),
    ("🔴 Мифическая: Горчица Матвея", 0.25),
    ("⚫ Секретная: Kendrick Lamar", 0.25),
]

# Специальные карты для покера
POKER_CARD = "⭐ Уникальная: Мастер Покера"
POKER_67_CARD = "⭐ Уникальная: 67"

# Рейтинги редкости для подсчета очков в покере
rarity_scores = {
    "🟢": 1,  # Обычная
    "🔵": 2,  # Необычная
    "🟣": 3,  # Эпическая
    "🟠": 4,  # Легендарная
    "🔴": 5,  # Мифическая
    "⚫": 10,  # Секретная
    "⭐": 6,  # Уникальная (покерная)
}

# Глобальное хранилище активных игр
active_games = {}
pending_challenges = {}
pending_trades = {}

def roll_card():
    roll = random.uniform(0, 100)
    total = 0
    for card, chance in cards:
        total += chance
        if roll <= total:
            return card
    return cards[0][0]

def roll_lucky_card():
    # Только эпические, легендарные, мифические и секретные карточки
    lucky_cards = [card for card, chance in cards if chance <= 3.5]
    weights = [chance for card, chance in cards if chance <= 3.5]
    return random.choices(lucky_cards, weights=weights, k=1)[0]

def get_user_cards(user_id):
    user_key = f"user_{user_id}"
    return db[user_key] if user_key in db else {}

def add_card_to_user(user_id, card):
    user_key = f"user_{user_id}"
    user_cards = get_user_cards(user_id)
    user_cards[card] = user_cards.get(card, 0) + 1
    db[user_key] = user_cards

def get_user_coins(user_id):
    coins_key = f"coins_{user_id}"
    return db[coins_key] if coins_key in db else 100

def set_user_coins(user_id, coins):
    coins_key = f"coins_{user_id}"
    db[coins_key] = coins

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_cards = get_user_cards(user_id)
    coins = get_user_coins(user_id)
    
    if not user_cards:
        # Новый игрок - даем стартовые карты
        for _ in range(3):
            card = roll_card()
            add_card_to_user(user_id, card)
    
    keyboard = [
        [InlineKeyboardButton("🎁 Открыть карту", callback_data="open_card")],
        [InlineKeyboardButton("📦 Мои карты", callback_data="my_cards")],
        [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("🃏 Mustard Poker", callback_data="poker_menu")],
        [InlineKeyboardButton("🔄 Трейд", callback_data="trade_menu")],
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🃏 Добро пожаловать в Mustard Card Bot!\n\n"
        "Коллекционируй карты, участвуй в покере и торгуй с другими игроками!",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == "open_card":
        coins = get_user_coins(user_id)
        if coins >= 10:
            card = roll_card()
            add_card_to_user(user_id, card)
            set_user_coins(user_id, coins - 10)
            
            await query.edit_message_text(
                f"🎉 Ты получил карту: {card}\n"
                f"💰 Осталось монет: {coins - 10}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")
                ]])
            )
        else:
            await query.edit_message_text(
                "❌ Недостаточно монет! Нужно 10 монет для открытия карты.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")
                ]])
            )
    
    elif query.data == "my_cards":
        user_cards = get_user_cards(user_id)
        if user_cards:
            cards_text = "📦 Твои карты:\n\n"
            for card, count in sorted(user_cards.items()):
                cards_text += f"{card} x{count}\n"
        else:
            cards_text = "📦 У тебя пока нет карт!"
        
        await query.edit_message_text(
            cards_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")
            ]])
        )
    
    elif query.data == "balance":
        coins = get_user_coins(user_id)
        await query.edit_message_text(
            f"💰 Твой баланс: {coins} монет",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")
            ]])
        )
    
    elif query.data == "back_to_menu":
        keyboard = [
            [InlineKeyboardButton("🎁 Открыть карту", callback_data="open_card")],
            [InlineKeyboardButton("📦 Мои карты", callback_data="my_cards")],
            [InlineKeyboardButton("💰 Баланс", callback_data="balance")],
            [InlineKeyboardButton("🃏 Mustard Poker", callback_data="poker_menu")],
            [InlineKeyboardButton("🔄 Трейд", callback_data="trade_menu")],
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🃏 Mustard Card Bot\n\n"
            "Выбери действие:",
            reply_markup=reply_markup
        )

def main():
    """Основная функция запуска бота"""
    bot_token = os.getenv('8216384677:AAFLKENl0wiM87HMJxomy4aoLUUOcgYljR0')
    
    if not bot_token:
        print("❌ Ошибка: BOT_TOKEN не установлен в переменных окружения")
        return
    
    print("🤖 Запуск Mustard Card Bot...")
    
    # Создаем приложение
    application = ApplicationBuilder().token(bot_token).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запуск бота
    print("✅ Бот запущен и готов к работе!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
