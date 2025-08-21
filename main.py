import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict, deque

from telegram import Update, ChatMember, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ChatMemberHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes
)
from telegram.constants import ChatMemberStatus

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Простая файловая база данных
class SimpleDB:
    def __init__(self, filename='chat_manager_data.json'):
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

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self._save_data()

    def __contains__(self, key):
        return key in self.data

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self._save_data()

db = SimpleDB()

# Глобальные переменные для антиспам системы
user_message_history = defaultdict(lambda: deque(maxlen=10))
user_warnings = defaultdict(int)

# Настройки антиспама
SPAM_SETTINGS = {
    'max_messages_per_minute': 5,
    'rapid_messages_count': 5,
    'rapid_messages_time': 10,
    'max_identical_messages': 3,
    'max_warnings': 3,
    'auto_mute_duration': 300,
    'warning_reset_time': 3600,
    'media_flood_protection': True,
}

# Настройки наказаний по умолчанию
DEFAULT_PUNISHMENT_SETTINGS = {
    'punishment_type': 'mute',
    'mute_duration': 300,
    'ban_duration': 3600,
    'warnings_before_punishment': 3,
}

def is_admin(user_id: int, chat_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    admins = db.get(f"admins_{chat_id}", [])
    return user_id in admins

def get_chat_settings(chat_id: int) -> dict:
    """Получает настройки чата"""
    default_settings = {
        'antispam_enabled': True,
        'auto_moderation': True,
        'welcome_message': True,
        'delete_service_messages': True,
        'punishment_type': 'mute',
        'mute_duration': 300,
        'ban_duration': 3600,
        'warnings_before_punishment': 3,
        'ai_enabled': True,
        'ai_response_chance': 25,
        'rapid_messages_count': 5,
    }
    settings = db.get(f"settings_{chat_id}", default_settings)
    for key, value in default_settings.items():
        if key not in settings:
            settings[key] = value
    if 'rapid_messages_count' in SPAM_SETTINGS and SPAM_SETTINGS['rapid_messages_count'] != settings.get('rapid_messages_count'):
        settings['rapid_messages_count'] = SPAM_SETTINGS['rapid_messages_count']

    return settings

def save_chat_settings(chat_id: int, settings: dict):
    """Сохраняет настройки чата"""
    db.set(f"settings_{chat_id}", settings)

async def check_spam(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Проверяет сообщение на спам"""
    if not update.message or not update.message.from_user:
        return False

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    message_text = update.message.text or ""
    current_time = time.time()

    settings = get_chat_settings(chat_id)
    if not settings.get('antispam_enabled', True):
        return False

    user_history = user_message_history[user_id]
    user_history.append(current_time)

    recent_messages = [t for t in user_history if current_time - t < SPAM_SETTINGS['rapid_messages_time']]

    rapid_count_setting = settings.get('rapid_messages_count', SPAM_SETTINGS['rapid_messages_count'])
    if len(recent_messages) > rapid_count_setting:
        await warn_user(update, context, "слишком частые сообщения")
        return True

    if message_text:
        recent_texts = db.get(f"recent_texts_{user_id}", [])
        recent_texts.append(message_text)
        recent_texts = recent_texts[-10:]
        db.set(f"recent_texts_{user_id}", recent_texts)

        identical_count = recent_texts.count(message_text)
        if identical_count >= SPAM_SETTINGS['max_identical_messages']:
            await warn_user(update, context, "повторяющиеся сообщения")
            return True

    media_type = None
    media_id = None

    if update.message.photo:
        media_type = "photo"
        media_id = update.message.photo[-1].file_id
    elif update.message.sticker:
        media_type = "sticker"
        media_id = update.message.sticker.file_id
    elif update.message.animation:
        media_type = "gif"
        media_id = update.message.animation.file_id
        logger.info(f"Обнаружена GIF от пользователя {user_id}: {media_id}")
    elif update.message.video:
        media_type = "video"
        media_id = update.message.video.file_id
    elif update.message.document:
        media_type = "document"
        media_id = update.message.document.file_id
    elif update.message.voice:
        media_type = "voice"
        media_id = update.message.voice.file_id
    elif update.message.video_note:
        media_type = "video_note"
        media_id = update.message.video_note.file_id
    elif update.message.audio:
        media_type = "audio"
        media_id = update.message.audio.file_id

    if media_type and media_id:
        recent_media = db.get(f"recent_media_{user_id}", [])
        recent_media.append({"type": media_type, "id": media_id, "time": current_time})

        recent_media = [
            item for item in recent_media[-20:]
            if current_time - item.get("time", 0) < 3600
        ]
        db.set(f"recent_media_{user_id}", recent_media)

        identical_media = [
            item for item in recent_media
            if item.get("id") == media_id and item.get("type") == media_type
        ]

        if len(identical_media) >= SPAM_SETTINGS['max_identical_messages']:
            await warn_user(update, context, f"повторяющиеся {media_type}")
            return True

        recent_media_minute = [
            item for item in recent_media
            if current_time - item.get("time", 0) < SPAM_SETTINGS['rapid_messages_time']]

        if len(recent_media_minute) > rapid_count_setting:
            await warn_user(update, context, f"флуд медиафайлами ({media_type})")
            return True

    return False

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE, reason: str):
    """Выдает предупреждение пользователю"""
    if not update.message or not update.message.from_user:
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    username = update.message.from_user.username or update.message.from_user.first_name

    settings = get_chat_settings(chat_id)
    punishment_type = settings.get('punishment_type', 'mute')
    warnings_limit = settings.get('warnings_before_punishment', 3)

    user_warnings[user_id] += 1
    warnings_count = user_warnings[user_id]

    if warnings_count >= warnings_limit:
        user_warnings[user_id] = 0

        if punishment_type == 'mute':
            duration = settings.get('mute_duration', 300)
            await mute_user(update, context, duration, f"превышение лимита предупреждений ({reason})")
        elif punishment_type == 'ban':
            duration = settings.get('ban_duration', 3600)
            await ban_user_spam(update, context, duration, f"превышение лимита предупреждений ({reason})")
        elif punishment_type == 'warn':
            warning_text = (
                f"⚠️ **ФИНАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ** для @{username}\n"
                f"Причина: {reason}\n"
                f"Следующее нарушение приведет к дополнительным мерам."
            )

            try:
                await update.message.delete()
                warning_msg = await context.bot.send_message(chat_id, warning_text, parse_mode='Markdown')
                context.job_queue.run_once(
                    lambda context: context.bot.delete_message(chat_id, warning_msg.message_id),
                    60
                )
            except Exception as e:
                logger.error(f"Ошибка при выдаче финального предупреждения: {e}")
    else:
        punishment_name = {
            'mute': 'мут',
            'ban': 'бан',
            'warn': 'финальное предупреждение'
        }.get(punishment_type, 'наказание')

        warning_text = (
            f"⚠️ Предупреждение для @{username}\n"
            f"Причина: {reason}\n"
            f"Предупреждений: {warnings_count}/{warnings_limit}\n"
            f"При достижении лимита будет выдан: {punishment_name}"
        )

        try:
            await update.message.delete()
            warning_msg = await context.bot.send_message(chat_id, warning_text)

            context.job_queue.run_once(
                lambda context: context.bot.delete_message(chat_id, warning_msg.message_id),
                30
            )
        except Exception as e:
            logger.error(f"Ошибка при выдаче предупреждения: {e}")

async def ban_user_spam(update: Update, context: ContextTypes.DEFAULT_TYPE, duration: int, reason: str = ""):
    """Банит пользователя на указанное время (для антиспама)"""
    if update.message:
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        username = update.message.from_user.username or update.message.from_user.first_name
    else:
        return

    try:
        until_date = datetime.now() + timedelta(seconds=duration)

        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date
        )

        if duration < 60:
            time_str = f"{duration} секунд"
        elif duration < 3600:
            time_str = f"{duration // 60} минут"
        else:
            time_str = f"{duration // 3600} часов"

        ban_text = (
            f"🚫 Пользователь @{username} забанен на {time_str}\n"
            f"Причина: {reason}" if reason else f"🚫 Пользователь @{username} забанен на {time_str}"
        )

        ban_msg = await context.bot.send_message(chat_id, ban_text)

        context.job_queue.run_once(
            lambda context: context.bot.delete_message(chat_id, ban_msg.message_id),
            60
        )

    except Exception as e:
        logger.error(f"Ошибка при бане пользователя: {e}")
        await context.bot.send_message(chat_id, f"❌ Не удалось забанить пользователя: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE, duration: int, reason: str = ""):
    """Мутит пользователя на указанное время"""
    if update.message:
        user_id = update.message.from_user.id
        chat_id = update.message.chat_id
        username = update.message.from_user.username or update.message.from_user.first_name
    else:
        return

    try:
        permissions = ChatPermissions(can_send_messages=False)
        until_date = datetime.now() + timedelta(seconds=duration)

        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date
        )

        if duration < 60:
            time_str = f"{duration} секунд"
        elif duration < 3600:
            time_str = f"{duration // 60} минут"
        else:
            time_str = f"{duration // 3600} часов"

        mute_text = (
            f"🔇 Пользователь @{username} замучен на {time_str}\n"
            f"Причина: {reason}" if reason else f"🔇 Пользователь @{username} замучен на {time_str}"
        )

        mute_msg = await context.bot.send_message(chat_id, mute_text)

        context.job_queue.run_once(
            lambda context: context.bot.delete_message(chat_id, mute_msg.message_id),
            60
        )

        context.job_queue.run_once(
            lambda context: unmute_user_job(context, chat_id, user_id),
            duration
        )

    except Exception as e:
        logger.error(f"Ошибка при муте пользователя: {e}")
        await context.bot.send_message(chat_id, f"❌ Не удалось замутить пользователя: {e}")

async def unmute_user_job(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """Размучивает пользователя (для job queue)"""
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )

        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions
        )
    except Exception as e:
        logger.error(f"Ошибка при автоматическом размуте: {e}")

async def get_smart_ai_response(message_text: str, user_id: int = None, chat_id: int = None) -> str:
    """🤖 Простой ИИ - повторяет только слова участников и составляет из них предложения"""
    import random

    chat_words_key = f"chat_words_{chat_id}" if chat_id else "chat_words_general"
    chat_words = db.get(chat_words_key, [])

    words = message_text.split()
    clean_words = []

    for word in words:
        clean_word = ''.join(char.lower() for char in word if char.isalnum() or char.isspace()).strip()
        if clean_word and len(clean_word) > 1:
            clean_words.append(clean_word)

    chat_words.extend(clean_words)

    chat_words = chat_words[-100:]
    db.set(chat_words_key, chat_words)

    if len(chat_words) < 3:
        return None

    def make_sentence():
        sentence_length = random.randint(2, 6)
        available_words = list(set(chat_words))

        if len(available_words) < sentence_length:
            sentence_length = len(available_words)

        if sentence_length < 2:
            return None

        selected_words = random.sample(available_words, sentence_length)

        return " ".join(selected_words)

    sentence = make_sentence()
    if sentence:
        return sentence
    else:
        return None

def parse_time(time_str: str) -> int:
    """Парсит строку времени в секунды"""
    try:
        if time_str.endswith('с') or time_str.endswith('s'):
            return int(time_str[:-1])
        elif time_str.endswith('м') or time_str.endswith('m'):
            return int(time_str[:-1]) * 60
        elif time_str.endswith('ч') or time_str.endswith('h'):
            return int(time_str[:-1]) * 3600
        elif time_str.endswith('д') or time_str.endswith('d'):
            return int(time_str[:-1]) * 86400
        else:
            return int(time_str) * 60
    except:
        return 300

# Обработчики команд

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    welcome_text = """
🤖 **Чат-Менеджер Бот активирован!**

Я умею:
• 🛡️ Автоматически блокировать спам
• 🔇 Мутить и банить пользователей
• ⚙️ Настраивать правила чата
• 👋 Приветствовать новых участников
• 🧠 Отвечать на некоторые сообщения (включите в настройках)

**Команды администратора:**
/mute [@user или reply] [время] - Замутить пользователя
/unmute [@user или reply] - Размутить пользователя
/ban [@user или reply] [время] - Забанить пользователя
/unban [@user] - Разбанить пользователя
/settings - Настройки чата
/rules [текст] - Показать или установить правила
/ai - Настройки ИИ

**Русские команды администратора (в ответ на сообщение):**
`мут [время]` - замутить пользователя
`бан [время]` - забанить пользователя
`размут` - размутить пользователя
`правила` - показать правила чата
`+правила текст` - установить новые правила

**РП команды (в ответ на сообщение):**
`обнять` - обнять пользователя
`лизнуть` - лизнуть пользователя
`пожать руку` - пожать руку пользователю
`поцеловать` - поцеловать пользователя
`погладить` - погладить по голове
`подмигнуть` - подмигнуть пользователю
И еще 6 РП команд!

**Команды брака:**
`жениться` - жениться (в ответ на сообщение)
`развестись` - развестись
`мой муж` / `моя жена` - информация о браке
`список пар` - все пары в чате

**Примеры:**
`/mute 30m` - мут на 30 минут
`мут 2ч` - мут на 2 часа
`обнять` - обнять (в ответ на сообщение)
`жениться` - пожениться (в ответ на сообщение)
"""

    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /mute"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            username = update.message.from_user.username or update.message.from_user.first_name
            await update.message.reply_text(
                f"❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                f"@{username}, у вас нет прав администратора для использования команды `/mute`.\n"
                f"Обратитесь к администраторам группы для получения необходимых прав.",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора для /mute: {e}")
        await update.message.reply_text("❌ Ошибка при проверке прав доступа!")
        return

    target_user = None
    duration = 300

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args and len(context.args) > 0:
            duration = parse_time(context.args[0])

    elif context.args and len(context.args) >= 2 and context.args[0].startswith('@'):
        username = context.args[0][1:]
        duration = parse_time(context.args[1])
        await update.message.reply_text("❌ Поиск по username пока не поддерживается. Пожалуйста, ответьте на сообщение пользователя.")
        return

    elif context.args and len(context.args) == 1:
        await update.message.reply_text(
            "❌ Укажите пользователя для мута!\n"
            "Использование:\n"
            "• Ответьте на сообщение пользователя и напишите `/mute [время]`\n"
            "• Пример: `/mute 5д` (в ответ на сообщение)\n"
            "• Форматы времени: `30с`, `5м`, `2ч`, `1д`"
        )
        return

    else:
        await update.message.reply_text(
            "❌ Использование команды `/mute`:\n"
            "• Ответьте на сообщение пользователя и напишите `/mute [время]`\n"
            "• Примеры: `/mute` (5 минут), `/mute 30м`, `/mute 2ч`, `/mute 1д`\n"
            "• Форматы: с/s (секунды), м/m (минуты), ч/h (часы), д/d (дни)"
        )
        return

    if target_user:
        try:
            target_member = await context.bot.get_chat_member(chat_id, target_user.id)
            if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await update.message.reply_text("❌ Нельзя замутить администратора или владельца чата!")
                return
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса пользователя: {e}")

        try:
            permissions = ChatPermissions(can_send_messages=False)
            until_date = datetime.now() + timedelta(seconds=duration)

            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user.id,
                permissions=permissions,
                until_date=until_date
            )

            if duration < 60:
                time_str = f"{duration} секунд"
            elif duration < 3600:
                time_str = f"{duration // 60} минут"
            elif duration < 86400:
                time_str = f"{duration // 3600} часов"
            else:
                time_str = f"{duration // 86400} дней"

            username = target_user.username or target_user.first_name
            admin_name = update.message.from_user.username or update.message.from_user.first_name

            mute_text = (
                f"🔇 ПОЛЬЗОВАТЕЛЬ ЗАМУЧЕН\n\n"
                f"👤 Пользователь: @{username} ({target_user.first_name})\n"
                f"⏱️ Время мута: {time_str}\n"
                f"👮‍♂️ Администратор: @{admin_name}\n"
                f"📝 Причина: Ручная команда администратора"
            )

            await context.bot.send_message(chat_id, mute_text)

            context.job_queue.run_once(
                lambda context: unmute_user_job(context, chat_id, target_user.id),
                duration
            )

        except Exception as e:
            logger.error(f"Ошибка при муте пользователя: {e}")
            await update.message.reply_text(f"❌ Не удалось замутить пользователя: {e}")

async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unmute"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            username = update.message.from_user.username or update.message.from_user.first_name
            await update.message.reply_text(
                f"❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                f"@{username}, у вас нет прав администратора для использования команды `/unmute`.\n"
                f"Обратитесь к администраторам группы для получения необходимых прав.",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора для /unmute: {e}")
        await update.message.reply_text("❌ Ошибка при проверке прав доступа!")
        return

    target_user = None

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    else:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя для размута")
        return

    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )

        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            permissions=permissions
        )

        username = target_user.username or target_user.first_name
        admin_name = update.message.from_user.username or update.message.from_user.first_name

        unmute_text = (
            f"🔊 ПОЛЬЗОВАТЕЛЬ РАЗМУЧЕН\n\n"
            f"👤 Пользователь: @{username} ({target_user.first_name})\n"
            f"👮‍♂️ Администратор: @{admin_name}\n"
            f"📝 Причина: Ручная команда администратора"
        )

        await context.bot.send_message(chat_id, unmute_text)

    except Exception as e:
        logger.error(f"Ошибка при размуте: {e}")
        await update.message.reply_text(f"❌ Не удалось размутить пользователя: {e}")

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ban"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            username = update.message.from_user.username or update.message.from_user.first_name
            await update.message.reply_text(
                f"❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                f"@{username}, у вас нет прав администратора для использования команды `/ban`.\n"
                f"Обратитесь к администраторам группы для получения необходимых прав.",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора для /ban: {e}")
        await update.message.reply_text("❌ Ошибка при проверке прав доступа!")
        return

    target_user = None
    duration = None
    duration_text = "навсегда"

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            duration_seconds = parse_time(context.args[0])
            duration = datetime.now() + timedelta(seconds=duration_seconds)

            if duration_seconds < 60:
                duration_text = f"{duration_seconds} секунд"
            elif duration_seconds < 3600:
                duration_text = f"{duration_seconds // 60} минут"
            elif duration_seconds < 86400:
                duration_text = f"{duration_seconds // 3600} часов"
            else:
                duration_text = f"{duration_seconds // 86400} дней"
    else:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя для бана")
        return

    try:
        target_member = await context.bot.get_chat_member(chat_id, target_user.id)
        if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            await update.message.reply_text("❌ Нельзя забанить администратора или владельца чата!")
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса пользователя: {e}")

    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            until_date=duration
        )

        username = target_user.username or target_user.first_name
        admin_name = update.message.from_user.username or update.message.from_user.first_name

        ban_text = (
            f"🚫 ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН\n\n"
            f"👤 Пользователь: @{username} ({target_user.first_name})\n"
            f"⏱️ Длительность: {duration_text}\n"
            f"👮‍♂️ Администратор: @{admin_name}\n"
            f"📝 Причина: Ручная команда администратора"
        )

        await context.bot.send_message(chat_id, ban_text)

    except Exception as e:
        logger.error(f"Ошибка при бане: {e}")
        await update.message.reply_text(f"❌ Не удалось забанить пользователя: {e}")

async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /unban"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            username = update.message.from_user.username or update.message.from_user.first_name
            await update.message.reply_text(
                f"❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                f"@{username}, у вас нет прав администратора для использования команды `/unban`.\n"
                f"Обратитесь к администраторам группы для получения необходимых прав.",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора для /unban: {e}")
        await update.message.reply_text("❌ Ошибка при проверке прав доступа!")
        return

    target_user = None

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
    elif context.args and context.args[0].startswith('@'):
        await update.message.reply_text("❌ Поиск по username пока не поддерживается. Пожалуйста, ответьте на сообщение пользователя.")
        return
    else:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя для разбана")
        return

    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=target_user.id,
            only_if_banned=True
        )

        username = target_user.username or target_user.first_name
        admin_name = update.message.from_user.username or update.message.from_user.first_name

        unban_text = (
            f"✅ ПОЛЬЗОВАТЕЛЬ РАЗБАНЕН\n\n"
            f"👤 Пользователь: @{username} ({target_user.first_name})\n"
            f"👮‍♂️ Администратор: @{admin_name}\n"
            f"📝 Причина: Ручная команда администратора\n\n"
            f"ℹ️ Пользователь может снова присоединиться к чату"
        )

        await context.bot.send_message(chat_id, unban_text)

    except Exception as e:
        logger.error(f"Ошибка при разбане: {e}")
        await update.message.reply_text(f"❌ Не удалось разбанить пользователя: {e}")

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settings"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды!")
        return

    settings = get_chat_settings(chat_id)

    mute_duration = settings.get('mute_duration', 300)
    ban_duration = settings.get('ban_duration', 3600)

    mute_time_str = f"{mute_duration // 60}м" if mute_duration < 3600 else f"{mute_duration // 3600}ч"
    ban_time_str = f"{ban_duration // 60}м" if ban_duration < 3600 else f"{ban_duration // 3600}ч"

    punishment_names = {'warn': 'Предупреждение', 'mute': 'Мут', 'ban': 'Бан'}
    current_punishment = punishment_names.get(settings.get('punishment_type', 'mute'), 'Мут')

    rapid_count = settings.get('rapid_messages_count', 5)
    ai_enabled = settings.get('ai_enabled', False)
    ai_status = '✅ Включены' if ai_enabled else '❌ Выключены'

    settings_text = f"""
⚙️ **Настройки чата**

🛡️ Антиспам: {'✅ Включен' if settings.get('antispam_enabled', True) else '❌ Выключен'}
🤖 Автомодерация: {'✅ Включена' if settings.get('auto_moderation', True) else '❌ Выключена'}
👋 Приветствие новых: {'✅ Включено' if settings.get('welcome_message', True) else '❌ Выключено'}
🗑️ Удаление служебных: {'✅ Включено' if settings.get('delete_service_messages', True) else '❌ Выключено'}

**Настройки наказаний:**
⚡ Тип наказания: {current_punishment}
⏱️ Длительность мута: {mute_time_str}
⏱️ Длительность бана: {ban_time_str}
⚠️ Предупреждений до наказания: {settings.get('warnings_before_punishment', 3)}

**Лимиты антиспама:**
⚡ Быстрых сообщений подряд: {rapid_count} за {SPAM_SETTINGS['rapid_messages_time']} сек
🔄 Одинаковых сообщений: {SPAM_SETTINGS['max_identical_messages']}

🧠 **ИИ ответы:** {ai_status} - _используйте команду **/ai** для настройки_

Для изменения настроек используйте кнопки ниже.
"""

    keyboard = [
        [
            InlineKeyboardButton(
                f"🛡️ Антиспам: {'✅' if settings.get('antispam_enabled', True) else '❌'}",
                callback_data='toggle_antispam'
            ),
            InlineKeyboardButton(
                f"🤖 Автомодерация: {'✅' if settings.get('auto_moderation', True) else '❌'}",
                callback_data='toggle_auto_mod'
            )
        ],
        [
            InlineKeyboardButton(
                f"👋 Приветствие: {'✅' if settings.get('welcome_message', True) else '❌'}",
                callback_data='toggle_welcome'
            ),
            InlineKeyboardButton(
                f"⚡ Наказание: {current_punishment}",
                callback_data='change_punishment'
            )
        ],
        [
            InlineKeyboardButton(
                f"⚠️ Предупреждений: {settings.get('warnings_before_punishment', 3)}",
                callback_data='change_warnings'
            ),
            InlineKeyboardButton(
                f"📊 Спам лимит: {rapid_count}",
                callback_data='change_rapid_count'
            )
        ],
        [
            InlineKeyboardButton(
                f"🔇 Мут: {mute_time_str}",
                callback_data='change_mute_time'
            ),
            InlineKeyboardButton(
                f"🚫 Бан: {ban_time_str}",
                callback_data='change_ban_time'
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(settings_text, parse_mode='Markdown', reply_markup=reply_markup)

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /warn для выдачи предупреждений"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    try:
        chat_member = await context.bot.get_chat_member(chat_id, user_id)
        if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            username = update.message.from_user.username or update.message.from_user.first_name
            await update.message.reply_text(
                f"❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                f"@{username}, у вас нет прав администратора для использования команды `/warn`.\n"
                f"Обратитесь к администраторам группы для получения необходимых прав.",
                parse_mode='Markdown'
            )
            return
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора для /warn: {e}")
        await update.message.reply_text("❌ Ошибка при проверке прав доступа!")
        return

    target_user = None
    reason = "Нарушение правил чата"

    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if context.args:
            reason = " ".join(context.args)
    else:
        await update.message.reply_text(
            "❌ Использование команды `/warn`:\n"
            "• Ответьте на сообщение пользователя и напишите `/warn [причина]`\n"
            "• Пример: `/warn спам` (в ответ на сообщение)"
        )
        return

    if target_user:
        try:
            target_member = await context.bot.get_chat_member(chat_id, target_user.id)
            if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await update.message.reply_text("❌ Нельзя предупредить администратора или владельца чата!")
                return
        except Exception as e:
            logger.error(f"Ошибка при проверке статуса пользователя: {e}")

        settings = get_chat_settings(chat_id)
        warnings_limit = settings.get('warnings_before_punishment', 3)

        user_warnings[target_user.id] += 1
        warnings_count = user_warnings[target_user.id]

        username = target_user.username or target_user.first_name
        admin_name = update.message.from_user.username or update.message.from_user.first_name

        if warnings_count >= warnings_limit:
            punishment_type = settings.get('punishment_type', 'mute')
            user_warnings[target_user.id] = 0

            if punishment_type == 'mute':
                duration = settings.get('mute_duration', 300)
                await mute_user(update, context, duration, f"превышение лимита предупреждений ({reason})")
            elif punishment_type == 'ban':
                duration = settings.get('ban_duration', 3600)
                await ban_user_spam(update, context, duration, f"превышение лимита предупреждений ({reason})")
            else:
                warn_text = (
                    f"⚠️ **ФИНАЛЬНОЕ ПРЕДУПРЕЖДЕНИЕ** для @{username}\n\n"
                    f"👤 Пользователь: {target_user.first_name}\n"
                    f"📝 Причина: {reason}\n"
                    f"👮‍♂️ Администратор: @{admin_name}\n"
                    f"🚨 Следующее нарушение приведет к дополнительным мерам!"
                )
                await context.bot.send_message(chat_id, warn_text, parse_mode='Markdown')
        else:
            punishment_name = {
                'mute': 'мут',
                'ban': 'бан',
                'warn': 'финальное предупреждение'
            }.get(settings.get('punishment_type', 'mute'), 'наказание')

            warn_text = (
                f"⚠️ **ПРЕДУПРЕЖДЕНИЕ** для @{username}\n\n"
                f"👤 Пользователь: {target_user.first_name}\n"
                f"📝 Причина: {reason}\n"
                f"👮‍♂️ Администратор: @{admin_name}\n"
                f"📊 Предупреждений: {warnings_count}/{warnings_limit}\n"
                f"🚨 При достижении лимита будет выдан: {punishment_name}"
            )

            await context.bot.send_message(chat_id, warn_text, parse_mode='Markdown')

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /rules для показа или установки правил"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    chat_id = update.message.chat_id

    if context.args:
        user_id = update.message.from_user.id

        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await update.message.reply_text(
                    "❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                    "У вас нет прав администратора для изменения правил чата.\n"
                    "Обратитесь к администраторам группы.",
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Ошибка при проверке прав администратора для команды /rules: {e}")
            await update.message.reply_text("❌ Ошибка при проверке прав доступа!")
            return

        new_rules = " ".join(context.args)

        db.set(f"rules_{chat_id}", new_rules)

        await update.message.reply_text(
            f"✅ **Правила чата обновлены!**\n\n"
            f"📋 **Новые правила:**\n{new_rules}",
            parse_mode='Markdown'
        )
    else:
        rules = db.get(f"rules_{chat_id}", "Правила чата не установлены.")

        await update.message.reply_text(
            f"📋 **Правила чата:**\n\n{rules}",
            parse_mode='Markdown'
        )

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ai для настройки ИИ"""
    if not update.message.chat.type in ['group', 'supergroup']:
        await update.message.reply_text("❌ Эта команда работает только в группах!")
        return

    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды!")
        return

    settings = get_chat_settings(chat_id)

    ai_enabled = settings.get('ai_enabled', False)
    ai_chance = settings.get('ai_response_chance', 10)
    ai_status = '✅ Включены' if ai_enabled else '❌ Выключены'

    ai_settings_text = f"""
🧠 **Настройки ИИ ответов**

🤖 Статус ИИ: {ai_status}
📊 Шанс ответа: {ai_chance}%

Для изменения настроек используйте кнопки ниже.
"""

    keyboard = [
        [
            InlineKeyboardButton(
                f"🧠 ИИ: {'✅' if ai_enabled else '❌'}",
                callback_data='toggle_ai'
            ),
            InlineKeyboardButton(
                f"🎯 Шанс ответа: {ai_chance}%",
                callback_data='change_ai_chance'
            )
        ],
        [
            InlineKeyboardButton(
                f"🔙 К основным настройкам",
                callback_data='back_to_settings'
            )
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(ai_settings_text, parse_mode='Markdown', reply_markup=reply_markup)


async def russian_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик русских команд"""
    if not update.message or not update.message.text:
        return

    if not update.message.chat.type in ['group', 'supergroup']:
        return

    text = update.message.text.lower().strip()
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    moderation_commands = ['мут', 'бан', 'размут', 'варн', '+правила']
    is_moderation_command = any(text.startswith(cmd) for cmd in moderation_commands)

    if is_moderation_command:
        try:
            chat_member = await context.bot.get_chat_member(chat_id, user_id)
            if chat_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                username = update.message.from_user.username or update.message.from_user.first_name
                command_name = text.split()[0] if ' ' in text else text
                await update.message.reply_text(
                    f"❌ **ДОСТУП ЗАПРЕЩЕН**\n\n"
                    f"@{username}, у вас нет прав администратора для использования команды `{command_name}`.\n"
                    f"Обратитесь к администраторам группы для получения необходимых прав.",
                    parse_mode='Markdown'
                )
                return
        except Exception as e:
            logger.error(f"Ошибка при проверке прав администратора для русских команд: {e}")
            return

    rp_commands = {
        'обнять': ['обнимает', '🤗'],
        'лизнуть': ['лизнул', '👅'], 
        'пожать руку': ['пожал руку', '🤝'],
        'поцеловать': ['поцеловал', '😘'],
        'ударить': ['ударил', '👊'],
        'обнимашки': ['крепко обнимает', '🫂'],
        'погладить': ['гладит по голове', '🤲'],
        'подмигнуть': ['подмигнул', '😉'],
        'поклониться': ['поклонился', '🙇'],
        'потанцевать': ['танцует с', '💃'],
        'поцеловать в щечку': ['нежно поцеловал в щечку', '😚'],
        'дать пять': ['дал пять', '🙏']
    }

    marriage_commands = ['жениться', 'развестись', 'мой муж', 'моя жена', 'список пар']

    for command, action_data in rp_commands.items():
        if text.startswith(command):
            if not update.message.reply_to_message:
                await update.message.reply_text(
                    f"❌ Ответьте на сообщение пользователя, чтобы {command}"
                )
                return

            target_user = update.message.reply_to_message.from_user
            user_name = update.message.from_user.first_name
            target_name = target_user.first_name
            action_verb, emoji = action_data

            if target_user.id == user_id:
                await update.message.reply_text(
                    f"😅 {user_name}, нельзя {command} самого себя!"
                )
                return

            rp_text = f"{emoji} {user_name} {action_verb} {target_name}"
            await update.message.reply_text(rp_text)
            return

    if text in marriage_commands:
        if text == 'жениться':
            if not update.message.reply_to_message:
                await update.message.reply_text(
                    "💍 Ответьте на сообщение пользователя, за которого хотите выйти замуж/жениться"
                )
                return

            target_user = update.message.reply_to_message.from_user
            user_name = update.message.from_user.first_name
            target_name = target_user.first_name

            if target_user.id == user_id:
                await update.message.reply_text(
                    "😅 Нельзя жениться на самом себе!"
                )
                return

            marriages = db.get(f"marriages_{chat_id}", {})
            
            if str(user_id) in marriages:
                await update.message.reply_text(
                    f"💔 {user_name}, вы уже состоите в браке! Сначала разведитесь."
                )
                return

            if str(target_user.id) in marriages:
                await update.message.reply_text(
                    f"💔 {target_name} уже состоит в браке с кем-то другим!"
                )
                return

            proposal_id = f"{user_id}_{target_user.id}_{chat_id}"
            proposals = db.get("marriage_proposals", {})
            proposals[proposal_id] = {
                'proposer_id': user_id,
                'proposer_name': user_name,
                'target_id': target_user.id,
                'target_name': target_name,
                'chat_id': chat_id,
                'timestamp': datetime.now().isoformat()
            }
            db.set("marriage_proposals", proposals)

            proposal_text = (
                f"💍 **ПРЕДЛОЖЕНИЕ БРАКА!** 💍\n\n"
                f"🤵 {user_name} делает предложение 👰 {target_name}!\n\n"
                f"💕 {target_name}, согласны ли вы стать мужем/женой {user_name}?"
            )

            keyboard = [
                [
                    InlineKeyboardButton("💒 Да, согласен(на)!", callback_data=f"accept_marriage_{proposal_id}"),
                    InlineKeyboardButton("💔 Нет, отказываюсь", callback_data=f"reject_marriage_{proposal_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(proposal_text, parse_mode='Markdown', reply_markup=reply_markup)
            return

        elif text == 'развестись':
            marriages = db.get(f"marriages_{chat_id}", {})
            
            if str(user_id) not in marriages:
                await update.message.reply_text(
                    "💔 Вы не состоите в браке!"
                )
                return

            partner_data = marriages[str(user_id)]
            partner_id = partner_data['partner_id']
            partner_name = partner_data['partner_name']
            user_name = update.message.from_user.first_name

            del marriages[str(user_id)]
            if str(partner_id) in marriages:
                del marriages[str(partner_id)]
            
            db.set(f"marriages_{chat_id}", marriages)

            divorce_text = (
                f"💔 **РАЗВОД В ЧАТЕ!** 💔\n\n"
                f"😢 {user_name} развелся с {partner_name}\n"
                f"📅 Дата развода: {datetime.now().strftime('%d.%m.%Y')}\n"
                f"💔 Их любовь закончилась..."
            )
            await update.message.reply_text(divorce_text, parse_mode='Markdown')
            return

        elif text in ['мой муж', 'моя жена']:
            marriages = db.get(f"marriages_{chat_id}", {})
            
            if str(user_id) not in marriages:
                await update.message.reply_text(
                    "💔 Вы не состоите в браке!"
                )
                return

            partner_data = marriages[str(user_id)]
            partner_name = partner_data['partner_name']
            marriage_date = partner_data['marriage_date']
            user_name = update.message.from_user.first_name

            marriage_info = (
                f"💕 **ИНФОРМАЦИЯ О БРАКЕ** 💕\n\n"
                f"👤 {user_name}\n"
                f"💍 В браке с: {partner_name}\n"
                f"📅 Дата свадьбы: {marriage_date}\n"
                f"❤️ Любовь длится уже {(datetime.now() - datetime.strptime(marriage_date, '%d.%m.%Y')).days} дней!"
            )
            await update.message.reply_text(marriage_info, parse_mode='Markdown')
            return

        elif text == 'список пар':
            marriages = db.get(f"marriages_{chat_id}", {})
            
            if not marriages:
                await update.message.reply_text(
                    "💔 В этом чате пока нет зарегистрированных браков!"
                )
                return

            couples_text = "💕 СПИСОК ПАР В ЧАТЕ 💕\n\n"
            processed_pairs = set()
            
            for user_id_str, partner_data in marriages.items():
                partner_id = partner_data['partner_id']
                
                pair = tuple(sorted([int(user_id_str), partner_id]))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)
                
                if str(partner_id) in marriages:
                    user_name = marriages[str(partner_id)]['partner_name']
                else:
                    user_name = 'Неизвестно'
                
                partner_name = partner_data.get('partner_name', 'Неизвестно')
                marriage_date = partner_data['marriage_date']
                
                couples_text += f"💒 {user_name} ❤️ {partner_name} (с {marriage_date})\n"
            
            await update.message.reply_text(couples_text)
            return

    if text.startswith('мут'):
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя для мута")
            return

        parts = text.split()
        duration = 300

        if len(parts) > 1:
            duration = parse_time(parts[1])

        target_user = update.message.reply_to_message.from_user

        try:
            target_member = await context.bot.get_chat_member(chat_id, target_user.id)
            if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await update.message.reply_text("❌ Нельзя замутить администратора!")
                return
        except:
            pass

        try:
            permissions = ChatPermissions(can_send_messages=False)
            until_date = datetime.now() + timedelta(seconds=duration)

            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user.id,
                permissions=permissions,
                until_date=until_date
            )

            if duration < 60:
                time_str = f"{duration} секунд"
            elif duration < 3600:
                time_str = f"{duration // 60} минут"
            elif duration < 86400:
                time_str = f"{duration // 3600} часов"
            else:
                time_str = f"{duration // 86400} дней"

            username = target_user.username or target_user.first_name
            admin_name = update.message.from_user.username or update.message.from_user.first_name

            mute_text = (
                f"🔇 ПОЛЬЗОВАТЕЛЬ ЗАМУЧЕН\n\n"
                f"👤 Пользователь: @{username} ({target_user.first_name})\n"
                f"⏱️ Время мута: {time_str}\n"
                f"👮‍♂️ Администратор: @{admin_name}\n"
                f"📝 Причина: Команда администратора (русская)"
            )

            await context.bot.send_message(chat_id, mute_text)

            context.job_queue.run_once(
                lambda context: unmute_user_job(context, chat_id, target_user.id),
                duration
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при муте: {e}")

    elif text.startswith('бан'):
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя для бана")
            return

        parts = text.split()
        duration = None
        duration_text = "навсегда"

        if len(parts) > 1:
            duration_seconds = parse_time(parts[1])
            duration = datetime.now() + timedelta(seconds=duration_seconds)

            if duration_seconds < 60:
                duration_text = f"{duration_seconds} секунд"
            elif duration_seconds < 3600:
                duration_text = f"{duration_seconds // 60} минут"
            elif duration_seconds < 86400:
                duration_text = f"{duration_seconds // 3600} часов"
            else:
                duration_text = f"{duration_seconds // 86400} дней"

        target_user = update.message.reply_to_message.from_user

        try:
            target_member = await context.bot.get_chat_member(chat_id, target_user.id)
            if target_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                await update.message.reply_text("❌ Нельзя забанить администратора!")
                return
        except:
            pass

        try:
            await context.bot.ban_chat_member(
                chat_id=chat_id,
                user_id=target_user.id,
                until_date=duration
            )

            username = target_user.username or target_user.first_name
            admin_name = update.message.from_user.username or update.message.from_user.first_name

            ban_text = (
                f"🚫 ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН\n\n"
                f"👤 Пользователь: @{username} ({target_user.first_name})\n"
                f"⏱️ Длительность: {duration_text}\n"
                f"👮‍♂️ Администратор: @{admin_name}\n"
                f"📝 Причина: Команда администратора (русская)"
            )

            await context.bot.send_message(chat_id, ban_text)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при бане: {e}")

    elif text == 'размут':
        if not update.message.reply_to_message:
            await update.message.reply_text("❌ Ответьте на сообщение пользователя для размута")
            return

        target_user = update.message.reply_to_message.from_user

        try:
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )

            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=target_user.id,
                permissions=permissions
            )

            username = target_user.username or target_user.first_name
            admin_name = update.message.from_user.username or update.message.from_user.first_name

            unmute_text = (
                f"🔊 ПОЛЬЗОВАТЕЛЬ РАЗМУЧЕН\n\n"
                f"👤 Пользователь: @{username} ({target_user.first_name})\n"
                f"👮‍♂️ Администратор: @{admin_name}\n"
                f"📝 Причина: Команда администратора (русская)"
            )

            await context.bot.send_message(chat_id, unmute_text)

        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка при размуте: {e}")

    elif text == 'прав
