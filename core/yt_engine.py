import os
import glob
import subprocess
import yt_dlp

from core.utils import (
    get_cookie_opts, clean_vtt, get_media_duration_sec, build_ffmpeg_cmd, run_exporters,
    log_task, update_task_analytics
)
from core.whisper_engine import transcribe_with_api

AUTO_DELETE_TEMP_MEDIA = True

def fetch_yt_playlist_info(url):
    opts = {'extract_flat': 'in_playlist', 'quiet': True, 'extractor_args': {'youtube': ['player_client=android,web']}}
    opts.update(get_cookie_opts())
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info['entries'] if 'entries' in info else [info]
    title = info.get('title', 'YouTube Job')
    return title, entries

def run_youtube_pipeline(task):
    selected_entries = task.data['entries']
    full_output_path = task.data['output_path']
    append_mode = task.data['append']
    config = task.data['config']

    total_videos = len(selected_entries)
    log_task(task, f"\nStarting YouTube Queue: {total_videos} video(s)...")

    mode = 'a' if append_mode else 'w'
    cookie_opts = get_cookie_opts()
    task.data["key_state"] = {"index": 0}
    out_dir = os.path.dirname(full_output_path)

    try:
        with open(full_output_path, mode, encoding='utf-8') as master:
            if not append_mode:
                master.write(f"Source: {task.name}\n{'='*60}\n\n")

            for index, entry in enumerate(selected_entries, start=1):
                task.check_state()
                video_url, title = entry.get('url'), entry.get('title', f'Video_{index}')
                log_task(task, f"[{index}/{total_videos}] Processing: {title}")
                master.write(f"\n\n--- {title} ---\n\n")

                base_progress = (index - 1) / total_videos
                video_sec = 0
                generated_text = ""

                def ytdl_progress_hook(d):
                    task.check_state()
                    if d['status'] == 'downloading':
                        try:
                            p = d.get('downloaded_bytes', 0) / d.get('total_bytes', 1)
                            task.update_progress(base_progress + (p * 0.33 / total_videos))
                        except Exception:
                            pass

                try:
                    ydl_opts_info = {'quiet': True, 'socket_timeout': 60, 'extractor_args': {'youtube': ['player_client=android,web']}}
                    ydl_opts_info.update(cookie_opts)

                    with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                        info = ydl.extract_info(video_url, download=False)
                    video_sec = info.get('duration', 0)
                    subs, auto_subs = info.get('subtitles', {}), info.get('automatic_captions', {})

                    if 'ar' in subs or 'ar' in auto_subs:
                        vtt_opts = {'skip_download': True, 'writesubtitles': True, 'writeautomaticsub': True, 'subtitleslangs': ['ar'], 'subtitlesformat': 'vtt', 'outtmpl': 'temp_sub.%(ext)s', 'quiet': True, 'progress_hooks': [ytdl_progress_hook]}
                        vtt_opts.update(cookie_opts)
                        with yt_dlp.YoutubeDL(vtt_opts) as ydl_vtt:
                            ydl_vtt.download([video_url])

                        vtt_files = glob.glob('temp_sub*.vtt')
                        if vtt_files:
                            generated_text = clean_vtt(vtt_files[0])
                            master.write(generated_text + "\n")
                            os.remove(vtt_files[0])
                    else:
                        mp4_filename = "temp_video.mp4"
                        dl_opts = {'format': 'bestaudio/best/worst', 'outtmpl': mp4_filename, 'quiet': True, 'progress_hooks': [ytdl_progress_hook]}
                        dl_opts.update(cookie_opts)
                        with yt_dlp.YoutubeDL(dl_opts) as ydl_dl:
                            ydl_dl.download([video_url])

                        if not video_sec:
                            video_sec = get_media_duration_sec(mp4_filename)
                        task.update_progress(base_progress + (0.35 / total_videos))
                        subprocess.run(build_ffmpeg_cmd(mp4_filename, config), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000 if os.name == 'nt' else 0)

                        task.update_progress(base_progress + (0.40 / total_videos))
                        chunks = sorted(glob.glob("chunk_*.mp3"))
                        full_transcription = []

                        for c_idx, chunk in enumerate(chunks):
                            task.check_state()
                            text = transcribe_with_api(chunk, task, c_idx, out_dir, full_output_path)
                            if text:
                                full_transcription.append(text)
                            os.remove(chunk)
                            chunk_prog = ((c_idx + 1) / len(chunks)) * 0.60
                            task.update_progress(base_progress + ((0.40 + chunk_prog) / total_videos))

                        generated_text = " ".join(full_transcription)
                        master.write(generated_text + "\n")
                        if AUTO_DELETE_TEMP_MEDIA and os.path.exists(mp4_filename):
                            os.remove(mp4_filename)
                except Exception as e:
                    if "Cancelled" in str(e):
                        raise e
                    master.write("\n[!] Failed to process.\n")

                words = len(generated_text.split()) if generated_text else 0
                update_task_analytics(task, yt_count=1, yt_sec=video_sec, words=words)
                task.update_progress(index / total_videos)

        log_task(task, "\n[SUCCESS] YouTube task complete!")
        run_exporters(full_output_path, config.get('export_docx', False), config.get('export_md', False), lambda msg: log_task(task, msg))
    except Exception as e:
        if "Cancelled" in str(e):
            raise e
        raise e
