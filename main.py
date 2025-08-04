import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
from keep_alive import keep_alive
import os
import time
from datetime import datetime, timedelta
import asyncio

# Простая файловая база данных как замена replit db
import json

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
    lucky_cards = [
        # Эпические карты
        ("🟣 Эпическая: Американский Психопат", 20),
        ("🟣 Эпическая: Мистер Гун", 20),
        ("🟣 Эпическая: Доктор Гун", 20),
        ("🟣 Эпическая: Открой Базу и Верни Мне БР БР Патапима", 20),
        # Легендарные карты
        ("🟠 Легендарная: Манго Марк", 8),
        ("🟠 Легендарная: Король Горчицы", 8),
        ("🟠 Легендарная: Китайский Вождь", 2),
        ("🟠 Легендарная: J_Манго", 1),
        # Мифические карты
        ("🔴 Мифическая: Манго Спонсор", 0.25),
        ("🔴 Мифическая: Омни-Манго", 0.25),
        ("🔴 Мифическая: Манго Троллфейс", 0.25),
        ("🔴 Мифическая: Горчица Матвея", 0.25),
        # Секретная карта
        ("⚫ Секретная: Kendrick Lamar", 0.5),
    ]

    roll = random.uniform(0, 100)
    total = 0
    for card, chance in lucky_cards:
        total += chance
        if roll <= total:
            return card
    return lucky_cards[0][0]

def roll_poker_card():
    # Для покера все карты имеют равные шансы
    poker_cards = [card[0] for card in cards] + [POKER_CARD, POKER_67_CARD]
    return random.choice(poker_cards)

def add_card_to_inventory(user_id, card):
    user_key = f"user_{user_id}"
    if user_key in db:
        inventory = db[user_key]
    else:
        inventory = {}

    if card in inventory:
        inventory[card] += 1
    else:
        inventory[card] = 1

    db[user_key] = inventory

def remove_card_from_inventory(user_id, card, amount=1):
    user_key = f"user_{user_id}"
    if user_key in db:
        inventory = db[user_key]
        if card in inventory and inventory[card] >= amount:
            inventory[card] -= amount
            if inventory[card] == 0:
                del inventory[card]
            db[user_key] = inventory
            return True
    return False

def get_user_inventory(user_id):
    user_key = f"user_{user_id}"
    if user_key in db:
        return db[user_key]
    return {}

def get_last_lucky_time(user_id):
    lucky_key = f"lucky_{user_id}"
    if lucky_key in db:
        return db[lucky_key]
    return 0

def set_last_lucky_time(user_id, timestamp):
    lucky_key = f"lucky_{user_id}"
    db[lucky_key] = timestamp

def get_last_card_time(user_id):
    card_key = f"card_{user_id}"
    if card_key in db:
        return db[card_key]
    return 0

def set_last_card_time(user_id, timestamp):
    card_key = f"card_{user_id}"
    db[card_key] = timestamp

def get_last_poker_time(user_id):
    poker_key = f"poker_{user_id}"
    if poker_key in db:
        return db[poker_key]
    return 0

def set_last_poker_time(user_id, timestamp):
    poker_key = f"poker_{user_id}"
    db[poker_key] = timestamp

def get_poker_wins(user_id):
    wins_key = f"poker_wins_{user_id}"
    if wins_key in db:
        return db[wins_key]
    return 0

def add_poker_win(user_id):
    wins_key = f"poker_wins_{user_id}"
    current_wins = get_poker_wins(user_id)
    db[wins_key] = current_wins + 1

def get_user_coins(user_id):
    coins_key = f"coins_{user_id}"
    if coins_key in db:
        return db[coins_key]
    return 0

def get_user_slots(user_id):
    """Получает количество слотов для продажи (по умолчанию 2)"""
    slots_key = f"slots_{user_id}"
    if slots_key in db:
        return db[slots_key]
    return 2

def add_user_slot(user_id):
    """Добавляет 1 слот пользователю"""
    slots_key = f"slots_{user_id}"
    current_slots = get_user_slots(user_id)
    db[slots_key] = current_slots + 1

def add_coins(user_id, amount):
    coins_key = f"coins_{user_id}"
    current_coins = get_user_coins(user_id)
    db[coins_key] = current_coins + amount

def remove_coins(user_id, amount):
    coins_key = f"coins_{user_id}"
    current_coins = get_user_coins(user_id)
    if current_coins >= amount:
        db[coins_key] = current_coins - amount
        return True
    return False

def get_last_mine_time(user_id):
    mine_key = f"mine_{user_id}"
    if mine_key in db:
        return db[mine_key]
    return 0

def set_last_mine_time(user_id, timestamp):
    mine_key = f"mine_{user_id}"
    db[mine_key] = timestamp

def get_lucky_uses(user_id):
    lucky_uses_key = f"lucky_uses_{user_id}"
    if lucky_uses_key in db:
        return db[lucky_uses_key]
    return 0

def set_lucky_uses(user_id, uses):
    lucky_uses_key = f"lucky_uses_{user_id}"
    db[lucky_uses_key] = uses

def get_daily_shop():
    """Генерирует ежедневный магазин"""
    today = datetime.now().strftime("%Y-%m-%d")
    shop_key = f"shop_{today}"

    if shop_key in db:
        return db[shop_key]

    # Генерируем новый магазин
    shop_items = []

    # Добавляем карты с разными шансами (чем реже карта, тем меньше шанс)
    for card, base_chance in cards:
        # Увеличиваем шансы появления в магазине в 3 раза по сравнению с /card
        shop_chance = base_chance * 3
        if random.random() * 100 <= shop_chance:
            # Цена зависит от редкости
            if card.startswith("🟢"):  # Обычная
                price = random.randint(50, 100)
            elif card.startswith("🔵"):  # Необычная
                price = random.randint(150, 250)
            elif card.startswith("🟣"):  # Эпическая
                price = random.randint(400, 600)
            elif card.startswith("🟠"):  # Легендарная
                price = random.randint(800, 1200)
            elif card.startswith("🔴"):  # Мифическая
                price = random.randint(2000, 3000)
            elif card.startswith("⚫"):  # Секретная
                price = random.randint(5000, 7000)
            else:
                price = 100

            shop_items.append({
                "card": card,
                "price": price
            })

    # Ограничиваем количество товаров до 29 (чтобы с Lucky Card было максимум 30)
    if len(shop_items) > 29:
        shop_items = random.sample(shop_items, 29)

    # Добавляем Lucky Cards (1, 2 или 3 штуки)
    lucky_count = random.choice([1, 2, 3])
    lucky_price_per_use = 300
    shop_items.append({
        "card": f"🍀 Lucky Card × {lucky_count}",
        "price": lucky_price_per_use * lucky_count,
        "special": "lucky",
        "count": lucky_count
    })

    # Сохраняем магазин на день
    db[shop_key] = shop_items
    return shop_items

def get_user_purchases_today(user_id):
    """Получает покупки пользователя за сегодня"""
    today = datetime.now().strftime("%Y-%m-%d")
    purchases_key = f"purchases_{user_id}_{today}"
    if purchases_key in db:
        return db[purchases_key]
    return []

def add_user_purchase_today(user_id, item):
    """Добавляет покупку пользователю за сегодня"""
    today = datetime.now().strftime("%Y-%m-%d")
    purchases_key = f"purchases_{user_id}_{today}"
    purchases = get_user_purchases_today(user_id)
    purchases.append(item)
    db[purchases_key] = purchases

