import os
import asyncio
import logging
import time
import re
from typing import Dict
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import FSInputFile, CallbackQuery
import yt_dlp

# --- RENDER ÜÇÜN KONFİQURASİYA ---
ffmpeg_path = os.path.join(os.getcwd(), 'bin')
os.environ["PATH"] += os.pathsep + ffmpeg_path

# Tokeni Environment Variables-dən götürür, yoxdursa bura birbaşa yaz
API_TOKEN = os.getenv('8621629815:AAEEKQF5aTDT1K-FOvUxiy6isiPytNjgrnw', '8621629815:AAEEKQF5aTDT1K-FOvUxiy6isiPytNjgrnw')
DOWNLOAD_DIR = '/tmp/downloads' # Render-də müvəqqəti yaddaş (Writable)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()

# --- DİLLƏR ---
STRINGS = {
    'az': {
        'welcome': "🎬 YouTube Video/MP3 Yükləyiciyə xoş gəldiniz!\nLinki göndərin:",
        'choose': "Hansı formatda yüklənsin?",
        'downloading': "⏳ Yüklənir: {percent}%",
        'uploading': "📤 Fayl Telegram-a göndərilir...",
        'error': "❌ Xəta! YouTube blokuna düşmüş ola bilərik və ya link səhvdir.",
        'video': "🎬 Video (MP4)",
        'audio': "🎵 Musiqi (MP3)"
    },
    'tr': {
        'welcome': "Hoş geldiniz! Bağlantıyı gönderin:",
        'choose': "Format seçin:",
        'downloading': "⏳ İndiriliyor: {percent}%",
        'uploading': "📤 Dosya gönderiliyor...",
        'error': "❌ Hata oluştu! Lütfen tekrar deneyin.",
        'video': "🎬 Video (MP4)",
        'audio': "🎵 Müzik (MP3)"
    },
    'en': {
        'welcome': "Welcome! Send the YouTube link:",
        'choose': "Choose format:",
        'downloading': "⏳ Downloading: {percent}%",
        'uploading': "📤 Uploading to Telegram...",
        'error': "❌ Error! Something went wrong.",
        'video': "🎬 Video (MP4)",
        'audio': "🎵 Music (MP3)"
    }
}

user_langs: Dict[int, str] = {}

def get_text(user_id, key):
    lang = user_langs.get(user_id, 'az')
    return STRINGS[lang].get(key, STRINGS['en'][key])

def extract_video_id(url):
    pattern = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
    match = re.search(pattern, url)
    return match.group(1) if match else None

# --- PROGRESS HOOK (STABIL) ---
def progress_hook(d, message_data: dict, loop, last_update):
    if d['status'] == 'downloading':
        p_raw = d.get('_percent_str', '0%')
        p = re.sub(r'\x1b\[[0-9;]*m', '', p_raw).replace('%', '').strip()
        
        current_time = time.time()
        if current_time - last_update[0] > 5: # Telegram limitləri üçün 5 saniyədən bir
            text = get_text(message_data['chat_id'], 'downloading').format(percent=p)
            asyncio.run_coroutine_threadsafe(
                bot.edit_message_text(
                    text=text, 
                    chat_id=message_data['chat_id'], 
                    message_id=message_data['message_id']
                ), 
                loop
            )
            last_update[0] = current_time

async def download_media(video_id, mode, status_msg):
    loop = asyncio.get_event_loop()
    last_update = [0]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    # Progress üçün lazım olan məlumatlar
    message_data = {
        'chat_id': status_msg.chat.id,
        'message_id': status_msg.message_id
    }
    
    # Kuki faylı kontrolü
    cookie_file = 'youtube_cookies.txt'
    cookie_path = cookie_file if os.path.exists(cookie_file) else None

    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, message_data, loop, last_update)],
        'quiet': True,
        'noplaylist': True,
        'cookiefile': cookie_path,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }
    }

    if mode == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        # Render-də 403 xətası almamamaq üçün stabil MP4 formatı
        ydl_opts.update({
            'format': 'best[ext=mp4]/best',
        })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
        file_path = ydl.prepare_filename(info)
        if mode == 'audio':
            file_path = os.path.splitext(file_path)[0] + ".mp3"
        return file_path

# --- HANDLERLƏR ---

@router.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="Azərbaycan 🇦🇿", callback_data="lang_az")
    kb.button(text="Türkçe 🇹🇷", callback_data="lang_tr")
    kb.button(text="English 🇺🇸", callback_data="lang_en")
    kb.adjust(1)
    await message.answer("Dili seçin / Choose language:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery):
    lang = callback.data.split("_")[1]
    user_langs[callback.from_user.id] = lang
    await callback.message.edit_text(get_text(callback.from_user.id, 'welcome'))

@router.message(F.text.regexp(r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+'))
async def handle_link(message: types.Message):
    video_id = extract_video_id(message.text)
    if not video_id: return
    
    uid = message.from_user.id
    kb = InlineKeyboardBuilder()
    kb.button(text=get_text(uid, 'video'), callback_data=f"vid|{video_id}")
    kb.button(text=get_text(uid, 'audio'), callback_data=f"aud|{video_id}")
    kb.adjust(2)
    await message.answer(get_text(uid, 'choose'), reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("vid|") | F.data.startswith("aud|"))
async def process_download(callback: CallbackQuery):
    mode_raw, video_id = callback.data.split("|")
    mode = 'video' if mode_raw == 'vid' else 'audio'
    uid = callback.from_user.id
    
    status_msg = await callback.message.edit_text(get_text(uid, 'downloading').format(percent="0"))
    
    try:
        file_path = await download_media(video_id, mode, status_msg)
        
        await bot.edit_message_text(
            text=get_text(uid, 'uploading'), 
            chat_id=callback.message.chat.id, 
            message_id=status_msg.message_id
        )
        
        if os.path.exists(file_path):
            document = FSInputFile(file_path)
            me = await bot.get_me()
            if mode == 'audio':
                await callback.message.answer_audio(audio=document, caption=f"🎵 @{me.username}")
            else:
                await callback.message.answer_video(video=document, caption=f"🎬 @{me.username}")
            
            await bot.delete_message(chat_id=callback.message.chat.id, message_id=status_msg.message_id)
            os.remove(file_path)
    except Exception as e:
        logging.error(f"Error: {e}")
        await callback.message.answer(get_text(uid, 'error'))

# --- RENDER OYAQ SAXLA ---
async def handle_web(request):
    return web.Response(text="Bot is Active!")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    await start_web() # Render-də botun sönməməsi üçün veb server
    dp.include_router(router)
    print("Bot Render-də uğurla başladı!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
