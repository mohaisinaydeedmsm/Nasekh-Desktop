import os
import re
import glob
import asyncio
import subprocess

from telethon import TelegramClient
from telethon.errors import (
    PhoneNumberInvalidError,
    ApiIdInvalidError,
    FloodWaitError,
    PhoneNumberBannedError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    RPCError
)
from FastTelethonhelper import fast_download

from core.utils import get_media_duration_sec, build_ffmpeg_cmd, run_exporters, log_task, update_task_analytics
from core.whisper_engine import transcribe_with_api

AUTO_DELETE_TEMP_MEDIA = True

def sanitize_phone_number(phone: str) -> str:
    """Sanitizes phone number input: strips spaces, dashes, parentheses and enforces leading '+'."""
    if not phone:
        return ""
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    if cleaned and not cleaned.startswith('+'):
        cleaned = '+' + cleaned
    return cleaned

def request_telegram_otp(tg_id, tg_hash, phone_number, session_name='my_telegram_session'):
    """Requests OTP code from Telegram servers with sanitization & detailed Telethon exception handling."""
    phone_clean = sanitize_phone_number(phone_number)
    if not phone_clean or len(phone_clean) < 6:
        raise ValueError(f"Invalid phone number format: '{phone_number}'. Must include country code e.g. +966500000000.")

    try:
        tg_id_int = int(tg_id)
    except Exception:
        raise ValueError(f"Invalid API ID format: '{tg_id}'. API ID must be a numeric integer.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = None
    try:
        async def _req():
            nonlocal client
            client = TelegramClient(session_name, tg_id_int, tg_hash)
            await client.connect()
            sent_code = await client.send_code_request(phone_clean)
            return sent_code.phone_code_hash

        return loop.run_until_complete(_req())
    except PhoneNumberInvalidError:
        raise ValueError(f"Invalid Phone Number: '{phone_clean}'. Please ensure the correct country code is included.")
    except ApiIdInvalidError:
        raise ValueError("Invalid Telegram API ID or API Hash. Please verify your credentials at my.telegram.org.")
    except FloodWaitError as e:
        raise ValueError(f"Telegram API Rate Limit Exceeded: Please wait {e.seconds} seconds before requesting a code again.")
    except PhoneNumberBannedError:
        raise ValueError(f"This phone number ({phone_clean}) has been banned from Telegram.")
    except RPCError as e:
        raise ValueError(f"Telegram API Error ({e.code}): {e.message}")
    except Exception as e:
        raise ValueError(f"Telegram Request Failed: {e}")
    finally:
        if client:
            try:
                loop.run_until_complete(client.disconnect())
            except Exception:
                pass
        loop.close()

def complete_telegram_otp(tg_id, tg_hash, phone_number, phone_code_hash, code, session_name='my_telegram_session'):
    """Completes sign-in with received OTP code and persists session file."""
    phone_clean = sanitize_phone_number(phone_number)

    try:
        tg_id_int = int(tg_id)
    except Exception:
        raise ValueError(f"Invalid API ID format: '{tg_id}'. API ID must be numeric.")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = None
    try:
        async def _login():
            nonlocal client
            client = TelegramClient(session_name, tg_id_int, tg_hash)
            await client.connect()
            user = await client.sign_in(phone=phone_clean, code=code, phone_code_hash=phone_code_hash)
            return user.id if user else None

        return loop.run_until_complete(_login())
    except PhoneCodeInvalidError:
        raise ValueError("Invalid verification code. Please check your Telegram app for the code from 'Telegram'.")
    except PhoneCodeExpiredError:
        raise ValueError("Verification code expired. Please click 'Send Telegram OTP' to request a new code.")
    except RPCError as e:
        raise ValueError(f"Telegram Sign-In Error ({e.code}): {e.message}")
    except Exception as e:
        raise ValueError(f"Telegram Sign-In Failed: {e}")
    finally:
        if client:
            try:
                loop.run_until_complete(client.disconnect())
            except Exception:
                pass
        loop.close()

def run_telegram_pipeline(task):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_telegram_async(task))
    finally:
        loop.close()

async def process_telegram_async(task):
    start_link, end_link = task.data['start'], task.data['end']
    tg_api_id, tg_api_hash = task.data['tg_id'], task.data['tg_hash']
    full_output_path = task.data['output_path']
    append_mode = task.data['append']
    config = task.data['config']

    log_task(task, "\nConnecting to Telegram...")
    client = TelegramClient('my_telegram_session', int(tg_api_id), tg_api_hash)
    try:
        await client.start()
        mode = 'a' if append_mode else 'w'
        out_dir = os.path.dirname(full_output_path)
        task.data["key_state"] = {"index": 0}

        start_id = int(start_link.split("t.me/")[1].split("/")[1].split("?")[0])
        end_id = int(end_link.split("t.me/")[1].split("/")[1].split("?")[0])
        channel = start_link.split("t.me/")[1].split("/")[0]
        if start_id > end_id:
            start_id, end_id = end_id, start_id

        total_posts = (end_id - start_id) + 1
        os.makedirs("./downloads", exist_ok=True)

        with open(full_output_path, mode, encoding='utf-8') as master:
            for current_idx, msg_id in enumerate(range(start_id, end_id + 1), start=1):
                await task.async_check_state()
                base_progress = (current_idx - 1) / total_posts

                message = await client.get_messages(channel, ids=msg_id)
                if message and (message.document or message.video or message.audio):
                    log_task(task, f"    ⬇️ Downloading Post {msg_id}...")
                    before = set(os.listdir('./downloads/'))
                    await fast_download(client, message, download_folder='./downloads/')
                    new_files = list(set(os.listdir('./downloads/')) - before)

                    if new_files:
                        task.update_progress(base_progress + (0.4 / total_posts))
                        dl_file = os.path.join('./downloads/', new_files[0])
                        duration_sec = get_media_duration_sec(dl_file)
                        master.write(f"\n\n--- Telegram Post {msg_id} ---\n\n")
                        subprocess.run(build_ffmpeg_cmd(dl_file, config), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)

                        task.update_progress(base_progress + (0.5 / total_posts))
                        chunks = sorted(glob.glob("chunk_*.mp3"))
                        full_transcription = []
                        for idx, chunk in enumerate(chunks):
                            await task.async_check_state()
                            text = transcribe_with_api(chunk, task, idx, out_dir, full_output_path)
                            if text:
                                full_transcription.append(text)
                            os.remove(chunk)
                            chunk_prog = ((idx + 1) / len(chunks)) * 0.50
                            task.update_progress(base_progress + ((0.50 + chunk_prog) / total_posts))

                        res_text = " ".join(full_transcription)
                        master.write(res_text + "\n")
                        if AUTO_DELETE_TEMP_MEDIA and os.path.exists(dl_file):
                            os.remove(dl_file)
                        words = len(res_text.split())
                        update_task_analytics(task, tg_count=1, tg_sec=duration_sec, words=words)
                task.update_progress(current_idx / total_posts)

        log_task(task, "\n🎉 Telegram harvest complete!")
        run_exporters(full_output_path, config.get('export_docx', False), config.get('export_md', False), lambda msg: log_task(task, msg))
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