def get_market_cards():
    """Получает список карт на продажу"""
    if "market_cards" in db:
        return db["market_cards"]
    return []

def add_card_to_market(card, price, seller_id, seller_name):
    """Добавляет карту на рынок"""
    market_cards = get_market_cards()
    market_cards.append({
        "card": card,
        "price": price,
        "seller_id": seller_id,
        "seller_name": seller_name,
        "timestamp": time.time(),
        "type": "market"
    })
    db["market_cards"] = market_cards

def remove_card_from_market(index):
    """Удаляет карту с рынка по индексу"""
    market_cards = get_market_cards()
    if 0 <= index < len(market_cards):
        removed_card = market_cards.pop(index)
        db["market_cards"] = market_cards
        return removed_card
    return None

def cleanup_expired_market_cards():
    """Удаляет карты старше 24 часов и возвращает их владельцам"""
    market_cards = get_market_cards()
    current_time = time.time()
    expired_cards = []
    active_cards = []
    
    # Разделяем на просроченные и активные
    for card_data in market_cards:
        if current_time - card_data['timestamp'] > 24 * 60 * 60:  # 24 часа
            expired_cards.append(card_data)
        else:
            active_cards.append(card_data)
    
    # Возвращаем просроченные карты владельцам
    for card_data in expired_cards:
        add_card_to_inventory(card_data['seller_id'], card_data['card'])
    
    # Обновляем рынок только активными картами
    if len(expired_cards) > 0:
        db["market_cards"] = active_cards
    
    return len(expired_cards)

def get_best_non_unique_card(user_id):
    """Находит лучшую карту игрока (исключая уникальные)"""
    inventory = get_user_inventory(user_id)
    if not inventory:
        return None

    # Исключаем уникальные карты (те что начинаются с ⭐)
    non_unique_cards = {card: count for card, count in inventory.items() 
                       if not card.startswith("⭐") and count > 0}

    if not non_unique_cards:
        return None

    # Сортируем карты по редкости (по убыванию ценности)
    rarity_order = {"🔴": 5, "🟠": 4, "🟣": 3, "🔵": 2, "🟢": 1}

    best_card = None
    best_rarity = 0

    for card in non_unique_cards:
        card_rarity = rarity_order.get(card[0], 0)
        if card_rarity > best_rarity:
            best_rarity = card_rarity
            best_card = card

    return best_card

def calculate_poker_score(hand):
    rarity_counts = {}
    for card in hand:
        rarity = card[0]  # Первый символ - эмодзи редкости
        rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1

    total_score = 0
    for rarity, count in rarity_counts.items():
        score = rarity_scores.get(rarity, 0)
        total_score += score * count

    return total_score, rarity_counts

def format_time_remaining(seconds):
    if seconds <= 0:
        return "0 секунд"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours} ч")
    if minutes > 0:
        parts.append(f"{minutes} мин")
    if secs > 0:
        parts.append(f"{secs} сек")

    return " ".join(parts)

async def get_user_display_name(context, chat_id, user_id):
    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        user = chat_member.user

        if user.username:
            return f"@{user.username}"
        elif user.first_name and user.last_name:
            return f"{user.first_name} {user.last_name}"
        elif user.first_name:
            return user.first_name
        else:
            return f"ID: {user_id}"
    except:
        return f"ID: {user_id}"

async def get_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_time = time.time()
    last_card_time = get_last_card_time(user_id)

    # Проверяем, прошло ли 60 секунд
    cooldown_time = 60  # 60 секунд
    time_passed = current_time - last_card_time

    if time_passed < cooldown_time:
        time_remaining = cooldown_time - time_passed
        formatted_time = format_time_remaining(time_remaining)
        await update.message.reply_text(
            f"⏰ Команду /card можно использовать снова через: {formatted_time}"
        )
        return

    card = roll_card()

    # Добавляем карточку в инвентарь
    add_card_to_inventory(user_id, card)

    # Обновляем время последнего использования
    set_last_card_time(user_id, current_time)

    await update.message.reply_text(f"🎉 Ты выбил: {card}")

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Определяем чей профиль показать
    if update.message.reply_to_message:
        # Если это ответ на сообщение, показываем профиль того пользователя
        target_user_id = update.message.reply_to_message.from_user.id
        target_user_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        # Если нет ответа на сообщение, показываем свой профиль
        target_user_id = update.effective_user.id
        target_user_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)

    inventory = get_user_inventory(target_user_id)
    poker_wins = get_poker_wins(target_user_id)
    coins = get_user_coins(target_user_id)

    if not inventory:
        profile_text = f"👤 Профиль {target_user_name}\n\n"
        profile_text += "📦 Инвентарь: Пуст\n"
        profile_text += "📊 Всего карт: 0\n"
        profile_text += f"🪙 Монеты: {coins}\n"
        profile_text += f"🃏 Побед в покере: {poker_wins}\n\n"
        
        if target_user_id == update.effective_user.id:
            profile_text += "💡 Используй /card чтобы получить карточки!"

        await update.message.reply_text(profile_text)
        return

    # Сортируем карточки по редкости (по порядку в списке cards)
    card_order = {card[0]: i for i, card in enumerate(cards)}
    card_order[POKER_CARD] = -1  # Покерная карта в начале
    card_order[POKER_67_CARD] = -2  # Вторая покерная карта
    sorted_inventory = sorted(inventory.items(), key=lambda x: card_order.get(x[0], 999))

    total_cards = sum(inventory.values())

    profile_text = f"👤 Профиль {target_user_name}\n\n"
    profile_text += "📦 Инвентарь:\n"

    for card, count in sorted_inventory:
        # Экранируем специальные символы для Markdown
        escaped_card = card.replace('_', '\\_').replace('-', '\\-')
        profile_text += f"{escaped_card} × {count}\n"

    profile_text += f"\n📊 Всего карт: {total_cards}\n"
    profile_text += f"🪙 Монеты: {coins}\n"
    profile_text += f"🃏 Побед в покере: {poker_wins}"

    await update.message.reply_text(profile_text)

async def lucky_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_time = time.time()
    last_lucky_time = get_last_lucky_time(user_id)
    lucky_uses = get_lucky_uses(user_id)

    # Проверяем, есть ли купленные использования
    if lucky_uses > 0:
        # Используем купленное использование
        card = roll_lucky_card()
        add_card_to_inventory(user_id, card)
        set_lucky_uses(user_id, lucky_uses - 1)

        remaining_uses = lucky_uses - 1
        uses_text = f"\n🎫 Осталось использований: {remaining_uses}" if remaining_uses > 0 else "\n⏰ Следующий Lucky Card будет доступен через 2 часа!"

        await update.message.reply_text(
            f"🍀 LUCKY CARD! 🍀\n\n"
            f"✨ Ты выбил: {card}{uses_text}",
            parse_mode='Markdown'
        )
        return

    # Проверяем кулдаун (2 часа)
    cooldown_time = 2 * 60 * 60  # 2 часа в секундах
    time_passed = current_time - last_lucky_time

    if time_passed < cooldown_time:
        time_remaining = cooldown_time - time_passed
        formatted_time = format_time_remaining(time_remaining)
        await update.message.reply_text(
            f"⏰ Lucky Card еще недоступен!\n"
            f"Попробуй снова через: {formatted_time}\n\n"
            f"💡 Купи Lucky Card в магазине (/shop) чтобы использовать без кулдауна!"
        )
        return

    # Получаем lucky карточку
    card = roll_lucky_card()

    # Добавляем карточку в инвентарь
    add_card_to_inventory(user_id, card)

    # Обновляем время последнего использования
    set_last_lucky_time(user_id, current_time)

    await update.message.reply_text(
        f"🍀 LUCKY CARD! 🍀\n\n"
        f"✨ Ты выбил: {card}\n\n"
        f"⏰ Следующий Lucky Card будет доступен через 2 часа!",
        parse_mode='Markdown'
    )

