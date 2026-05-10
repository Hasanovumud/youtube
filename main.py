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

# --- RENDER ÜÇÜN FFMPEG YOLU ---
ffmpeg_path = os.path.join(os.getcwd(), 'bin')
os.environ["PATH"] += os.pathsep + ffmpeg_path

# --- KONFİQURASİYA ---
# Render-də Environment Variables hissəsindən götürüləcək
API_TOKEN = os.getenv('8723229543:AAGxucoZOsCMgjU2rTjgj0cP8ZSizYJMv8g', '8723229543:AAGxucoZOsCMgjU2rTjgj0cP8ZSizYJMv8g')
DOWNLOAD_DIR = '/tmp/downloads' # Render-də müvəqqəti yaddaş

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()

# --- DİL DƏSTƏYİ ---
STRINGS = {
    'az': {
        'welcome': "Salam! YouTube linkini göndərin.",
        'choose': "Formatı seçin:",
        'downloading': "Yüklənir: {percent}%",
        'uploading': "Fayl Telegram-a yüklənir...",
        'error': "Xəta! Linki və ya ölçünü yoxlayın.",
        'video': "🎬 Video (MP4)",
        'audio': "🎵 Musiqi (MP3)"
    },
    'tr': {
        'welcome': "Merhaba! YouTube bağlantısını gönderin.",
        'choose': "Formatı seçin:",
        'downloading': "İndiriliyor: {percent}%",
        'uploading': "Dosya Telegram'a yükleniyor...",
        'error': "Hata oluştu. Bağlantıyı kontrol edin.",
        'video': "🎬 Video (MP4)",
        'audio': "🎵 Müzik (MP3)"
    },
    'en': {
        'welcome': "Hello! Send me a YouTube link.",
        'choose': "Choose format:",
        'downloading': "Downloading: {percent}%",
        'uploading': "Uploading to Telegram...",
        'error': "An error occurred. Check the link.",
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

# --- PROGRESS HOOK ---
def progress_hook(d, message: types.Message, loop, last_update):
    if d['status'] == 'downloading':
        p_raw = d.get('_percent_str', '0%')
        p = re.sub(r'\x1b\[[0-9;]*m', '', p_raw).replace('%', '').strip()
        
        current_time = time.time()
        if current_time - last_update[0] > 5:
            text = get_text(message.chat.id, 'downloading').format(percent=p)
            asyncio.run_coroutine_threadsafe(
                bot.edit_message_text(text=text, chat_id=message.chat.id, message_id=message.message_id), 
                loop
            )
            last_update[0] = current_time

async def download_media(video_id, mode, message):
    loop = asyncio.get_event_loop()
    last_update = [0]
    url = f"https://www.youtube.com/watch?v={video_id}"
    
    ydl_opts = {
        'outtmpl': f'{DOWNLOAD_DIR}/%(title)s_%(id)s.%(ext)s',
        'progress_hooks': [lambda d: progress_hook(d, message, loop, last_update)],
        'quiet': True,
        'noplaylist': True,
        'no_warnings': True,
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
        ydl_opts.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
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
        await bot.edit_message_text(text=get_text(uid, 'uploading'), chat_id=callback.message.chat.id, message_id=status_msg.message_id)
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

# --- RENDER ÜÇÜN OYAQ SAXLA (WEB SERVER) ---
async def handle_web(request):
    return web.Response(text="Bot is running!")

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    await start_web() # Veb serveri başlat
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
