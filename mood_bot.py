#!/usr/bin/env python3
"""
A gentle mood tracking Telegram bot that serves as a soft companion 
for self-reflection and emotional awareness.
"""

import asyncio
import logging
import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import hashlib
import secrets

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Mood(Enum):
    HAPPY = "😊"
    NEUTRAL = "😐"
    SAD = "😔"


@dataclass
class MoodEntry:
    id: Optional[int]
    user_id: int
    date: str
    content: str
    mood: Optional[str]
    tags: List[str]
    timestamp: datetime


class EncryptionManager:
    """Handles encryption/decryption of sensitive data"""
    
    def __init__(self, key: str):
        self.key = key.encode('utf-8')[:32].ljust(32, b'\0')  # Pad or truncate to 32 bytes
    
    def encrypt(self, plaintext: str) -> str:
        """Simple XOR-based encryption (in production, use proper crypto library)"""
        plaintext_bytes = plaintext.encode('utf-8')
        encrypted = bytearray()
        
        for i, byte in enumerate(plaintext_bytes):
            encrypted.append(byte ^ self.key[i % len(self.key)])
        
        return encrypted.hex()
    
    def decrypt(self, ciphertext_hex: str) -> str:
        """Decrypt the ciphertext"""
        ciphertext = bytes.fromhex(ciphertext_hex)
        decrypted = bytearray()
        
        for i, byte in enumerate(ciphertext):
            decrypted.append(byte ^ self.key[i % len(self.key)])
        
        return decrypted.decode('utf-8')