async def show_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Собираем всех пользователей и их количество карточек
    users_stats = []

    for key, value in db.data.items():
        if key.startswith("user_") and isinstance(value, dict):
            user_id = int(key.replace("user_", ""))
            total_cards = sum(value.values())

            display_name = await get_user_display_name(context, update.effective_chat.id, user_id)
            users_stats.append((display_name, total_cards, user_id))

    if not users_stats:
        await update.message.reply_text("📊 Пока никто не собирал карточки!")
        return

    # Сортируем по количеству карточек (по убыванию)
    users_stats.sort(key=lambda x: x[1], reverse=True)

    # Берем топ-10
    top_users = users_stats[:10]

    top_text = "🏆 ТОП-10 КОЛЛЕКЦИОНЕРОВ КАРТОЧЕК 🏆\n\n"

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for i, (display_name, total_cards, user_id) in enumerate(top_users):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        top_text += f"{medal} {display_name} — {total_cards} карт\n"

    await update.message.reply_text(top_text, parse_mode='Markdown')

async def poker_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    challenger_id = update.effective_user.id
    current_time = time.time()
    last_poker_time = get_last_poker_time(challenger_id)

    # Проверяем кулдаун 15 минут (900 секунд)
    cooldown_time = 15 * 60  # 15 минут в секундах
    time_passed = current_time - last_poker_time

    if time_passed < cooldown_time:
        time_remaining = cooldown_time - time_passed
        formatted_time = format_time_remaining(time_remaining)
        await update.message.reply_text(
            f"⏰ Покер можно использовать снова через: {formatted_time}"
        )
        return

    challenger_name = await get_user_display_name(context, update.effective_chat.id, challenger_id)

    # Определяем оппонента
    opponent_id = None
    opponent_name = None

    if update.message.reply_to_message:
        # Если это ответ на сообщение
        opponent_id = update.message.reply_to_message.from_user.id
        opponent_name = await get_user_display_name(context, update.effective_chat.id, opponent_id)
        print(f"DEBUG: Reply to message - opponent_id: {opponent_id}, opponent_name: {opponent_name}")
    elif context.args:
        # Если указан username в аргументах
        target_username = context.args[0].replace('@', '')
        await update.message.reply_text(
            f"⚠ Не удалось найти пользователя {target_username}.\n"
            f"Попробуйте ответить на сообщение пользователя командой /poker"
        )
        return
    else:
        # Если нет ни ответа на сообщение, ни аргументов
        await update.message.reply_text(
            "🃏 Mustard Poker\n\n"
            "Использование: /poker @username\n"
            "Или ответьте на сообщение пользователя командой /poker",
            parse_mode='Markdown'
        )
        return

    if opponent_id == challenger_id:
        await update.message.reply_text("❌ Нельзя вызвать самого себя на дуэль!")
        return

    # Проверяем, есть ли у игроков карты
    challenger_inventory = get_user_inventory(challenger_id)
    opponent_inventory = get_user_inventory(opponent_id)

    if not challenger_inventory:
        await update.message.reply_text("❌ У вас нет карт для игры! Используйте /card")
        return

    if not opponent_inventory:
        await update.message.reply_text(f"❌ У {opponent_name} нет карт для игры!")
        return

    # Обновляем время последнего использования покера
    set_last_poker_time(challenger_id, current_time)

    # Создаем вызов
    challenge_id = f"{challenger_id}{opponent_id}{int(time.time())}"
    print(f"DEBUG: Creating challenge {challenge_id}")

    pending_challenges[challenge_id] = {
        'challenger_id': challenger_id,
        'opponent_id': opponent_id,
        'challenger_name': challenger_name,
        'opponent_name': opponent_name,
        'chat_id': update.effective_chat.id,
        'timestamp': time.time()
    }

    print(f"DEBUG: Stored challenge: {pending_challenges[challenge_id]}")

    await update.message.reply_text(
        f"🃏 Mustard Poker Challenge!\n\n"
        f"{challenger_name} вызывает {opponent_name} на дуэль!\n\n"
        f"💡 {opponent_name}, используйте команду /accept чтобы принять вызов\n"
        f"💡 Или команду /decline чтобы отклонить",
        parse_mode='Markdown'
    )

async def accept_poker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ищем активный вызов для этого пользователя
    challenge = None
    challenge_id = None

    for cid, c in pending_challenges.items():
        if c['opponent_id'] == user_id:
            challenge = c
            challenge_id = cid
            break

    if not challenge:
        await update.message.reply_text("❌ У вас нет активных вызовов на покер!")
        return

    print(f"DEBUG: Accepting challenge {challenge_id}")

    # Удаляем вызов из pending
    del pending_challenges[challenge_id]

    # Запускаем игру
    await start_poker_game_from_command(update, context, challenge)

async def decline_poker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ищем активный вызов для этого пользователя
    challenge = None
    challenge_id = None

    for cid, c in pending_challenges.items():
        if c['opponent_id'] == user_id:
            challenge = c
            challenge_id = cid
            break

    if not challenge:
        await update.message.reply_text("❌ У вас нет активных вызовов на покер!")
        return

    print(f"DEBUG: Declining challenge {challenge_id}")

    # Удаляем вызов из pending
    del pending_challenges[challenge_id]

    await update.message.reply_text(
        f"❌ {challenge['opponent_name']} отклонил вызов от {challenge['challenger_name']}"
    )

async def start_poker_game_from_command(update, context, game_data):
    print(f"DEBUG: Starting poker game from command")
    print(f"DEBUG: Game data: {game_data}")

    try:
        game = game_data

        # Получаем инвентари игроков
        challenger_inventory = get_user_inventory(game['challenger_id'])
        opponent_inventory = get_user_inventory(game['opponent_id'])

        # Формируем руки из инвентаря (все карты игрока)
        challenger_hand = []
        for card, count in challenger_inventory.items():
            challenger_hand.extend([card] * count)

        opponent_hand = []
        for card, count in opponent_inventory.items():
            opponent_hand.extend([card] * count)

        # Если у игрока больше 10 карт, берем случайные 10
        if len(challenger_hand) > 10:
            challenger_hand = random.sample(challenger_hand, 10)

        if len(opponent_hand) > 10:
            opponent_hand = random.sample(opponent_hand, 10)

        # Подсчитываем очки
        challenger_score, challenger_rarities = calculate_poker_score(challenger_hand)
        opponent_score, opponent_rarities = calculate_poker_score(opponent_hand)

        # Определяем победителя
        if challenger_score > opponent_score:
            winner_id = game['challenger_id']
            winner_name = game['challenger_name']
            loser_id = game['opponent_id']
            loser_name = game['opponent_name']
            winner_hand = challenger_hand
            winner_score = challenger_score
            loser_hand = opponent_hand
            loser_score = opponent_score
        elif opponent_score > challenger_score:
            winner_id = game['opponent_id']
            winner_name = game['opponent_name']
            loser_id = game['challenger_id']
            loser_name = game['challenger_name']
            winner_hand = opponent_hand
            winner_score = opponent_score
            loser_hand = challenger_hand
            loser_score = opponent_score
        else:
            # Ничья
            result_text = f"🤝 НИЧЬЯ!\n\n"
            result_text += f"🎲 {game['challenger_name']}: {challenger_score} очков\n"
            result_text += f"🎲 {game['opponent_name']}: {opponent_score} очков\n\n"
            result_text += "Никто не получает награду!"

            await update.message.reply_text(result_text)
            return

        # Награда победителю - случайная уникальная покерная карта или секретная карта
        unique_rewards = [POKER_CARD, POKER_67_CARD]

        # 5% шанс получить секретную карту Kendrick Lamar
        if random.random() < 0.05:
            reward_card = "⚫ Секретная: Kendrick Lamar"
        else:
            reward_card = random.choice(unique_rewards)

        add_card_to_inventory(winner_id, reward_card)

        # Добавляем победу в статистику
        add_poker_win(winner_id)

        # Отнимаем лучшую карту у проигравшего (кроме уникальных)
        lost_card = get_best_non_unique_card(loser_id)
        lost_card_text = ""
        if lost_card:
            if remove_card_from_inventory(loser_id, lost_card, 1):
                lost_card_text = f"\n💔 {loser_name} теряет: {lost_card}"

