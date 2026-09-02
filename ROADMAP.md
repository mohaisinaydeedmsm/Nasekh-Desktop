# Thafreeg v2.0 Master Development Roadmap

## Batch 1: Core Engine & Pipeline Hardening
- Feature 1: Storage Management & Output Formatting (auto-increment filenames like Thafreeg_1.txt, auto-delete temp downloaded media toggle).
- Feature 2: Auto-SRT & VTT Subtitle Generator (convert API timestamps to .srt and .vtt files).
- Feature 3: Target Language Override (pass language code parameter to API to force language).
- Feature 4: Custom Vocabulary Injector (append custom glossary/terms into the API prompt).
- Feature 5: Multi-Provider API Failover (try/except fallback with key rotation on 429 rate limits).

## Batch 2: Advanced Media Handling
- Feature 6: Direct URL Media Downloader (yt-dlp support for direct audio links & Archive.org).
- Feature 7: FFmpeg Audio Pre-Enhancer (local CPU noise reduction `afftdn` with save cleaned audio option).
- Feature 8: OCR Document Processing (Groq Vision API integration for PDF/JPG/PNG).
- Feature 9: Universal Drag-and-Drop Drop Zone.
- Feature 10: Multi-Format Professional Exporter (.docx and .md exporters).

## Batch 3: UI Overhaul & UX Modernization
- Feature 11: Google Drive Aesthetic Overhaul (CustomTkinter sidebar navigation).
- Feature 12: Bilingual UI & RTL Flip (English/Arabic live toggle).
- Feature 13: API & Account Safety Dashboards (visual rate limits and Telegram safety meters).
- Feature 14: Interactive "Click-to-Play" Transcript Viewer (built-in audio player text sync).

## Batch 4: Enterprise Features
- Feature 15: Global Project Queuing & Pause/Resume.
- Feature 16: Telegram "Live Channel Watcher" (Telethon passive event handler).
- Feature 17: Lifetime Analytics & Global Archive Search (SQLite database).
- Feature 18: One-Click AI Summarizer & Dual-Column Translation (BYOK LLM features).
- Feature 19: Windows Taskbar Integration & Professional Setup (Inno Setup installer).