class DatabaseManager:
    """Manages database operations for the mood tracker"""
    
    def __init__(self, db_path: str, encryption_key: str):
        self.db_path = db_path
        self.encryption_manager = EncryptionManager(encryption_key)
        self.init_db()
    
    def init_db(self):
        """Initialize the database with necessary tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create table for mood entries
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mood_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                content TEXT NOT NULL,
                mood TEXT,
                tags TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create table for user settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                reminder_time TEXT DEFAULT '20:00',
                timezone_offset INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    
    def save_entry(self, entry: MoodEntry) -> bool:
        """Save a mood entry to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Encrypt the content before storing
            encrypted_content = self.encryption_manager.encrypt(entry.content)
            tags_json = json.dumps(entry.tags) if entry.tags else "[]"
            
            if entry.id is None:
                cursor.execute('''
                    INSERT INTO mood_entries (user_id, date, content, mood, tags, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (entry.user_id, entry.date, encrypted_content, entry.mood, tags_json, entry.timestamp))
            else:
                cursor.execute('''
                    UPDATE mood_entries 
                    SET content = ?, mood = ?, tags = ?, timestamp = ?
                    WHERE id = ?
                ''', (encrypted_content, entry.mood, tags_json, entry.timestamp, entry.id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving entry: {e}")
            return False
    
    def get_entries_by_user(self, user_id: int, limit: int = 10) -> List[MoodEntry]:
        """Retrieve mood entries for a specific user"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, user_id, date, content, mood, tags, timestamp
            FROM mood_entries
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        entries = []
        for row in rows:
            # Decrypt the content
            try:
                decrypted_content = self.encryption_manager.decrypt(row[3])
            except:
                decrypted_content = "[Encrypted content could not be decrypted]"
            
            try:
                tags = json.loads(row[5]) if row[5] else []
            except:
                tags = []
            
            entry = MoodEntry(
                id=row[0],
                user_id=row[1],
                date=row[2],
                content=decrypted_content,
                mood=row[4],
                tags=tags,
                timestamp=datetime.strptime(row[6], '%Y-%m-%d %H:%M:%S.%f') if '.' in row[6] else datetime.strptime(row[6], '%Y-%m-%d %H:%M:%S')
            )
            entries.append(entry)
        
        return entries
    
    def get_entries_by_date_range(self, user_id: int, start_date: str, end_date: str) -> List[MoodEntry]:
        """Retrieve mood entries within a date range"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, user_id, date, content, mood, tags, timestamp
            FROM mood_entries
            WHERE user_id = ? AND date BETWEEN ? AND ?
            ORDER BY timestamp DESC
        ''', (user_id, start_date, end_date))
        
        rows = cursor.fetchall()
        conn.close()
        
        entries = []
        for row in rows:
            # Decrypt the content
            try:
                decrypted_content = self.encryption_manager.decrypt(row[3])
            except:
                decrypted_content = "[Encrypted content could not be decrypted]"
            
            try:
                tags = json.loads(row[5]) if row[5] else []
            except:
                tags = []
            
            entry = MoodEntry(
                id=row[0],
                user_id=row[1],
                date=row[2],
                content=decrypted_content,
                mood=row[4],
                tags=tags,
                timestamp=datetime.strptime(row[6], '%Y-%m-%d %H:%M:%S.%f') if '.' in row[6] else datetime.strptime(row[6], '%Y-%m-%d %H:%M:%S')
            )
            entries.append(entry)
        
        return entries
    
    def delete_all_user_data(self, user_id: int) -> bool:
        """Delete all data for a specific user"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM mood_entries WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM user_settings WHERE user_id = ?', (user_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error deleting user data: {e}")
            return False
    
    def export_user_data(self, user_id: int) -> List[Dict]:
        """Export user data as list of dictionaries"""
        entries = self.get_entries_by_user(user_id, limit=999999)  # Get all entries
        
        export_data = []
        for entry in entries:
            export_data.append({
                'id': entry.id,
                'date': entry.date,
                'content': entry.content,
                'mood': entry.mood,
                'tags': entry.tags,
                'timestamp': entry.timestamp.isoformat()
            })
        
        return export_data


class MoodBot:
    """Main class for the mood tracking bot"""
    
    def __init__(self, token: str, db_path: str, encryption_key: str):
        self.bot = Bot(token=token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.db = DatabaseManager(db_path, encryption_key)
        
        # Register handlers
        self.register_handlers()
    
    def register_handlers(self):
        """Register all bot handlers"""
        self.dp.message(CommandStart())(self.start_handler)
        self.dp.message(Command("help"))(self.help_handler)
        self.dp.message(Command("today"))(self.today_entry_handler)
        self.dp.message(Command("history"))(self.history_handler)
        self.dp.message(Command("export"))(self.export_handler)
        self.dp.message(Command("deleteall"))(self.delete_all_handler)
        self.dp.message()(self.handle_message)
        
        # Callback handlers for inline keyboards
        self.dp.callback_query(lambda c: c.data.startswith("mood_"))(self.mood_callback)
        self.dp.callback_query(lambda c: c.data.startswith("tag_"))(self.tag_callback)
    
    async def start_handler(self, message: Message):
        """Handle /start command"""
        welcome_text = (
            "Привет! 👋\n\n"
            "Я - твой мягкий собеседник для душевных размышлений.\n"
            "Я помогаю замечать свои состояния, фиксировать мысли и со временем "
            "видеть паттерны в твоём настроении и поведении.\n\n"
            "Вот что я умею:\n"
            "- Записывать твои мысли и чувства\n"
            "- Предлагать ставить настроение к записям\n"
            "- Показывать историю твоих записей\n"
            "- Экспортировать все данные, чтобы ты всегда контролировал их\n"
            "- Удалять все данные по первому запросу\n\n"
            "Просто напиши мне, как прошёл твой день, и я сохраню это."
        )
        
        await message.answer(welcome_text)
    
    async def help_handler(self, message: Message):
        """Handle /help command"""
        help_text = (
            "Вот команды, которые я понимаю:\n\n"
            "/today - Создать запись за сегодня\n"
            "/history - Посмотреть последние записи\n"
            "/export - Экспортировать все данные\n"
            "/deleteall - Удалить все твои данные\n"
            "/help - Показать это сообщение снова\n\n"
            "Ты также можешь просто писать мне, и я сохраню твои мысли."
        )
        
        await message.answer(help_text)
    
    async def today_entry_handler(self, message: Message):
        """Handle /today command"""
        await message.answer(
            "Как прошёл твой день?\n\n"
            "Расскажи, что сегодня зацепило, что хотелось бы отметить, "
            "или просто поделись своими мыслями..."
        )
    
    async def history_handler(self, message: Message):
        """Handle /history command"""
        entries = self.db.get_entries_by_user(message.from_user.id, limit=5)
        
        if not entries:
            await message.answer("У тебя ещё нет записей. Начни с простого: напиши, как прошёл день!")
            return
        
        history_text = "Твои последние записи:\n\n"
        for entry in entries:
            mood_str = f" {entry.mood}" if entry.mood else ""
            tags_str = f" #{' #'.join(entry.tags)}" if entry.tags else ""
            history_text += f"<b>{entry.date}</b>{mood_str}\n{entry.content}{tags_str}\n\n"
        
        await message.answer(history_text, parse_mode="HTML")
    
    async def export_handler(self, message: Message):
        """Handle /export command"""
        try:
            export_data = self.db.export_user_data(message.from_user.id)
            
            if not export_data:
                await message.answer("У тебя ещё нет записей для экспорта.")
                return
            
            # Create JSON export
            json_content = json.dumps(export_data, ensure_ascii=False, indent=2)
            
            # Send as file
            from io import StringIO
            from aiogram.types.input_file import BufferedInputFile
            
            file = BufferedInputFile(json_content.encode(), filename=f"mood_tracker_export_{message.from_user.id}.json")
            await message.answer_document(file, caption="Твои записи в формате JSON")
            
        except Exception as e:
            logger.error(f"Error during export: {e}")
            await message.answer("Произошла ошибка при экспорте данных. Пожалуйста, попробуйте позже.")
    
    async def delete_all_handler(self, message: Message):
        """Handle /deleteall command"""
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Да, удалить всё", callback_data="confirm_delete")],
            [InlineKeyboardButton(text="Нет, отменить", callback_data="cancel_delete")]
        ])
        
        await message.answer(
            "Ты уверен, что хочешь удалить все свои данные? "
            "Это действие невозможно отменить, и вся история записей будет потеряна.",
            reply_markup=keyboard
        )
    
    async def handle_message(self, message: Message):
        """Handle regular text messages"""
        # Save the entry
        entry = MoodEntry(
            id=None,
            user_id=message.from_user.id,
            date=datetime.now().strftime("%Y-%m-%d"),
            content=message.text,
            mood=None,
            tags=[],
            timestamp=datetime.now()
        )
        
        success = self.db.save_entry(entry)
        
        if success:
            # Ask for mood and tags
            mood_keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="😊 Хорошее", callback_data="mood_happy"),
                    InlineKeyboardButton(text="😐 Обычное", callback_data="mood_neutral"),
                    InlineKeyboardButton(text="😔 Тяжёлое", callback_data="mood_sad")
                ]
            ])
            
            await message.answer(
                "Спасибо за доверие. Какое у тебя было сегодня настроение?",
                reply_markup=mood_keyboard
            )
        else:
            await message.answer("К сожалению, не удалось сохранить запись. Попробуйте ещё раз.")
    
    async def mood_callback(self, callback_query: types.CallbackQuery):
        """Handle mood selection"""
        user_id = callback_query.from_user.id
        mood_map = {
            "mood_happy": Mood.HAPPY.value,
            "mood_neutral": Mood.NEUTRAL.value,
            "mood_sad": Mood.SAD.value
        }
        
        selected_mood = mood_map.get(callback_query.data)
        
        # Get the latest entry for this user
        entries = self.db.get_entries_by_user(user_id, limit=1)
        
        if entries:
            entry = entries[0]
            entry.mood = selected_mood
            self.db.save_entry(entry)
        
        tag_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="#работа", callback_data="tag_work"),
                InlineKeyboardButton(text="#отношения", callback_data="tag_relationships")
            ],
            [
                InlineKeyboardButton(text="#учеба", callback_data="tag_study"),
                InlineKeyboardButton(text="#здоровье", callback_data="tag_health")
            ],
            [
                InlineKeyboardButton(text="Без тегов", callback_data="tag_none")
            ]
        ])
        
        await callback_query.message.edit_text(
            f"Отлично! Настроение сохранено как {selected_mood}\n\n"
            "Хочешь добавить теги к этой записи?",
            reply_markup=tag_keyboard
        )
        
        await callback_query.answer()
    
    async def tag_callback(self, callback_query: types.CallbackQuery):
        """Handle tag selection"""
        user_id = callback_query.from_user.id
        tag_map = {
            "tag_work": "работа",
            "tag_relationships": "отношения",
            "tag_study": "учеба",
            "tag_health": "здоровье",
            "tag_none": None
        }
        
        selected_tag = tag_map.get(callback_query.data)
        
        # Get the latest entry for this user
        entries = self.db.get_entries_by_user(user_id, limit=1)
        
        if entries:
            entry = entries[0]
            if selected_tag and selected_tag not in entry.tags:
                entry.tags.append(selected_tag)
            self.db.save_entry(entry)
        
        if selected_tag:
            await callback_query.message.edit_text(
                f"Тег '{selected_tag}' добавлен к записи!\n\n"
                "Спасибо, что поделился. Я храню твои мысли в безопасности."
            )
        else:
            await callback_query.message.edit_text(
                "Запись сохранена без тегов.\n\n"
                "Спасибо, что поделился. Я храню твои мысли в безопасности."
            )
        
        await callback_query.answer()
    
    async def run(self):
        """Run the bot"""
        logger.info("Starting the mood tracking bot...")
        await self.dp.start_polling(self.bot)


async def main():
    # Configuration
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
    DB_PATH = os.getenv("DB_PATH", "mood_tracker.db")
    
    # Generate a random encryption key if not set
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", secrets.token_hex(16))
    
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("Please set TELEGRAM_BOT_TOKEN environment variable with your bot token")
        return
    
    bot_instance = MoodBot(BOT_TOKEN, DB_PATH, ENCRYPTION_KEY)
    await bot_instance.run()


if __name__ == "__main__":
    asyncio.run(main())