# Формируем результат
        result_text = f"🃏 РЕЗУЛЬТАТЫ MUSTARD POKER\n\n"
        result_text += f"🏆 Победитель: {winner_name}\n"
        result_text += f"💔 Проигравший: {loser_name}\n\n"
        result_text += f"🎲 Очки:\n"
        result_text += f"• {winner_name}: {winner_score}\n"
        result_text += f"• {loser_name}: {loser_score}\n\n"
        result_text += f"🎁 Награда: {reward_card}{lost_card_text}\n\n"

        result_text += f"🃏 Рука победителя ({winner_name}):\n"
        for card in winner_hand:
            result_text += f"• {card}\n"

        await update.message.reply_text(result_text)
        print(f"DEBUG: Game completed successfully")

    except Exception as e:
        print(f"ERROR in start_poker_game_from_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске игры.")

async def poker_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Собираем всех игроков с победами в покере
    poker_stats = []

    for key, value in db.data.items():
        if key.startswith("poker_wins_") and isinstance(value, int) and value > 0:
            user_id = int(key.replace("poker_wins_", ""))
            wins = value

            display_name = await get_user_display_name(context, update.effective_chat.id, user_id)
            poker_stats.append((display_name, wins, user_id))

    if not poker_stats:
        await update.message.reply_text("🃏 Пока никто не играл в Mustard Poker!")
        return

    # Сортируем по количеству побед (по убыванию)
    poker_stats.sort(key=lambda x: x[1], reverse=True)

    # Берем топ-10
    top_players = poker_stats[:10]

    leaderboard_text = "🃏 РЕЙТИНГ MUSTARD POKER 🃏\n\n"

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    for i, (display_name, wins, user_id) in enumerate(top_players):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        leaderboard_text += f"{medal} {display_name} - {wins} побед\n"

    await update.message.reply_text(leaderboard_text)

async def show_cardlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cardlist_text = "🃏 СПИСОК ВСЕХ КАРТ В ИГРЕ 🃏\n\n"

    cardlist_text += "🟢 ОБЫЧНЫЕ КАРТЫ (12% каждая):\n"
    cardlist_text += "• Простой Манго\n"
    cardlist_text += "• Денчик\n"
    cardlist_text += "• Просроченная Горчица\n"
    cardlist_text += "• Kanye West\n\n"

    cardlist_text += "🔵 НЕОБЫЧНЫЕ КАРТЫ (6% каждая):\n"
    cardlist_text += "• Горчица\n"
    cardlist_text += "• Троллфейс\n"
    cardlist_text += "• Тантум Верде\n"
    cardlist_text += "• Sigeon Pex\n\n"

    cardlist_text += "🟣 ЭПИЧЕСКИЕ КАРТЫ (3\\.5% каждая):\n"
    cardlist_text += "• Американский Психопат\n"
    cardlist_text += "• Мистер Гун\n"
    cardlist_text += "• Доктор Гун\n"
    cardlist_text += "• Открой Базу и Верни Мне БР БР Патапима\n\n"

    cardlist_text += "🟠 ЛЕГЕНДАРНЫЕ КАРТЫ (2% каждая):\n"
    cardlist_text += "• Манго Марк\n"
    cardlist_text += "• Король Горчицы\n"
    cardlist_text += "• Китайский Вождь\n"
    cardlist_text += "• J\\_Манго\n\n"

    cardlist_text += "🔴 МИФИЧЕСКИЕ КАРТЫ (0\\.25% каждая):\n"
    cardlist_text += "• Манго Спонсор\n"
    cardlist_text += "• Омни-Манго\n"
    cardlist_text += "• Манго Троллфейс\n"
    cardlist_text += "• Горчица Матвея\n\n"

    cardlist_text += "⚫ СЕКРЕТНАЯ КАРТА:\n"
    cardlist_text += "• Kendrick Lamar\n\n"

    cardlist_text += "⭐ УНИКАЛЬНЫЕ КАРТЫ:\n"
    cardlist_text += "• Мастер Покера\n"
    cardlist_text += "• 67\n\n"

    cardlist_text += "💡 Всего карт: 21 обычная \\+ 2 уникальных \\+ 1 секретная"

    await update.message.reply_text(cardlist_text, parse_mode='Markdown')

async def give_sponsor_mango(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    # Определяем получателя карты
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        target_user_id = user.id
        target_name = f"@{user.username}"

    card = "🔴 Мифическая: Манго Спонсор"
    add_card_to_inventory(target_user_id, card)
    await update.message.reply_text(f"✅ Выдана карта {card} пользователю {target_name}")

async def give_omni_mango(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    # Определяем получателя карты
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        target_user_id = user.id
        target_name = f"@{user.username}"

    card = "🔴 Мифическая: Омни-Манго"
    add_card_to_inventory(target_user_id, card)
    await update.message.reply_text(f"✅ Выдана карта {card} пользователю {target_name}")

async def give_troll_mango(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    # Определяем получателя карты
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        target_user_id = user.id
        target_name = f"@{user.username}"

    card = "🔴 Мифическая: Манго Троллфейс"
    add_card_to_inventory(target_user_id, card)
    await update.message.reply_text(f"✅ Выдана карта {card} пользователю {target_name}")

async def give_matvey_mustard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    # Определяем получателя карты
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        target_user_id = user.id
        target_name = f"@{user.username}"

    card = "🔴 Мифическая: Горчица Матвея"
    add_card_to_inventory(target_user_id, card)
    await update.message.reply_text(f"✅ Выдана карта {card} пользователю {target_name}")

async def give_kendrick_lamar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    # Определяем получателя карты
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        target_user_id = user.id
        target_name = f"@{user.username}"

    card = "⚫ Секретная: Kendrick Lamar"
    add_card_to_inventory(target_user_id, card)
    await update.message.reply_text(f"✅ Выдана карта {card} пользователю {target_name}")

async def give_any_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    if not context.args:
        all_cards_list = "\n".join([f"• {card[0]}" for card in cards])
        await update.message.reply_text(
            "🎁 Выдача любой карты\n\n"
            "📋 Использование:\n"
            "/giveanycard [количество] [название карты]\n\n"
            "📝 Примеры:\n"
            "/giveanycard 5 Простой Манго\n"
            "/giveanycard 1 Американский\n"
            "/giveanycard Троллфейс (количество по умолчанию = 1)\n\n"
            "💡 Ответьте на сообщение пользователя для выдачи карты ему\n\n"
            f"🃏 Доступные карты:\n{all_cards_list}\n• {POKER_CARD}\n• {POKER_67_CARD}"
        )
        return

    # Парсим аргументы
    args = context.args
    quantity = 1
    card_search_parts = args

    # Если первый аргумент - число, это количество
    if args[0].isdigit():
        quantity = int(args[0])
        if quantity <= 0:
            await update.message.reply_text("❌ Количество должно быть больше 0!")
            return
        if quantity > 100:
            await update.message.reply_text("❌ Максимальное количество: 100!")
            return
        card_search_parts = args[1:]

    if not card_search_parts:
        await update.message.reply_text("❌ Укажите название карты!")
        return

    card_search = " ".join(card_search_parts)
    
    # Ищем карту в списке всех карт
    found_card = None
    all_cards = [card[0] for card in cards] + [POKER_CARD, POKER_67_CARD]
    
    for card in all_cards:
        if card_search.lower() in card.lower():
            found_card = card
            break
    
    if not found_card:
        await update.message.reply_text(f"❌ Карта содержащая '{card_search}' не найдена!")
        return

    # Определяем получателя карты
    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        target_user_id = user.id
        target_name = f"@{user.username}"

    # Выдаем карты
    for _ in range(quantity):
        add_card_to_inventory(target_user_id, found_card)

    quantity_text = f" × {quantity}" if quantity > 1 else ""
    await update.message.reply_text(f"✅ Выдана карта {found_card}{quantity_text} пользователю {target_name}")

async def give_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что команду использует именно @PigeonGoonMaster
    user = update.effective_user
    if not user.username or user.username.lower() != "pigeongoonmaster":
        await update.message.reply_text("❌ Эта команда доступна только пользователю @PigeonGoonMaster!")
        return

    # Проверяем аргументы
    if len(context.args) < 1:
        await update.message.reply_text("❌ Укажите количество монет! Например: /givemoney 1000")
        return

    if not context.args[0].isdigit():
        await update.message.reply_text("❌ Количество монет должно быть числом!")
        return

    amount = int(context.args[0])
    if amount <= 0:
        await update.message.reply_text("❌ Количество монет должно быть больше 0!")
        return

    # Определяем получателя
    target_user_id = None
    target_name = None

    if update.message.reply_to_message:
        target_user_id = update.message.reply_to_message.from_user.id
        target_name = await get_user_display_name(context, update.effective_chat.id, target_user_id)
    else:
        # Выдаем себе
        target_user_id = user.id
        target_name = f"@{user.username}"

    # Добавляем монеты
    add_coins(target_user_id, amount)

    await update.message.reply_text(
        f"✅ Выдано {amount} монет пользователю {target_name}\n"
        f"🪙 Теперь у него {get_user_coins(target_user_id)} монет"
    )

async def trade_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    trader_id = update.effective_user.id
    trader_name = await get_user_display_name(context, update.effective_chat.id, trader_id)

    # Проверяем аргументы команды
    if len(context.args) < 2:
        await update.message.reply_text(
            "💰 Система трейдов карт\n\n"
            "📋 Использование:\n"
            "/trade [количество] [карта_для_обмена] [количество] [желаемая_карта]\n\n"
            "📝 Примеры:\n"
            "/trade 2 Простой Манго 1 Горчица\n"
            "/trade 1 Американский 1 Мистер\n\n"
            "💡 Если количество не указано, по умолчанию = 1\n"
            "💡 Ответьте на сообщение пользователя с этой командой"
        )
        return

    # Определяем оппонента
    opponent_id = None
    opponent_name = None

    if update.message.reply_to_message:
        opponent_id = update.message.reply_to_message.from_user.id
        opponent_name = await get_user_display_name(context, update.effective_chat.id, opponent_id)
    else:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя для отправки предложения трейда!")
        return

    if opponent_id == trader_id:
        await update.message.reply_text("❌ Нельзя торговать с самим собой!")
        return

    # Парсим аргументы для извлечения количества и названий карт
    args = context.args

    # Пытаемся найти числа в аргументах
    offer_quantity = 1
    want_quantity = 1
    offer_card_parts = []
    want_card_parts = []

    parsing_want_card = False

    i = 0
    while i < len(args):
        arg = args[i]

        # Проверяем, является ли аргумент числом
        if arg.isdigit():
            quantity = int(arg)
            if quantity <= 0:
                await update.message.reply_text("❌ Количество карт должно быть больше 0!")
                return

            if not parsing_want_card:
                offer_quantity = quantity
            else:
                want_quantity = quantity
        else:
            # Если мы встретили не число после числа, начинаем собирать название карты
            if not parsing_want_card:
                offer_card_parts.append(arg)
                # Проверяем, нет ли числа в следующих аргументах (для желаемой карты)
                for j in range(i + 1, len(args)):
                    if args[j].isdigit():
                        parsing_want_card = True
                        break
                    if j == len(args) - 1:  # Если это последний аргумент
                        parsing_want_card = True
                        want_card_parts.append(args[j])
                        i = j  # пропускаем обработку этого аргумента в основном цикле
            else:
                want_card_parts.append(arg)

        i += 1

    # Если не указали желаемую карту, берем последнюю часть как желаемую
    if not want_card_parts and offer_card_parts:
        want_card_parts = [offer_card_parts.pop()]

    if not offer_card_parts or not want_card_parts:
        await update.message.reply_text("❌ Укажите названия карт для обмена!")
        return

    offer_card_input = " ".join(offer_card_parts)
    want_card_input = " ".join(want_card_parts)

    # Находим полные названия карт
    trader_inventory = get_user_inventory(trader_id)
    opponent_inventory = get_user_inventory(opponent_id)

    offer_card = None
    want_card = None

    # Ищем карту для обмена у трейдера
    for card in trader_inventory:
        if trader_inventory[card] >= offer_quantity and offer_card_input.lower() in card.lower():
            offer_card = card
            break

    # Ищем желаемую карту у оппонента
    for card in opponent_inventory:
        if opponent_inventory[card] >= want_quantity and want_card_input.lower() in card.lower():
            want_card = card
            break

    if not offer_card:
        await update.message.reply_text(f"❌ У вас нет {offer_quantity} карт содержащих '{offer_card_input}'!")
        return

    if not want_card:
        await update.message.reply_text(f"❌ У {opponent_name} нет {want_quantity} карт содержащих '{want_card_input}'!")
        return

    # Создаем предложение трейда
    trade_id = f"{trader_id}{opponent_id}{int(time.time())}"
    pending_trades[trade_id] = {
        'trader_id': trader_id,
        'opponent_id': opponent_id,
        'trader_name': trader_name,
        'opponent_name': opponent_name,
        'offer_card': offer_card,
        'want_card': want_card,
        'offer_quantity': offer_quantity,
        'want_quantity': want_quantity,
        'chat_id': update.effective_chat.id,
        'timestamp': time.time()
    }

    # Экранируем специальные символы для Markdown
    escaped_offer_card = offer_card.replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
    escaped_want_card = want_card.replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
    escaped_trader_name = trader_name.replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
    escaped_opponent_name = opponent_name.replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')

    await update.message.reply_text(
        f"💰 ПРЕДЛОЖЕНИЕ ТРЕЙДА\n\n"
        f"👤 {escaped_trader_name} предлагает:\n"
        f"📤 Отдать: {escaped_offer_card} × {offer_quantity}\n"
        f"📥 Получить: {escaped_want_card} × {want_quantity}\n\n"
        f"💡 {escaped_opponent_name}, используйте /accepttrade чтобы принять\n"
        f"💡 Или /declinetrade чтобы отклонить",
        parse_mode='Markdown'
    )

async def accept_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ищем активное предложение трейда для этого пользователя
    trade = None
    trade_id = None

    for tid, t in pending_trades.items():
        if t['opponent_id'] == user_id:
            trade = t
            trade_id = tid
            break

    if not trade:
        await update.message.reply_text("❌ У вас нет активных предложений трейда!")
        return

    # Удаляем предложение из pending
    del pending_trades[trade_id]

    # Получаем количества (для совместимости со старыми трейдами)
    offer_quantity = trade.get('offer_quantity', 1)
    want_quantity = trade.get('want_quantity', 1)

    # Проверяем, что у обеих сторон еще есть нужные карты в достаточном количестве
    trader_inventory = get_user_inventory(trade['trader_id'])
    opponent_inventory = get_user_inventory(trade['opponent_id'])

    if trade['offer_card'] not in trader_inventory or trader_inventory[trade['offer_card']] < offer_quantity:
        await update.message.reply_text(f"❌ У {trade['trader_name']} нет {offer_quantity} карт {trade['offer_card']}!")
        return

    if trade['want_card'] not in opponent_inventory or opponent_inventory[trade['want_card']] < want_quantity:
        await update.message.reply_text(f"❌ У вас нет {want_quantity} карт {trade['want_card']}!")
        return

    # Выполняем обмен
    remove_card_from_inventory(trade['trader_id'], trade['offer_card'], offer_quantity)
    remove_card_from_inventory(trade['opponent_id'], trade['want_card'], want_quantity)

    # Добавляем карты
    for _ in range(want_quantity):
        add_card_to_inventory(trade['trader_id'], trade['want_card'])
    for _ in range(offer_quantity):
        add_card_to_inventory(trade['opponent_id'], trade['offer_card'])

    # Формируем текст результата
    offer_text = f"{trade['offer_card']}" + (f" × {offer_quantity}" if offer_quantity > 1 else "")
    want_text = f"{trade['want_card']}" + (f" × {want_quantity}" if want_quantity > 1 else "")

    # Экранируем специальные символы для Markdown
    escaped_trader_name = trade['trader_name'].replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
    escaped_opponent_name = trade['opponent_name'].replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
    escaped_want_text = want_text.replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')
    escaped_offer_text = offer_text.replace('_', '\\_').replace('-', '\\-').replace('(', '\\(').replace(')', '\\)')

    await update.message.reply_text(
        f"✅ ТРЕЙД ЗАВЕРШЕН!\n\n"
        f"🔄 {escaped_trader_name} получает: {escaped_want_text}\n"
        f"🔄 {escaped_opponent_name} получает: {escaped_offer_text}\n\n"
        f"🎉 Удачной игры!",
        parse_mode='Markdown'
    )

async def decline_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ищем активное предложение трейда для этого пользователя
    trade = None
    trade_id = None

    for tid, t in pending_trades.items():
        if t['opponent_id'] == user_id:
            trade = t
            trade_id = tid
            break

    if not trade:
        await update.message.reply_text("❌ У вас нет активных предложений трейда!")
        return

    # Удаляем предложение из pending
    del pending_trades[trade_id]

    await update.message.reply_text(
        f"❌ {trade['opponent_name']} отклонил предложение трейда от {trade['trader_name']}"
    )

async def cancel_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # Ищем активное предложение трейда от этого пользователя
    trade = None
    trade_id = None

    for tid, t in pending_trades.items():
        if t['trader_id'] == user_id:
            trade = t
            trade_id = tid
            break

    if not trade:
        await update.message.reply_text("❌ У вас нет активных предложений трейда!")
        return

    # Удаляем предложение из pending
    del pending_trades[trade_id]

    await update.message.reply_text(
        f"❌ {trade['trader_name']} отменил предложение трейда для {trade['opponent_name']}"
    )

async def mine_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    current_time = time.time()
    last_mine_time = get_last_mine_time(user_id)

    # Проверяем кулдаун 12 часов (43200 секунд)
    cooldown_time = 12 * 60 * 60  # 12 часов в секундах
    time_passed = current_time - last_mine_time

    if time_passed < cooldown_time:
        time_remaining = cooldown_time - time_passed
        formatted_time = format_time_remaining(time_remaining)
        await update.message.reply_text(
            f"⏰ Майнинг доступен снова через: {formatted_time}"
        )
        return

    # Подсчитываем количество карт для расчета дохода
    inventory = get_user_inventory(user_id)
    total_cards = sum(inventory.values()) if inventory else 0

    # Случайный доход от 50 до 150 монет
    income = random.randint(50, 150)

    # Добавляем монеты
    add_coins(user_id, income)

    # Обновляем время последнего майнинга
    set_last_mine_time(user_id, current_time)

    await update.message.reply_text(
        f"⛏ МАЙНИНГ ЗАВЕРШЕН! ⛏\n\n"
        f"💰 Получено: {income} монет\n"
        f"🪙 Всего монет: {get_user_coins(user_id)}\n\n"
        f"⏰ Следующий майнинг через 12 часов!",
        parse_mode='Markdown'
    )

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_coins = get_user_coins(user_id)
    purchases_today = get_user_purchases_today(user_id)
    shop_items = get_daily_shop()
    
    # Очищаем просроченные карты с рынка
    expired_count = cleanup_expired_market_cards()
    
    market_cards = get_market_cards()

    # Вычисляем время до обновления магазина
    now = datetime.now()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_until_update = tomorrow - now
    hours = int(time_until_update.total_seconds() // 3600)
    minutes = int((time_until_update.total_seconds() % 3600) // 60)

    shop_text = f"🛒 МАГАЗИН И РЫНОК ИГРОКОВ 🛒\n\n"
    shop_text += f"🪙 Ваши монеты: {user_coins}\n"
    shop_text += f"⏰ Обновление магазина через: {hours}ч {minutes}мин\n\n"

    # Показываем ежедневный магазин
    shop_text += f"📅 ЕЖЕДНЕВНЫЙ МАГАЗИН\n"
    shop_text += f"⚠ Каждую карту можно купить только 1 раз в день\n\n"

    for i, item in enumerate(shop_items, 1):
        if item.get("special") == "lucky":
            # Lucky Card
            if "lucky" in purchases_today:
                status = "❌ Куплено"
            else:
                status = f"💰 {item['price']} монет"
            shop_text += f"{i}. {item['card']} - {status}\n"
        else:
            # Обычная карта
            card_name = item['card'].split(': ', 1)[1] if ': ' in item['card'] else item['card']
            if card_name in purchases_today:
                status = "❌ Куплено"
            else:
                status = f"💰 {item['price']} монет"

            shop_text += f"{i}. {item['card']} - {status}\n"

    # Показываем рынок игроков
    if market_cards:
        shop_text += f"\n🏪 РЫНОК ИГРОКОВ\n"
        shop_text += f"💡 Карты от других игроков\n\n"

        for i, item in enumerate(market_cards, len(shop_items) + 1):
            seller_name = item['seller_name']
            shop_text += f"{i}. {item['card']} - 💰 {item['price']} монет (от {seller_name})\n"
    else:
        shop_text += f"\n🏪 РЫНОК ИГРОКОВ\n"
        shop_text += f"📭 Пока никто не продает карты\n"
        shop_text += f"💡 Используйте /sell [цена] [карта] чтобы продать свою карту\n"

    shop_text += f"\n💡 Используйте /buy [номер] для покупки"

    await update.message.reply_text(shop_text)

async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "💡 Использование: /buy [номер товара]\n"
            "Посмотрите магазин: /shop",
            parse_mode='Markdown'
        )
        return

    item_number = int(context.args[0])
    shop_items = get_daily_shop()
    
    # Очищаем просроченные карты с рынка
    cleanup_expired_market_cards()
    
    market_cards = get_market_cards()

    # Объединяем товары магазина и рынка
    all_items = shop_items + market_cards

    if item_number < 1 or item_number > len(all_items):
        await update.message.reply_text("❌ Неверный номер товара! Проверьте /shop")
        return

    item = all_items[item_number - 1]
    user_coins = get_user_coins(user_id)

    # Проверяем, это товар из магазина или с рынка
    if item_number <= len(shop_items):
        # Товар из ежедневного магазина
        purchases_today = get_user_purchases_today(user_id)

        # Проверяем, не купил ли уже сегодня
        if item.get("special") == "lucky":
            if "lucky" in purchases_today:
                await update.message.reply_text("❌ Вы уже купили Lucky Card сегодня!")
                return
        else:
            card_name = item['card'].split(': ', 1)[1] if ': ' in item['card'] else item['card']
            if card_name in purchases_today:
                await update.message.reply_text("❌ Вы уже купили эту карту сегодня!")
                return

        # Проверяем хватает ли денег
        if user_coins < item['price']:
            needed = item['price'] - user_coins
            await update.message.reply_text(f"❌ Недостаточно монет! Нужно еще: {needed}")
            return

        # Покупаем товар
        remove_coins(user_id, item['price'])

        if item.get("special") == "lucky":
            # Покупка Lucky Card
            current_uses = get_lucky_uses(user_id)
            set_lucky_uses(user_id, current_uses + item['count'])
            add_user_purchase_today(user_id, "lucky")

            await update.message.reply_text(
                f"✅ Покупка успешна!\n\n"
                f"🍀 Вы купили: {item['card']}\n"
                f"💰 Потрачено: {item['price']} монет\n"
                f"🪙 Осталось: {get_user_coins(user_id)} монет\n\n"
                f"🎫 Теперь у вас {get_lucky_uses(user_id)} использований Lucky Card!",
                parse_mode='Markdown'
            )
        else:
            # Покупка обычной карты
            add_card_to_inventory(user_id, item['card'])
            card_name = item['card'].split(': ', 1)[1] if ': ' in item['card'] else item['card']
            add_user_purchase_today(user_id, card_name)

            await update.message.reply_text(
                f"✅ Покупка успешна!\n\n"
                f"🃏 Вы купили: {item['card']}\n"
                f"💰 Потрачено: {item['price']} монет\n"
                f"🪙 Осталось: {get_user_coins(user_id)} монет",
                parse_mode='Markdown'
            )
    else:
        # Покупка с рынка игроков
        market_index = item_number - len(shop_items) - 1
        seller_id = item['seller_id']

        # Проверяем, не покупает ли свою же карту
        if seller_id == user_id:
            await update.message.reply_text("❌ Нельзя покупать свои собственные карты!")
            return

        # Проверяем хватает ли денег
        if user_coins < item['price']:
            needed = item['price'] - user_coins
            await update.message.reply_text(f"❌ Недостаточно монет! Нужно еще: {needed}")
            return

        # Проверяем, что карта еще на рынке
        current_market = get_market_cards()
        if market_index >= len(current_market) or current_market[market_index]['timestamp'] != item['timestamp']:
            await update.message.reply_text("❌ Эта карта уже была продана!")
            return

        # Покупаем карту с рынка
        remove_coins(user_id, item['price'])
        add_coins(seller_id, item['price'])
        add_card_to_inventory(user_id, item['card'])
        remove_card_from_market(market_index)

        await update.message.reply_text(
            f"✅ Покупка с рынка успешна!\n\n"
            f"🃏 Вы купили: {item['card']}\n"
            f"💰 Потрачено: {item['price']} монет\n"
            f"🪙 Осталось: {get_user_coins(user_id)} монет\n"
            f"👤 Продавец: {item['seller_name']}",
            parse_mode='Markdown'
        )

async def sell_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = await get_user_display_name(context, update.effective_chat.id, user_id)

    if len(context.args) < 2:
        await update.message.reply_text(
            "💰 Продажа карт на рынке\n\n"
            "📋 Использование:\n"
            "/sell [цена] [название карты]\n\n"
            "📝 Примеры:\n"
            "/sell 100 Простой Манго\n"
            "/sell 500 Американский\n\n"
            "💡 Укажите цену в монетах и часть названия карты\n"
            "⚠ Лимит: 2 слота по умолчанию, больше можно купить за ⭐ Stars",
            parse_mode='Markdown'
        )
        return

    # Проверяем лимит на продажу
    user_slots = get_user_slots(user_id)
    market_cards = get_market_cards()
    user_cards_on_sale = [card for card in market_cards if card['seller_id'] == user_id]
    
    if len(user_cards_on_sale) >= user_slots:
        await update.message.reply_text(
            f"❌ Вы уже продаете максимальное количество карт ({user_slots})!\n"
            "💡 Используйте /mysales чтобы посмотреть свои карты на продаже\n"
            "💡 Используйте /unsell [номер] чтобы снять карту с продажи\n"
            "⭐ Используйте /buyslot чтобы купить дополнительный слот за 10 Telegram Stars"
        )
        return

    if not context.args[0].isdigit():
        await update.message.reply_text("❌ Цена должна быть числом!")
        return

    price = int(context.args[0])
    if price <= 0:
        await update.message.reply_text("❌ Цена должна быть больше 0!")
        return

    card_search = " ".join(context.args[1:])
    user_inventory = get_user_inventory(user_id)

    if not user_inventory:
        await update.message.reply_text("❌ У вас нет карт для продажи!")
        return

    # Ищем карту в инвентаре
    found_card = None
    for card in user_inventory:
        if card_search.lower() in card.lower() and user_inventory[card] > 0:
            found_card = card
            break

    if not found_card:
        await update.message.reply_text(f"❌ У вас нет карты содержащей '{card_search}'!")
        return

    # Проверяем, не пытается ли продать уникальную карту
    if found_card.startswith("⭐"):
        await update.message.reply_text("❌ Нельзя продавать уникальные карты!")
        return

    # Удаляем карту из инвентаря
    if not remove_card_from_inventory(user_id, found_card, 1):
        await update.message.reply_text("❌ Ошибка при удалении карты из инвентаря!")
        return

    # Добавляем карту на рынок
    add_card_to_market(found_card, price, user_id, user_name)

    user_slots = get_user_slots(user_id)
    remaining_slots = user_slots - len(user_cards_on_sale) - 1  # -1 потому что только что добавили карту

    await update.message.reply_text(
        f"✅ Карта выставлена на продажу!\n\n"
        f"🃏 Карта: {found_card}\n"
        f"💰 Цена: {price} монет\n"
        f"🛒 Другие игроки могут купить её в магазине (/shop)\n\n"
        f"💡 Когда карту купят, вы получите монеты\n"
        f"⏰ Если карту не купят в течение 24 часов, она вернется к вам\n"
        f"📊 Свободных слотов для продажи: {remaining_slots}/{user_slots}",
        parse_mode='Markdown'
    )

async def show_my_sales(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Очищаем просроченные карты с рынка
    cleanup_expired_market_cards()
    
    market_cards = get_market_cards()
    user_cards_on_sale = [card for card in market_cards if card['seller_id'] == user_id]

    user_slots = get_user_slots(user_id)
    
    if not user_cards_on_sale:
        await update.message.reply_text(
            f"📦 Ваши продажи\n\n"
            f"🛒 У вас нет карт на продаже\n\n"
            f"💡 Используйте /sell [цена] [карта] чтобы выставить карту на продажу\n"
            f"📊 Доступно слотов: {user_slots}\n"
            f"⭐ Используйте /buyslot чтобы купить дополнительный слот за 10 Telegram Stars"
        )
        return

    sales_text = f"📦 ВАШИ ПРОДАЖИ ({len(user_cards_on_sale)}/{user_slots})\n\n"

    for i, card_data in enumerate(user_cards_on_sale, 1):
        # Вычисляем время на рынке
        time_on_market = time.time() - card_data['timestamp']
        hours_left = max(0, 24 - (time_on_market / 3600))
        
        if hours_left > 1:
            time_left_text = f"{int(hours_left)}ч {int((hours_left % 1) * 60)}мин"
        elif hours_left > 0:
            time_left_text = f"{int(hours_left * 60)}мин"
        else:
            time_left_text = "скоро истекает"

        sales_text += f"{i}. {card_data['card']}\n"
        sales_text += f"   💰 Цена: {card_data['price']} монет\n"
        sales_text += f"   ⏰ Осталось: {time_left_text}\n\n"

    user_slots = get_user_slots(user_id)
    free_slots = user_slots - len(user_cards_on_sale)
    sales_text += f"📊 Свободных слотов: {free_slots}/{user_slots}\n\n"
    sales_text += "💡 Используйте /unsell [номер] чтобы снять карту с продажи\n"
    sales_text += "⭐ Используйте /buyslot чтобы купить дополнительный слот за 10 Telegram Stars"

    await update.message.reply_text(sales_text)

async def buy_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Покупка дополнительного слота для продажи карт за Telegram Stars"""
    user_id = update.effective_user.id
    current_slots = get_user_slots(user_id)
    
    # Ограничиваем максимальное количество слотов
    if current_slots >= 4:
        await update.message.reply_text(
            "❌ Достигнуто максимальное количество слотов (4)!\n"
            f"📊 У вас уже {current_slots} слотов для продажи карт."
        )
        return

    # Создаем инвойс для оплаты
    title = "Дополнительный слот для продажи"
    description = "Покупка дополнительного слота для продажи карт на рынке"
    payload = f"slot_{user_id}_{int(time.time())}"
    currency = "XTR"  # Telegram Stars
    price = 10  # 10 звезд
    
    prices = [LabeledPrice(label="Дополнительный слот", amount=price)]
    
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Пустой для Telegram Stars
        currency=currency,
        prices=prices,
        start_parameter="slot_purchase"
    )

async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка перед оплатой"""
    query = update.pre_checkout_query
    
    # Проверяем payload
    if query.invoice_payload.startswith("slot_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный товар!")

async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешной оплаты"""
    payment = update.message.successful_payment
    
    if payment.invoice_payload.startswith("slot_"):
        user_id = update.effective_user.id
        
        # Добавляем слот пользователю
        add_user_slot(user_id)
        new_slots = get_user_slots(user_id)
        
        await update.message.reply_text(
            f"✅ Спасибо за покупку!\n\n"
            f"🎉 Вам добавлен дополнительный слот для продажи карт!\n"
            f"📊 Теперь у вас {new_slots} слотов для продажи\n\n"
            f"💡 Используйте /sell чтобы выставить карты на продажу"
        )

async def unsell_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "🔄 Снятие карты с продажи\n\n"
            "📋 Использование:\n"
            "/unsell [номер]\n\n"
            "💡 Посмотрите номера своих карт: /mysales"
        )
        return

    card_number = int(context.args[0])
    
    # Очищаем просроченные карты с рынка
    cleanup_expired_market_cards()
    
    market_cards = get_market_cards()
    user_cards_on_sale = [(i, card) for i, card in enumerate(market_cards) if card['seller_id'] == user_id]

    if not user_cards_on_sale:
        await update.message.reply_text("❌ У вас нет карт на продаже!")
        return

    if card_number < 1 or card_number > len(user_cards_on_sale):
        await update.message.reply_text(f"❌ Неверный номер! Доступные номера: 1-{len(user_cards_on_sale)}")
        return

    # Получаем индекс карты в общем списке рынка и саму карту
    market_index, card_data = user_cards_on_sale[card_number - 1]

    # Снимаем карту с рынка и возвращаем в инвентарь
    removed_card = remove_card_from_market(market_index)
    if removed_card:
        add_card_to_inventory(user_id, removed_card['card'])
        
        user_slots = get_user_slots(user_id)
        await update.message.reply_text(
            f"✅ Карта снята с продажи!\n\n"
            f"🃏 {removed_card['card']} возвращена в ваш инвентарь\n"
            f"📊 Теперь у вас {user_slots - len(user_cards_on_sale) + 1}/{user_slots} свободных слотов для продажи"
        )
    else:
        await update.message.reply_text("❌ Ошибка при снятии карты с продажи!")

keep_alive()

# Используем переменную окружения или токен по умолчанию
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8216384677:AAHXkJVK0IH5P9xMuiptFTRBgZTGPOYAKMc")

application = ApplicationBuilder().token(TOKEN).build()

# Обычные команды
application.add_handler(CommandHandler("card", get_card))
application.add_handler(CommandHandler("profile", show_profile))
application.add_handler(CommandHandler("luckycard", lucky_card))
application.add_handler(CommandHandler("top", show_top))
application.add_handler(CommandHandler("cardlist", show_cardlist))

# Покерные команды
application.add_handler(CommandHandler("poker", poker_challenge))
application.add_handler(CommandHandler("accept", accept_poker))
application.add_handler(CommandHandler("decline", decline_poker))
application.add_handler(CommandHandler("pokertop", poker_leaderboard))

# Админские команды для выдачи мифических карт @PigeonGoonMaster
application.add_handler(CommandHandler("givesponsor", give_sponsor_mango))
application.add_handler(CommandHandler("giveomni", give_omni_mango))
application.add_handler(CommandHandler("givetroll", give_troll_mango))
application.add_handler(CommandHandler("givematvey", give_matvey_mustard))
application.add_handler(CommandHandler("givekendrick", give_kendrick_lamar))
application.add_handler(CommandHandler("giveanycard", give_any_card))
application.add_handler(CommandHandler("givemoney", give_money))

# Команды трейдов
application.add_handler(CommandHandler("trade", trade_offer))
application.add_handler(CommandHandler("accepttrade", accept_trade))
application.add_handler(CommandHandler("declinetrade", decline_trade))
application.add_handler(CommandHandler("canceltrade", cancel_trade))

# Команды валютной системы
application.add_handler(CommandHandler("mine", mine_coins))
application.add_handler(CommandHandler("shop", show_shop))
application.add_handler(CommandHandler("buy", buy_item))
application.add_handler(CommandHandler("sell", sell_card))
application.add_handler(CommandHandler("mysales", show_my_sales))
application.add_handler(CommandHandler("unsell", unsell_card))
application.add_handler(CommandHandler("buyslot", buy_slot))

# Обработчики платежей
application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

print("🤖 Бот запущен и готов к работе!")
application.run_polling()
