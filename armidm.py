#!/usr/bin/env python3
"""
ArmIDM - Open Source Internet Download Manager Clone (Python Desktop App)
========================================================================
Fitur Lengkap ala IDM (Tanpa Lisensi / 100% Gratis):
1. Multi-Connection Dynamic Segmented Downloading (1 - 32 koneksi paralel via HTTP Range)
2. Pause & Resume kapan saja (menyimpan state segmen & metadata di ~/.armidm/downloads.json)
3. Speed Limiter (Token Bucket Algorithm) - Global maupun Per-Unduhan secara real-time
4. Local HTTP REST + WebSocket Server (127.0.0.1:16888) untuk integrasi Chrome Extension
5. Video & Media Sniffer (Menerima stream video dari Chrome Extension + mendukung MP4/WEBM/MKV & HLS .m3u8)
6. Layout Klasik IDM:
   - Menu Bar & Toolbar Ikon Lengkap
   - Panel Kiri: TreeView Kategori Otomatis (Compressed, Documents, Music, Programs, Video, General) & Antrean
   - Tabel Utama: File Name, Size, Status, Time Left, Transfer Rate, Connections, Category, Added Date
   - Dialog "Download File Info" (Pop-up otomatis saat ekstensi menangkap unduhan/video)
   - Jendela "Download Progress" ala IDM (3 Tab: Download Status dengan visualisasi bar segmen biru, Speed Limiter, Options on Completion)
   - Jendela "Video Sniffer / Grabbed Videos" & "Scheduler / Queue Manager"
"""
import base64
import datetime
import hashlib
import http.server
import json
import os
import pathlib
import queue
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

# ============================================================================
# KONFIGURASI & UTILITAS UMUM
# ============================================================================
APP_NAME = "ArmIDM - Modern Download Manager"
APP_VERSION = "3.0.0"
THEMES = {
    "dark": {
        "bg_root": "#0F172A",
        "bg_panel": "#1E293B",
        "bg_card": "#1E293B",
        "bg_header": "#0B1120",
        "bg_input": "#0F172A",
        "fg_primary": "#F8FAFC",
        "fg_secondary": "#94A3B8",
        "fg_muted": "#64748B",
        "border": "#334155",
        "accent": "#3B82F6",
        "accent_hover": "#2563EB",
        "success": "#10B981",
        "success_hover": "#059669",
        "warning": "#F59E0B",
        "danger": "#EF4444",
        "purple": "#8B5CF6",
        "tree_bg": "#1E293B",
        "tree_alt": "#172033",
        "tree_fg": "#F1F5F9",
        "tree_sel_bg": "#2563EB",
        "tree_sel_fg": "#FFFFFF",
        "tree_head_bg": "#0F172A",
        "tree_head_fg": "#94A3B8",
        "row_downloading": "#38BDF8",
        "row_complete": "#4ADE80",
        "row_paused": "#FBBF24",
        "row_error": "#F87171",
        "seg_bg": "#0F172A",
        "seg_empty": "#334155",
        "seg_fill": "#3B82F6",
    },
    "light": {
        "bg_root": "#F1F5F9",
        "bg_panel": "#FFFFFF",
        "bg_card": "#FFFFFF",
        "bg_header": "#0F172A",
        "bg_input": "#FFFFFF",
        "fg_primary": "#0F172A",
        "fg_secondary": "#475569",
        "fg_muted": "#64748B",
        "border": "#CBD5E1",
        "accent": "#2563EB",
        "accent_hover": "#1D4ED8",
        "success": "#16A34A",
        "success_hover": "#15803D",
        "warning": "#D97706",
        "danger": "#DC2626",
        "purple": "#7C3AED",
        "tree_bg": "#FFFFFF",
        "tree_alt": "#F8FAFC",
        "tree_fg": "#0F172A",
        "tree_sel_bg": "#2563EB",
        "tree_sel_fg": "#FFFFFF",
        "tree_head_bg": "#E2E8F0",
        "tree_head_fg": "#1E293B",
        "row_downloading": "#0284C7",
        "row_complete": "#16A34A",
        "row_paused": "#D97706",
        "row_error": "#DC2626",
        "seg_bg": "#E2E8F0",
        "seg_empty": "#CBD5E1",
        "seg_fill": "#2563EB",
    },
}
CAT_ICONS = {
    "Compressed": "🗜",
    "Documents": "📄",
    "Music": "🎵",
    "Programs": "⚙",
    "Video": "🎬",
    "General": "📦",
}

def apply_win32_titlebar_theme(win, is_dark: bool = True):
    """Mengaktifkan Dark/Light Title Bar native pada Windows 10/11 menggunakan DWM API."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        val = ctypes.c_int(1 if is_dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (dan fallback 19 untuk Windows 10 lama)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass
DEFAULT_PORT = 16888
DATA_DIR = pathlib.Path.home() / ".armidm"
TEMP_DIR = DATA_DIR / "temp_segments"
DEFAULT_DOWNLOAD_DIR = pathlib.Path.home() / "Downloads" / "ArmIDM"
STATE_FILE = DATA_DIR / "downloads_state.json"
CONFIG_FILE = DATA_DIR / "config.json"
CATEGORY_MAP = {
    "Compressed": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"},
    "Documents": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".epub", ".md"},
    "Music": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".wma", ".opus"},
    "Programs": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".iso", ".bin", ".sh", ".bat"},
    "Video": {".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".m3u8", ".mpd"},
}
CATEGORY_FOLDERS = {
    "Compressed": "Compressed",
    "Documents": "Documents",
    "Music": "Music",
    "Programs": "Programs",
    "Video": "Video",
    "General": "General",
}

def detect_category(filename: str, mime_type: str = "") -> str:
    ext = pathlib.Path(filename).suffix.lower()
    for cat, exts in CATEGORY_MAP.items():
        if ext in exts:
            return cat
    mime_lower = (mime_type or "").lower()
    if mime_lower.startswith("video/") or "mpegurl" in mime_lower or "dash+xml" in mime_lower:
        return "Video"
    if mime_lower.startswith("audio/"):
        return "Music"
    if "pdf" in mime_lower or "word" in mime_lower or "excel" in mime_lower:
        return "Documents"
    if "zip" in mime_lower or "compressed" in mime_lower or "tar" in mime_lower:
        return "Compressed"
    return "General"

def format_size(num_bytes: float) -> str:
    if num_bytes is None or num_bytes < 0:
        return "Unknown"
    if num_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    val = float(num_bytes)
    while val >= 1024.0 and idx < len(units) - 1:
        val /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(val)} B"
    return f"{val:.2f} {units[idx]}"

def format_speed(bytes_per_sec: float) -> str:
    if bytes_per_sec <= 0:
        return "0 KB/s"
    return f"{format_size(bytes_per_sec)}/s"

def format_eta(seconds: float) -> str:
    if seconds is None or seconds < 0 or seconds == float("inf"):
        return "Unknown"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} sec"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {sec} sec"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hr {minutes} min"

def sanitize_filename(name: str) -> str:
    name = urllib.parse.unquote(name or "download_file")
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return name or "download_file"

def launch_file_default(filepath: pathlib.Path):
    if not filepath.exists():
        return
    if sys.platform.startswith("win"):
        os.startfile(str(filepath))
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(filepath)])
    else:
        subprocess.Popen(["xdg-open", str(filepath)])

def launch_open_with(filepath: pathlib.Path):
    if not filepath.exists():
        return
    if sys.platform.startswith("win"):
        subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", os.path.normpath(str(filepath))])
    else:
        launch_file_default(filepath)

def launch_open_folder_select(filepath: pathlib.Path, fallback_dir: str = ""):
    """
    Membuka Windows Explorer tepat di direktori tempat file disimpan dan langsung menyorot (highlight)
    file tersebut menggunakan Win32 API SHOpenFolderAndSelectItems / raw command explorer.exe.
    """
    try:
        resolved_file = filepath.resolve() if filepath else None
    except Exception:
        resolved_file = filepath
    target_dir = ""
    if fallback_dir:
        try:
            target_dir = os.path.abspath(fallback_dir)
        except Exception:
            target_dir = fallback_dir
    if not target_dir and resolved_file:
        target_dir = os.path.abspath(str(resolved_file.parent))
    if sys.platform.startswith("win"):
        # Jika file belum ada dengan nama persis (misal ekstensi bertambah .mp4), cari file yang cocok di folder
        if resolved_file and not resolved_file.exists() and target_dir and os.path.isdir(target_dir):
            stem = resolved_file.stem
            candidates = list(pathlib.Path(target_dir).glob(f"{stem}*"))
            if candidates:
                resolved_file = candidates[0].resolve()
        if resolved_file and resolved_file.exists():
            norm_file = os.path.normpath(str(resolved_file))
            # Metode 1: Win32 Shell32 SHOpenFolderAndSelectItems (paling akurat, bebas masalah spasi/karakter khusus)
            try:
                import ctypes
                shell32 = ctypes.windll.shell32
                ole32 = ctypes.windll.ole32
                ole32.CoInitialize(None)
                shell32.ILCreateFromPathW.argtypes = [ctypes.c_wchar_p]
                shell32.ILCreateFromPathW.restype = ctypes.c_void_p
                shell32.SHOpenFolderAndSelectItems.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_uint,
                    ctypes.c_void_p,
                    ctypes.c_ulong,
                ]
                shell32.ILFree.argtypes = [ctypes.c_void_p]
                pidl = shell32.ILCreateFromPathW(norm_file)
                if pidl:
                    res = shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0)
                    shell32.ILFree(pidl)
                    if res == 0:
                        return
            except Exception:
                pass
            # Metode 2: Raw string command ke explorer.exe (tanpa list2cmdline agar /select, tidak terbungkus tanda kutip)
            try:
                subprocess.Popen(f'explorer.exe /select,"{norm_file}"')
                return
            except Exception:
                pass
        if target_dir and os.path.isdir(target_dir):
            os.startfile(os.path.normpath(target_dir))
    elif sys.platform == "darwin":
        if resolved_file and resolved_file.exists():
            subprocess.Popen(["open", "-R", str(resolved_file)])
        elif target_dir:
            subprocess.Popen(["open", target_dir])
    else:
        if target_dir:
            subprocess.Popen(["xdg-open", target_dir])

def create_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

BINARY_FILE_EXTENSIONS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz",
    ".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".iso", ".bin",
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".m4v",
    ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
    ".pdf", ".docx", ".xlsx", ".pptx", ".nsp", ".xci", ".nsz",
}

class PreserveHeadersRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Mempertahankan header Cookie, Referer, dan Authorization saat terjadi HTTP 301/302/307/308 Redirect."""
    def __init__(self, preserved_headers: dict = None):
        super().__init__()
        self.preserved_headers = preserved_headers or {}
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is not None:
            for k, v in self.preserved_headers.items():
                if k and v:
                    new_req.add_unredirected_header(k, v)
        return new_req

def open_url_with_headers(req: urllib.request.Request, headers: dict, timeout: int = 20):
    ctx = create_ssl_context()
    for k, v in (headers or {}).items():
        if k and v:
            req.add_unredirected_header(k, v)
    opener = urllib.request.build_opener(
        PreserveHeadersRedirectHandler(headers),
        urllib.request.HTTPSHandler(context=ctx),
    )
    return opener.open(req, timeout=timeout)

YTDLP_DOMAINS = (
    "youtube.com/",
    "youtu.be/",
    "tiktok.com/",
    "instagram.com/reel",
    "instagram.com/p/",
    "facebook.com/watch",
    "fb.watch/",
    "twitter.com/",
    "x.com/",
    "twitch.tv/",
    "vimeo.com/",
    "dailymotion.com/",
    "bilibili.com/",
)

def is_ytdlp_supported_url(url: str) -> bool:
    u = (url or "").lower()
    return any(d in u for d in YTDLP_DOMAINS)

class YouTubeAndSocialEngine:
    """
    Mesin pengunduh khusus untuk YouTube, TikTok, Instagram, X/Twitter, dan Facebook:
    - Mengambil judul asli video YouTube secara instan melalui API oEmbed resmi YouTube.
    - Menjalankan unduhan menggunakan `yt-dlp` (baik pustaka Python `yt_dlp`, perintah sistem,
      maupun mengunduh biner mandiri resmi `yt-dlp.exe` ke `~/.armidm/bin/yt-dlp.exe` secara otomatis
      pada penggunaan pertama di Windows).
    - Mendukung pemilihan resolusi (1080p, 720p, 480p, 360p, Audio Only), Speed Limiter, Pause/Resume,
      dan pembacaan Cookie dari ekstensi browser.
    """
    BIN_DIR = DATA_DIR / "bin"
    YTDLP_EXE = BIN_DIR / ("yt-dlp.exe" if sys.platform.startswith("win") else "yt-dlp")
    _download_lock = threading.Lock()
    @classmethod
    def extract_quality_tag(cls, url: str) -> tuple[str, str]:
        if "#pyidm_quality=" in url:
            base, q = url.split("#pyidm_quality=", 1)
            return base, q.strip().lower()
        return url, "720p"
    @classmethod
    def probe_video_info(cls, url: str, headers: dict = None) -> dict:
        clean_url, quality = cls.extract_quality_tag(url)
        ext = "m4a" if quality == "audio" else "mp4"
        title = "YouTube_Video"
        ctx = create_ssl_context()
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(clean_url, safe='')}&format=json"
            if "tiktok.com" in clean_url.lower():
                oembed_url = f"https://www.tiktok.com/oembed?url={urllib.parse.quote(clean_url, safe='')}"
            req = urllib.request.Request(
                oembed_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if data.get("title"):
                    title = sanitize_filename(data["title"])[:80]
        except Exception:
            try:
                req = urllib.request.Request(
                    clean_url,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                    html_chunk = resp.read(65536).decode("utf-8", errors="ignore")
                    m = re.search(r"<title[^>]*>([^<]+)</title>", html_chunk, re.IGNORECASE)
                    if m:
                        raw_t = m.group(1).replace("- YouTube", "").strip()
                        if raw_t:
                            title = sanitize_filename(raw_t)[:80]
            except Exception:
                pass
        filename = f"{title} [{quality}].{ext}" if quality else f"{title}.{ext}"
        return {
            "url": url,
            "filename": sanitize_filename(filename),
            "total_size": -1,
            "resumable": True,
            "mime_type": "audio/mp4" if ext == "m4a" else "video/mp4",
            "is_hls": False,
            "category": "Music" if ext == "m4a" else "Video",
            "headers": headers or {},
            "is_html_trap": False,
        }
    @classmethod
    def ensure_ytdlp_binary(cls, task: "DownloadTask") -> str:
        sys_bin = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
        if sys_bin:
            return sys_bin
        if cls.YTDLP_EXE.exists() and cls.YTDLP_EXE.stat().st_size > 1024 * 1024:
            return str(cls.YTDLP_EXE)
        with cls._download_lock:
            if cls.YTDLP_EXE.exists() and cls.YTDLP_EXE.stat().st_size > 1024 * 1024:
                return str(cls.YTDLP_EXE)
            cls.BIN_DIR.mkdir(parents=True, exist_ok=True)
            task.status = "Menyiapkan modul YouTube (yt-dlp)..."
            dl_url = (
                "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
                if sys.platform.startswith("win")
                else "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
            )
            ctx = create_ssl_context()
            req = urllib.request.Request(dl_url, headers={"User-Agent": "Mozilla/5.0 ArmIDM/2.8"})
            temp_bin = cls.BIN_DIR / (cls.YTDLP_EXE.name + ".part")
            with urllib.request.urlopen(req, timeout=45, context=ctx) as resp, open(temp_bin, "wb") as out_f:
                shutil.copyfileobj(resp, out_f, length=256 * 1024)
            temp_bin.replace(cls.YTDLP_EXE)
            if not sys.platform.startswith("win"):
                cls.YTDLP_EXE.chmod(0o755)
            return str(cls.YTDLP_EXE)
    @classmethod
    def _write_netscape_cookies_file(cls, cookie_header: str, url: str, target_file: pathlib.Path) -> bool:
        """Mengonversi header Cookie dari ekstensi browser menjadi file cookies.txt format Netscape untuk yt-dlp."""
        if not cookie_header or "=" not in cookie_header:
            return False
        try:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "youtube.com").lower()
            parts = host.split(".")
            base_domain = "." + ".".join(parts[-2:]) if len(parts) >= 2 else "." + host
            lines = [
                "# Netscape HTTP Cookie File",
                "# https://curl.haxx.se/rfc/cookie_spec.html",
                "# This is a generated file! Do not edit.",
                "",
            ]
            count = 0
            for pair in cookie_header.split(";"):
                pair = pair.strip()
                if "=" not in pair:
                    continue
                k, v = pair.split("=", 1)
                k, v = k.strip(), v.strip()
                if not k:
                    continue
                lines.append(f"{base_domain}\tTRUE\t/\tTRUE\t2147483647\t{k}\t{v}")
                if "youtube.com" in base_domain:
                    lines.append(f".googlevideo.com\tTRUE\t/\tTRUE\t2147483647\t{k}\t{v}")
                count += 1
            if count == 0:
                return False
            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
        except Exception:
            return False
    @classmethod
    def download_video(cls, core: "DownloadManagerCore", task: "DownloadTask"):
        clean_url, quality = cls.extract_quality_tag(task.url)
        ytdlp_bin = cls.ensure_ytdlp_binary(task)
        is_youtube = "youtube.com" in clean_url.lower() or "youtu.be" in clean_url.lower()
        task.segments = [SegmentInfo(index=0, start_byte=0, end_byte=100, downloaded=0, status="Connecting")]
        task.status = "Connecting to YouTube..."
        res_map = {"1080p": "1080", "720p": "720", "480p": "480", "360p": "360"}
        res_num = res_map.get(quality, "720")
        # Gunakan template output dengan %(ext)s agar yt-dlp dapat menulis ekstensi yang sesuai tanpa konflik
        base_stem = task.target_path.stem.replace("%", "_")
        out_template = str(pathlib.Path(task.save_dir) / f"{base_stem}.%(ext)s")
        cookie_file = task.temp_folder / "browser_cookies.txt"
        has_cookie_file = cls._write_netscape_cookies_file(
            task.headers.get("Cookie") or task.headers.get("cookie") or "",
            clean_url,
            cookie_file,
        )
        # Strategi multi-percobaan (Tanpa filter [acodec!=none] yang kaku agar tidak pernah gagal "Requested format is not available")
        if quality == "audio":
            base_fmt_args = ["-f", "ba[ext=m4a]/ba/b", "-S", "ext:m4a:mp3"]
        else:
            # Dengan hanya memakai -S (Format Sort) dan membiarkan -f otomatis (atau b/bv*+ba),
            # yt-dlp otomatis memakai single-file MP4 jika FFmpeg belum ada, atau menggabungkan HD jika FFmpeg ada!
            base_fmt_args = ["-S", f"res:{res_num},ext:mp4:m4a"]
        attempts = [
            # Attempt 1: Default yt-dlp client (tanpa override UA dan tanpa cookies agar kecepatan maksimal)
            {"use_cookies": False, "extra": base_fmt_args},
            # Attempt 2: Client Android VR / iOS / TV (bebas bot-check & bebas po_token)
            {
                "use_cookies": False,
                "extra": base_fmt_args + (["--extractor-args", "youtube:player_client=android_vr,ios,tv,mweb"] if is_youtube else []),
            },
        ]
        if has_cookie_file:
            # Attempt 3: Menggunakan Cookie sesi dari ekstensi browser (untuk video age-restricted / private)
            attempts.append({"use_cookies": True, "extra": base_fmt_args})
        prog_re = re.compile(
            r"\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+~?\s*(\d+(?:\.\d+)?)([KMGTP]?i?B)(?:\s+at\s+(\d+(?:\.\d+)?)([KMGTP]?i?B)/s)?",
            re.IGNORECASE,
        )
        def unit_to_bytes(val_str: str, unit_str: str) -> int:
            val = float(val_str)
            u = unit_str.upper()
            if u.startswith("K"):
                return int(val * 1024)
            if u.startswith("M"):
                return int(val * 1024 * 1024)
            if u.startswith("G"):
                return int(val * 1024 * 1024 * 1024)
            return int(val)
        def find_downloaded_file() -> pathlib.Path:
            if task.target_path.exists() and task.target_path.stat().st_size > 0:
                return task.target_path
            candidates = [
                p for p in pathlib.Path(task.save_dir).glob(f"{base_stem}.*")
                if not p.name.endswith(".part") and not p.name.endswith(".ytdl") and p.stat().st_size > 0
            ]
            if candidates:
                return max(candidates, key=lambda p: p.stat().st_mtime)
            return None
        last_error_line = ""
        creationflags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
        for attempt_idx, cfg in enumerate(attempts):
            if task._stop_event.is_set():
                return
            cmd = [
                ytdlp_bin,
                "--no-playlist",
                "--continue",
                "--no-part",
                "--newline",
                "--no-check-certificates",
                "--no-mtime",
                "-o",
                out_template,
            ]
            cmd.extend(cfg["extra"])
            if cfg["use_cookies"] and cookie_file.exists():
                cmd.extend(["--cookies", str(cookie_file)])
            # Jangan kirim --user-agent Desktop ke YouTube karena akan ditolak oleh endpoint Android/iOS YouTube
            if not is_youtube:
                ua = task.headers.get("User-Agent")
                if ua:
                    cmd.extend(["--user-agent", ua])
                ref = task.headers.get("Referer") or task.headers.get("referer")
                if ref:
                    cmd.extend(["--referer", ref])
            if core.config.get("speed_limit_enabled"):
                kbps = max(10, int(core.config.get("speed_limit_kbps", 1024)))
                cmd.extend(["--limit-rate", f"{kbps}K"])
            elif task.task_limiter.enabled:
                kbps = max(10, int(task.task_limiter.rate_kbps))
                cmd.extend(["--limit-rate", f"{kbps}K"])
            cmd.append(clean_url)
            task.status = "Downloading"
            task.segments[0].status = "Downloading"
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creationflags,
            )
            for line in proc.stdout:
                if task._stop_event.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except Exception:
                        proc.kill()
                    task.status = "Paused"
                    task.segments[0].status = "Paused"
                    task.transfer_rate = 0.0
                    core.save_state()
                    return
                line_str = line.strip()
                if "ERROR:" in line_str:
                    last_error_line = line_str.split("ERROR:", 1)[-1].strip()
                m = prog_re.search(line_str)
                if m:
                    pct = float(m.group(1))
                    total_b = unit_to_bytes(m.group(2), m.group(3))
                    dl_b = int(total_b * (pct / 100.0))
                    task.total_size = total_b
                    task.downloaded_bytes = dl_b
                    task.segments[0].end_byte = max(1, total_b)
                    task.segments[0].downloaded = dl_b
                    task.segments[0].status = f"Downloading ({pct:.1f}%)"
                    if m.group(4) and m.group(5):
                        spd = unit_to_bytes(m.group(4), m.group(5))
                        task.transfer_rate = float(spd)
                        if spd > 0 and total_b > dl_b:
                            task.eta_seconds = (total_b - dl_b) / spd
            ret = proc.wait()
            if task._stop_event.is_set():
                task.status = "Paused"
                task.transfer_rate = 0.0
                core.save_state()
                return
            found_file = find_downloaded_file()
            if ret == 0 and found_file is not None:
                task.filename = found_file.name
                break
            # Jika percobaan pertama gagal, coba jalankan self-update yt-dlp.exe -U
            if attempt_idx == 0:
                try:
                    subprocess.run([ytdlp_bin, "-U"], timeout=20, creationflags=creationflags)
                except Exception:
                    pass
        shutil.rmtree(task.temp_folder, ignore_errors=True)
        final_file = find_downloaded_file()
        if final_file is None:
            err_detail = last_error_line[:130] if last_error_line else "Gagal mengunduh stream video YouTube/Sosmed."
            raise RuntimeError(err_detail)
        task.filename = final_file.name
        task.total_size = final_file.stat().st_size
        task.downloaded_bytes = task.total_size
        task.segments[0].end_byte = task.total_size
        task.segments[0].downloaded = task.total_size
        task.segments[0].status = "Completed"
        task.status = "Complete"
        task.transfer_rate = 0.0
        task.eta_seconds = 0.0
        core.save_state()
        core.notify_event("task_completed", {"task_id": task.id})

class GofileResolver:
    """
    Menangani autentikasi otomatis Gofile.io:
    1. Jika pengguna menempelkan link halaman Gofile (`https://gofile.io/d/<id>`) atau jika
       unduhan `storeX.gofile.io` belum memiliki `Cookie: accountToken=...`, otomatis mengambil
       token akun guest dari API Gofile agar server Gofile memberikan file asli (bukan halaman HTML 3.28 KB).
    """
    _cached_token = None
    _lock = threading.Lock()
    @classmethod
    def get_guest_token(cls) -> str:
        with cls._lock:
            if cls._cached_token:
                return cls._cached_token
            try:
                ctx = create_ssl_context()
                req = urllib.request.Request(
                    "https://api.gofile.io/accounts",
                    data=b"{}",
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",
                        "Content-Type": "application/json",
                        "Origin": "https://gofile.io",
                        "Referer": "https://gofile.io/",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                    if payload.get("status") == "ok":
                        cls._cached_token = payload.get("data", {}).get("token", "")
                        return cls._cached_token
            except Exception:
                pass
            return ""
    @classmethod
    def ensure_gofile_headers(cls, url: str, headers: dict) -> tuple[str, dict]:
        hdrs = dict(headers or {})
        lower_url = (url or "").lower()
        if "gofile.io" not in lower_url:
            return url, hdrs
        # Pastikan Referer selalu mengarah ke https://gofile.io/
        if not hdrs.get("Referer") and not hdrs.get("referer"):
            hdrs["Referer"] = "https://gofile.io/"
        cookie_val = hdrs.get("Cookie") or hdrs.get("cookie") or ""
        if "accountToken=" not in cookie_val:
            token = cls.get_guest_token()
            if token:
                hdrs["Cookie"] = f"{cookie_val}; accountToken={token}".strip("; ")
        # Jika URL yang dimasukkan adalah halaman folder Gofile (https://gofile.io/d/<code_id>),
        # coba resolusi menjadi direct download link melalui API Gofile
        m = re.search(r"gofile\.io/d/([a-zA-Z0-9]+)", url)
        if m:
            content_id = m.group(1)
            token = cls.get_guest_token()
            if token:
                try:
                    ctx = create_ssl_context()
                    # Ambil websiteToken (wt) dari global.js Gofile
                    wt = "4fd6sg89d7s6"
                    try:
                        req_js = urllib.request.Request(
                            "https://gofile.io/dist/js/global.js",
                            headers={"User-Agent": hdrs.get("User-Agent", "Mozilla/5.0")},
                        )
                        with urllib.request.urlopen(req_js, timeout=8, context=ctx) as r_js:
                            js_txt = r_js.read().decode("utf-8", errors="ignore")
                            m_wt = re.search(r"appdata\.wt\s*=\s*[\"\']([^\"\']+)[\"\']", js_txt)
                            if m_wt:
                                wt = m_wt.group(1)
                    except Exception:
                        pass
                    api_url = f"https://api.gofile.io/contents/{content_id}?wt={wt}"
                    req_api = urllib.request.Request(
                        api_url,
                        headers={
                            "User-Agent": hdrs.get("User-Agent", "Mozilla/5.0"),
                            "Authorization": f"Bearer {token}",
                            "Origin": "https://gofile.io",
                            "Referer": "https://gofile.io/",
                        },
                    )
                    with urllib.request.urlopen(req_api, timeout=10, context=ctx) as r_api:
                        res_json = json.loads(r_api.read().decode("utf-8"))
                        if res_json.get("status") == "ok":
                            children = res_json.get("data", {}).get("children", {})
                            for _, child in children.items():
                                if child.get("type") == "file" and child.get("link"):
                                    url = child["link"]
                                    hdrs["Cookie"] = f"accountToken={token}"
                                    break
                except Exception:
                    pass
        return url, hdrs

def _unused_old_ssl():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

EMBEDDED_ICO_B64 = "AAABAAMAEBAAAAAAIADPAgAANgAAACAgAAAAACAAGgUAAAUDAAAwMAAAAAAgAAUIAAAfCAAAiVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAClklEQVR4nG2STYtURxSGn1NVt29P35keZxwVIR03UTKKSFBESFBCJrrOTxAkKwUh66SVrF0KjiBCJNlIFtkqKDIbN1nET5CQMM7YRjHi9NzbH7er6rjoadsRX6hFnTrnPVVPHQGApoHzEaB+5MJsuyiV0BPel61qPZuT9t0ba3A9jMIyKq59vXjc1aZ/lMTuIQYxRsTI0EOBEKJirGo0L0K+drm4dfIizXPDjOzY4kJlR+Omm50BAkaETj/SLYeNEivUJxyKohhiV+m3nvyU3zz5s3Dw+6S+/ehSuuuzw2jfG1VX9Dzf7N/Kl3u2APD0/x7Xlp6TOoNCFFeh11rtla9aex3FbF0qld2CFw3RGWekUyoL+7dy+kQDgL+e5ly53aKaCKrREgdqa5OZsRP7HCZViAHGzESg6Ad8UADeFANkE1IBVQTj3bhkfCZG3y0Y7xEdEt2QahTHB1Jv8OsVKn4CKwaAjBrleoUoBpLBpvyxgUD0hslGm/mvnvFkxxq/vakDsCwln3+3Qvl8C68ebcOm+hEDBeMi+X8Zn37bYXn3EvdeOkSUahb55PAU9xYbH7AAM3rN+7d4/OsBun/vZK5WZSbJqHSmeXj1EN2XGeICqGyQi2qIqYCxMARkk0AoLQ9/+YLidQppyaNrB1hfreNqA4jyjrtC4sjTTgz+NeKmEY9GrE08Pk/45495qrMd2v/OkGQlGgwQFbFB+32R0q8YVn/oaq9zIXSDxTorVlTFqcuitpfn9MWfu9RNBgWnYkWxDo2p8/na9eLumfuOZtPk509dYuHqdjc1fVbSdGb42YLIEM2guzE4IkQ/6Id85XfD4Aw0zYipAFo9dLFhptJ5CQNVNZtnT6KqnRCJvlXcOfVgFH4LeP8pT0IuhY0AAAAASUVORK5CYIKJUE5HDQoaCgAAAA1JSERSAAAAIAAAACAIBgAAAHN6evQAAAThSURBVHic7ZdNbFRVFMd/59z33gydGWgpYHSByEYTA5rUqDEqNmpkI3HTutBgolET9+qyoIkrV8YNRhYmiknH6ML4hQvUYMJGY4yaIODHQlCLkLYzTOe9d+9x8abAtDOdFsPOk9y57879+P/vPR/3XOgtwtiBuE/f2mXsQMzEtOsNtFQmph31Sb/Y3PjYsfUy/6ddKbaWUpupTzYA2HUk4svxvD+BRfCxZ+Lqll3Pk2f3otFdhDRg6NrhBcMWtFx7M6StI83Dez+HKYX9YTmBDnjloYMPiAy9oHH5QU0UjZQr3j6AGSEF3zjrNUpentvafIU3TnvYZyAWXQ5e3f3W3UL8qRsacq6SZLquoiI9dr5ccR2w3n+HLMs1MRdSt6/6WzbWYP8eQAETMGGiriPnqeZy4UOtjdyTbBpOBUnMAtjyVfPQG01FUF3SJcWPOGd5o5Fl/8wmFtqPNO7c+yH766KMvRFRn/S5az0l5ZF7ompSgIeOHYp0FRFhuBIxUokZrsRddTlxmHWPXzwuy3OJhiqRliLD5+9M/ITAZIjYPhLY/HHJ8r92ayxBy0POgu9MvmwjApk3hocivn7pdqplV+xUwHvDOeG1T35nqv4LWzYk5L6XPkyj9TUf0iz6bP6t+4HDSn3Sb4QShHFNREVkRWsXYMNQRK3sqK1z1MqO4U67HGsvjV3cgZkhSRw0qZS8MQ6FISBJaiDN1Zp77g0zCB0TyRbbq5lvgAUk0ASILutatZ9fVC9L1L0WEdM1gV4t+Z9ANHjIcrHLCku+rwoB8wpqWAALQoRyKcRAhBRtEyx0ii8GiK5MbSABUSOuLBAyh5nhykbDWhAcZoX1+2A4EXKXEq/LcSVFSgED8laMSH8SAwmEXNn64Ek27fiTtJGgCs/9dazL7ToBkfZNgfteDGhkIHD80C3M/boRSXxfHa1KBafevxlXzth441l86mhaioUOql2q1QnxUBGcTkzvZPbkKNG6rLgf+shALxBnhCCcmN5J1ooQZ6g5IlEitKsmd8TVlD++uoG/v72OqLIy+KoIYOBij08dJ9/bAWKIC5hJlzeEIMS1NjPfXcvpo9tI1rcxPzg8rioOmAku9vzzwzUcf/tW0ILEol7NhLiaFv3v3IoF6Z+0XAmBLpAfC5DgCxALgkv8RfCl5FZPwGwgGVt6zNU24gK+7ThR31H4vQtFojVwQ1y6jLS0wUTkAtb3Nr800SvJ+janj25j5vtrcSXPz9M78KlDI78qcMy8CAsFgbED8Ux9vGkih3xbJGRZPvBulSI+nPrgZn48eBvnfroGF/uVLd4MUTXfaMShdV5JRt8sCGwfCYCp2EdhYa7hm03EOeuf2lD4fOzxbcfsqVHiSjoQHFXM5943W2bIR40zZ2ZhSrV4iByI5w4/+TnWftUvuDifn89F1bqyjmWLKii4ksfCCuYjgqgawfLs/FwU0oVWrTT6KN88m3UOE8CEXV+4zVtmyq3Z1iFxpYe1FBHVqqZJKbf/8jQxE99oRv5Ci5Dn58TC3vnPHv+YibpSn+yKFIuBldpDh/ZAOIjYJi1vKJK/taZcnSUt5ISs3cSnR1SyJ+YOP32usNTihuq77OZdr1ebSfWuKKncEbILAULP1+1K2JgKWJvR6w823h0/Cyx7/PaWqamrlCktt9R/AcGOSdbKTuffAAAAAElFTkSuQmCCiVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAYAAABXAvmHAAAHzElEQVR4nO2a229dxRXGf2tm9j4X+8ROHEdJcYJSVSA1FyQCVIoixVQlpFIf+uK8lVLaqmql8i8Yv1R9ygMvvSm9JFWr2lSIF0popWCkBpFyEaVA5VAkihMb241sH5/bvszqw/aJje3gc47jIlQ+aetsbc2s+b5ZM2tm1hz4v8DQqGVo1P7P2xweNpsVk00NnRx2jI8kTaMDEE7OVJRG1+Z120WuogN77pbJseO1m9+GRi1jZ9JbVfk4EsLJS5bxB5Pur5w7gcuDJmfF5g6TNjywae90gISg2xEvXVBX/K02bsxX/vK9Nzn2SsCr98WtCxgeNoyMeIDSqd88ZvI7zqn3aFxFfYqIALoN/AVVj9gQE3ThfTSP1k+Xn33kZVQFeUIg43VrAcvkd5z+5f0EPWe1UT6BmFTV+3BXn5NcTlC/rtptgYJYS7JY9kl5PhGXD9UnN8SY18vVq19nfGRpveSPWhCGxkzhxtK9LghfwIRFoaGmWJRgZ19WxGzHyPkoIfUevCeam1GNUsEW0KT2ilEztFDfO8n4YAqisHYcn3zBMnYmtdb8VGyuKBJHuTv2E/TtWSmzbHy7HvX+Zkfl9g1IuKdfNSpXTX7nfZ76o4w/mHD6T+FqwcvkLzn2zGpPuf5tbws/Fo27c3fscyCCKsjmQccayRykbDy7lr8nqaKtTCFVxFp8va6N6ekUV5gUXx1afOC91wAYGfFZM1mo8t0PXzhhwq4XNSrjurs12N0vmqYtkTcilOsJ1cYtI95N9HYFhE5aFoExNKauoYmAj5bKfu9e/vxwBcCtLupVF40C6mO3a3eg3rfc8+VawqmjfRy/qxfvFWPW1/OqGBF+/9dp3pupkg8sfjMVIiBCsKuP6No1xVrXJL8iYOyM5/SzOauzv9C4QtDX52gjUhoDlXrCQ0f6+MGpgU3LvzQxz9uTSxRC21ob3mPCHLbUo2m1HpZOn/9J+blHvs/QqG16QJn9wEp/8X71CRLmBBFa8/EyRFisJcSJEqdKYNd7IPGKM0KUaCuOXYEqEgRIGCi12KLplwCY6ZeVIRTsVNVaBaSrLeKrYI0QuIxZ83c1JAVnpT3yq0RkvBSg3Py8Nqhvb5C/fTDrXj6t+EzAJ43PBHzS+EzAJ41PvQC3eZH1EFEwK3tmsWCsouJJNCVRRXSDrYQqqIDxGKuI1cwWAIp60/ZJtW0BIkpSD0gji5isNXWCn1dycRdOLM6x4XnANVurFqgv5CikAalftuGFoBgjzrcloi0BYjLyfYc+pOfzN4jKIcZlW+TeesLE5xb43XwvqVfsRtvp5W22Hpvm7oEq+dDgfUY+LDWYvrKf2mwXNkjRDTy4ZQGqgnEp1Q+7Ofi1f1LaP09UyWGMxxhhojbB63ObH2h23htw9/KBRlMh7Gkw9dIBGvN5jNOWybctIMsaeGr/KfLa2RMc/s7fKO2fp1HOgyg5k6O4wS50LZKq0tCMaFhq8P5zd3H1qSO4YoRYbWsItR+FVHD5BFXhrV8do/zvnbh8kh0fbk7ij38wHgSCQsz1y3fy7tOHCEqNbE61OYk7CqPqBZtLiBbzzL25l6A7Qn0bm/xlkiaXMn1lIItGHSbKOl4HNDHkeupMvbyfa+MHyfXW0LR1c0F3xMQfjlKb6cbl47bG/WpsaSFTLxjrufrHw1y/fCfhjjqabkJEwXXFvDt2hKmXDmDDtD3vrcFtWYldMebdpzJC4Y7GxiKWT4OuGHN17AjXLx/IBG+BPHS4Em9oqBhz9akjAOw7/j5ROb9qlQVEccVkRWhPo60hd8t2t2wBbk7KpgifGvY98AFJwy1HFkGc5+rYJl7qAGu7ILvI6DArIWT7m+krA5gwy79qKpggIakFzLx6RxaxtkpeNGm+rgiI8yI2LDXzkZ1AVXD5mNpMNxOjR3GFBJtLSSPHO+fvRazvOFw2M3TZJkv61whQgalYffwzXKhJuew79YJ6wYYpU5cP8K+nD6Gp8Na5+yl/0ItxvrNwaQwaRfha1aBJQz1PAjA4+JHkbtp1+tdHbbjrDV+bjQoHDoZbuQsQUdLYUthdpfphN64Qdx5xjMFXKjSmrqfinClf/OaavNAX31KGh41T79Q3bogthNHcrBdrs7x9B1AVTJBSmytujTwgqkRzM2oKvRb4Ow+d78pGTVPAyIjn7UOycPGx1ySqfBXrJjX2ia/VvTjX8aRmWcSWyBtLUi6nmDBF0xdN3g9y/Bs1hp9YJQBg7EzKsVeCxecfvaJR9R/YQlifutbw9bpiDNIcTs0cZauP76COkF0kipCUF9JodqZuwl6ncfnphWe+Nc/LTwbNS8j1XXPykiOY6Cq5/Ljkdt+jtVlMLiTYtRsJQ8Q6tueGctmsEXwUoY0G0dyMIoGYXA++NvfzsvQ/Tq2QMv7gzTC6fiEbfMEzMrIgp0a/rD56XIUfamp21a9N4nb0eAmCFu+HOlRgDL5StWl1SU1xp2hcuZLWZp9ZuvjojzaqsengLJ46d4+1uXFUA1SKyDZ6oEnJ15GgUFH170iy9PDi89+9wclLbnXPryp9K6gwNBYwdibiofNd9OZ9aaF+VoLCYU1q23NTL5pI2OMkWrxQKn3hwuTMRWV8pM7QaMjYmagzoy384WJ78fErX3vxbWjUMtN/+//ksRaDg54RaWkB+i8/XRuK0m9lWQAAAABJRU5ErkJggg=="
ICON_FILE = DATA_DIR / "armidm_app.ico"

def ensure_app_icon() -> pathlib.Path:
    """Memastikan file armidm_app.ico tersedia di disk agar semua jendela & System Tray memiliki ikon resmi."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        local_ico = pathlib.Path(__file__).resolve().parent / "armidm.ico"
        if local_ico.exists():
            return local_ico
        if not ICON_FILE.exists() or ICON_FILE.stat().st_size < 100:
            ICON_FILE.write_bytes(base64.b64decode(EMBEDDED_ICO_B64))
        return ICON_FILE
    except Exception:
        return ICON_FILE

def center_window_on_screen(win, width: int, height: int):
    """Memposisikan jendela pop-up tepat di tengah layar monitor."""
    try:
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2 - 20)
        win.geometry(f"{width}x{height}+{x}+{y}")
    except Exception:
        win.geometry(f"{width}x{height}")

def bring_window_to_front(win, keep_topmost: bool = False):
    """
    Memaksa jendela pop-up ( seperti Download File Info & Download Complete ) muncul
    langsung di paling depan (di atas Google Chrome) tanpa harus mengklik aplikasi ArmIDM dulu.
    Menggunakan kombinasi Tkinter `-topmost` dan Win32 API `SwitchToThisWindow` / `SetForegroundWindow`.
    """
    try:
        win.deiconify()
        win.state("normal")
        win.attributes("-topmost", True)
        win.lift()
        win.focus_force()
        win.update_idletasks()
        if sys.platform.startswith("win"):
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
            # Gunakan AttachThreadInput agar Windows mengizinkan pindah fokus dari Chrome ke pop-up ArmIDM
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd:
                fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
                cur_tid = kernel32.GetCurrentThreadId()
                if fg_tid != cur_tid:
                    user32.AttachThreadInput(fg_tid, cur_tid, True)
                    user32.BringWindowToTop(hwnd)
                    user32.SetForegroundWindow(hwnd)
                    user32.AttachThreadInput(fg_tid, cur_tid, False)
            user32.SwitchToThisWindow(hwnd, True)
        if not keep_topmost:
            win.after(1800, lambda: win.winfo_exists() and win.attributes("-topmost", False))
    except Exception:
        pass

def apply_window_icon(win, parent=None, use_transient: bool = False, is_dark: bool = True):
    """Memasang ikon ArmIDM & tema titlebar modern pada jendela Tkinter."""
    try:
        ico = ensure_app_icon()
        if ico.exists() and sys.platform.startswith("win"):
            win.iconbitmap(default=str(ico))
    except Exception:
        pass
    try:
        pal = THEMES["dark" if is_dark else "light"]
        win.configure(bg=pal["bg_root"])
        apply_win32_titlebar_theme(win, is_dark=is_dark)
    except Exception:
        pass
    try:
        if use_transient and parent is not None and parent.winfo_viewable():
            win.transient(parent)
    except Exception:
        pass

# ============================================================================
# AUTO-RUN SAAT KOMPUTER DINYALAKAN (WINDOWS STARTUP & LINUX AUTOSTART)
# ============================================================================
class StartupManager:
    """
    Mengelola pendaftaran otomatis ArmIDM agar berjalan saat komputer dinyalakan (Auto-Start on Boot)
    dalam mode System Tray (--tray) seperti IDM aslinya.
    """
    REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_KEY = "ArmIDMDownloadManager"
    @classmethod
    def get_startup_command(cls) -> str:
        if getattr(sys, "frozen", False):
            # Jika dijalankan dari hasil build ArmIDM.exe
            exe_path = os.path.abspath(sys.executable)
            return f'"{exe_path}" --tray'
        # Jika dijalankan dari script armidm.py
        script_path = os.path.abspath(__file__)
        py_dir = pathlib.Path(sys.executable).resolve().parent
        pythonw = py_dir / "pythonw.exe"
        interpreter = str(pythonw) if pythonw.exists() else sys.executable
        return f'"{interpreter}" "{script_path}" --tray'
    @classmethod
    def is_enabled(cls) -> bool:
        if sys.platform.startswith("win"):
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_READ) as key:
                    val, _ = winreg.QueryValueEx(key, cls.APP_KEY)
                    return bool(val)
            except Exception:
                startup_vbs = cls._windows_startup_vbs_path()
                return startup_vbs.exists()
        else:
            desktop_file = pathlib.Path.home() / ".config" / "autostart" / "armidm.desktop"
            return desktop_file.exists()
    @classmethod
    def _windows_startup_vbs_path(cls) -> pathlib.Path:
        appdata = os.environ.get("APPDATA", str(pathlib.Path.home() / "AppData" / "Roaming"))
        return pathlib.Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "ArmIDM_AutoStart.vbs"
    @classmethod
    def set_enabled(cls, enabled: bool) -> bool:
        cmd = cls.get_startup_command()
        if sys.platform.startswith("win"):
            ok = False
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
                    try:
                        winreg.DeleteValue(key, "PyIDMDownloadManager")
                    except Exception:
                        pass
                    if enabled:
                        winreg.SetValueEx(key, cls.APP_KEY, 0, winreg.REG_SZ, cmd)
                    else:
                        try:
                            winreg.DeleteValue(key, cls.APP_KEY)
                        except FileNotFoundError:
                            pass
                ok = True
            except Exception:
                pass
            # Bersihkan atau buat fallback di Startup folder jika diperlukan
            vbs_path = cls._windows_startup_vbs_path()
            try:
                if enabled and not ok:
                    vbs_path.parent.mkdir(parents=True, exist_ok=True)
                    vbs_content = f'Set WshShell = CreateObject("WScript.Shell")\r\nWshShell.Run {cmd!r}, 0, False\r\n'
                    vbs_path.write_text(vbs_content, encoding="utf-8")
                    ok = True
                elif not enabled and vbs_path.exists():
                    vbs_path.unlink(missing_ok=True)
            except Exception:
                pass
            return ok
        else:
            autostart_dir = pathlib.Path.home() / ".config" / "autostart"
            desktop_file = autostart_dir / "armidm.desktop"
            try:
                if enabled:
                    autostart_dir.mkdir(parents=True, exist_ok=True)
                    desktop_file.write_text(
                        "[Desktop Entry]\n"
                        "Type=Application\n"
                        f"Name={APP_NAME}\n"
                        f"Exec={cmd}\n"
                        "Hidden=false\n"
                        "NoDisplay=false\n"
                        "X-GNOME-Autostart-enabled=true\n",
                        encoding="utf-8",
                    )
                else:
                    desktop_file.unlink(missing_ok=True)
                return True
            except Exception:
                return False

# ============================================================================
# NATIVE WINDOWS SYSTEM TRAY ICON (PURE CTYPES WIN32 SHELL_NOTIFYICONW)
# ============================================================================
class Win32SystemTray:
    """
    Implementasi System Tray Icon Native di Windows menggunakan ctypes (user32 & shell32)
    tanpa membutuhkan library eksternal tambahan.
    Mendukung:
    - Klik Kiri / Double Klik untuk Restore jendela utama ArmIDM
    - Klik Kanan untuk menampilkan Popup Context Menu ala IDM
    - Balloon Notification saat aplikasi diminimalkan ke System Tray
    """
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_COMMAND = 0x0111
    WM_USER = 0x0400
    WM_TRAYICON = WM_USER + 20
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    WM_CONTEXTMENU = 0x007B
    NIM_ADD = 0x00000000
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004
    NIF_INFO = 0x00000010
    NIIF_INFO = 0x00000001
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x00000010
    LR_DEFAULTSIZE = 0x00000040
    MF_STRING = 0x00000000
    MF_SEPARATOR = 0x00000800
    TPM_LEFTALIGN = 0x0000
    TPM_RIGHTBUTTON = 0x0002
    TPM_RETURNCMD = 0x0100
    TPM_NONOTIFY = 0x0080
    CMD_RESTORE = 1001
    CMD_ADD_URL = 1002
    CMD_VIDEO_SNIFFER = 1003
    CMD_START_QUEUE = 1004
    CMD_STOP_QUEUE = 1005
    CMD_PAUSE_ALL = 1006
    CMD_TOGGLE_LIMIT = 1007
    CMD_EXIT = 1009
    def __init__(self, action_callback):
        self.action_callback = action_callback
        self.hwnd = None
        self.hicon = None
        self._nid = None
        self._thread = None
        self._running = False
        self._balloon_shown = False
    def start(self):
        if not sys.platform.startswith("win"):
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._win32_loop, daemon=True)
        self._thread.start()
    def show_balloon(self, title: str, message: str):
        if not sys.platform.startswith("win") or not self.hwnd or not self._nid:
            return
        try:
            import ctypes
            self._nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP | self.NIF_INFO
            self._nid.szInfoTitle = title[:63]
            self._nid.szInfo = message[:255]
            self._nid.dwInfoFlags = self.NIIF_INFO
            ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_MODIFY, ctypes.byref(self._nid))
        except Exception:
            pass
    def stop(self):
        if not sys.platform.startswith("win") or not self._running:
            return
        self._running = False
        try:
            import ctypes
            if self._nid and self.hwnd:
                ctypes.windll.shell32.Shell_NotifyIconW(self.NIM_DELETE, ctypes.byref(self._nid))
            if self.hwnd:
                ctypes.windll.user32.PostMessageW(self.hwnd, self.WM_CLOSE, 0, 0)
        except Exception:
            pass
    def _win32_loop(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            kernel32 = ctypes.windll.kernel32
            LRESULT = ctypes.c_ssize_t
            WPARAM = ctypes.c_size_t
            LPARAM = ctypes.c_ssize_t
            WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)
            user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
            user32.DefWindowProcW.restype = LRESULT
            class WNDCLASSEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("style", wintypes.UINT),
                    ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR),
                    ("hIconSm", wintypes.HICON),
                ]
            class NOTIFYICONDATAW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT),
                    ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.WCHAR * 128),
                    ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.WCHAR * 256),
                    ("uTimeoutOrVersion", wintypes.UINT),
                    ("szInfoTitle", wintypes.WCHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD),
                ]
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            def wnd_proc(hwnd, msg, wparam, lparam):
                if msg == self.WM_TRAYICON:
                    event = lparam & 0xFFFF
                    if event in (self.WM_LBUTTONUP, self.WM_LBUTTONDBLCLK):
                        self.action_callback("restore")
                        return 0
                    elif event in (self.WM_RBUTTONUP, self.WM_CONTEXTMENU):
                        self._show_popup_menu(hwnd, user32, POINT)
                        return 0
                elif msg == self.WM_CLOSE:
                    user32.DestroyWindow(hwnd)
                    return 0
                elif msg == self.WM_DESTROY:
                    user32.PostQuitMessage(0)
                    return 0
                return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
            self._wnd_proc_ref = WNDPROC(wnd_proc)
            hinst = kernel32.GetModuleHandleW(None)
            class_name = f"ArmIDMTrayWnd_{os.getpid()}"
            wcx = WNDCLASSEXW()
            wcx.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wcx.lpfnWndProc = self._wnd_proc_ref
            wcx.hInstance = hinst
            wcx.lpszClassName = class_name
            user32.RegisterClassExW(ctypes.byref(wcx))
            user32.CreateWindowExW.restype = wintypes.HWND
            self.hwnd = user32.CreateWindowExW(
                0, class_name, "ArmIDMTrayHost", 0, 0, 0, 0, 0, None, None, hinst, None
            )
            ico_path = str(ensure_app_icon())
            user32.LoadImageW.restype = wintypes.HICON
            self.hicon = user32.LoadImageW(
                None, ico_path, self.IMAGE_ICON, 0, 0, self.LR_LOADFROMFILE | self.LR_DEFAULTSIZE
            )
            if not self.hicon:
                self.hicon = user32.LoadIconW(None, ctypes.cast(32512, wintypes.LPCWSTR))
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = self.NIF_MESSAGE | self.NIF_ICON | self.NIF_TIP
            nid.uCallbackMessage = self.WM_TRAYICON
            nid.hIcon = self.hicon
            nid.szTip = "ArmIDM - Internet Download Manager (Klik untuk Membuka)"
            self._nid = nid
            shell32.Shell_NotifyIconW(self.NIM_ADD, ctypes.byref(self._nid))
            msg = wintypes.MSG()
            while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception:
            pass
    def _show_popup_menu(self, hwnd, user32, point_cls):
        import ctypes
        from ctypes import wintypes
        user32.CreatePopupMenu.restype = wintypes.HMENU
        hmenu = user32.CreatePopupMenu()
        if not hmenu:
            return
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_RESTORE, "📂 Buka ArmIDM (Restore Window)")
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_ADD_URL, "➕ Tambah Unduhan Baru (Add URL)...")
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_VIDEO_SNIFFER, "🎬 Video Sniffer (Daftar Video)...")
        user32.AppendMenuW(hmenu, self.MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_START_QUEUE, "▶ Mulai Antrean (Start Queue)")
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_STOP_QUEUE, "⏹ Hentikan Antrean (Stop Queue)")
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_PAUSE_ALL, "⏸ Jeda Semua Unduhan Aktif")
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_TOGGLE_LIMIT, "⚡ Aktifkan / Matikan Speed Limiter")
        user32.AppendMenuW(hmenu, self.MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, self.MF_STRING, self.CMD_EXIT, "❌ Keluar dari ArmIDM (Exit)")
        # Jadikan item pertama (Restore) tampak bold seperti IDM
        try:
            user32.SetMenuDefaultItem(hmenu, self.CMD_RESTORE, 0)
        except Exception:
            pass
        pt = point_cls()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(
            hmenu,
            self.TPM_LEFTALIGN | self.TPM_RIGHTBUTTON | self.TPM_RETURNCMD | self.TPM_NONOTIFY,
            pt.x,
            pt.y,
            0,
            hwnd,
            None,
        )
        user32.PostMessageW(hwnd, 0, 0, 0)
        user32.DestroyMenu(hmenu)
        cmd_map = {
            self.CMD_RESTORE: "restore",
            self.CMD_ADD_URL: "add_url",
            self.CMD_VIDEO_SNIFFER: "video_sniffer",
            self.CMD_START_QUEUE: "start_queue",
            self.CMD_STOP_QUEUE: "stop_queue",
            self.CMD_PAUSE_ALL: "pause_all",
            self.CMD_TOGGLE_LIMIT: "toggle_limit",
            self.CMD_EXIT: "exit",
        }
        if cmd in cmd_map:
            self.action_callback(cmd_map[cmd])

# ============================================================================
# SPEED LIMITER (TOKEN BUCKET RATE LIMITER)
# ============================================================================
class TokenBucketLimiter:
    """
    Pembatas kecepatan real-time menggunakan algoritma Token Bucket.
    Mendukung pembatasan global dan pembatasan spesifik per tugas unduhan.
    """
    def __init__(self, enabled: bool = False, rate_kbps: int = 1024):
        self.enabled = enabled
        self.rate_kbps = max(10, int(rate_kbps))
        self._tokens = float(self.rate_kbps * 1024)
        self._last_check = time.monotonic()
        self._lock = threading.Lock()
    def set_limit(self, enabled: bool, rate_kbps: int):
        with self._lock:
            self.enabled = bool(enabled)
            self.rate_kbps = max(10, int(rate_kbps))
            self._tokens = float(self.rate_kbps * 1024)
            self._last_check = time.monotonic()
    def consume(self, byte_count: int):
        if not self.enabled or byte_count <= 0:
            return
        sleep_needed = 0.0
        with self._lock:
            if not self.enabled:
                return
            rate_bps = float(self.rate_kbps * 1024)
            now = time.monotonic()
            elapsed = now - self._last_check
            self._last_check = now
            self._tokens = min(rate_bps, self._tokens + elapsed * rate_bps)
            self._tokens -= byte_count
            if self._tokens < 0:
                sleep_needed = (-self._tokens) / rate_bps
        if sleep_needed > 0:
            time.sleep(min(sleep_needed, 2.0))

# ============================================================================
# MODEL SEGMEN & TUGAS UNDUHAN (MULTI-CONNECTION DOWNLOAD ENGINE)
# ============================================================================
class SegmentInfo:
    def __init__(self, index: int, start_byte: int, end_byte: int, downloaded: int = 0, status: str = "Waiting"):
        self.index = index
        self.start_byte = start_byte
        self.end_byte = end_byte  # -1 jika ukuran tidak diketahui
        self.downloaded = downloaded
        self.status = status
    @property
    def total_bytes(self) -> int:
        if self.end_byte < 0:
            return -1
        return max(0, self.end_byte - self.start_byte + 1)
    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "downloaded": self.downloaded,
            "status": self.status,
        }
    @classmethod
    def from_dict(cls, data: dict) -> "SegmentInfo":
        return cls(
            index=data["index"],
            start_byte=data["start_byte"],
            end_byte=data["end_byte"],
            downloaded=data.get("downloaded", 0),
            status=data.get("status", "Waiting"),
        )

class DownloadTask:
    """
    Merepresentasikan satu item unduhan di ArmIDM.
    Mendukung:
    - Multi-connection HTTP Range segmented downloading
    - HLS (.m3u8) video stream downloading & segment merging
    - Pause, Resume, Cancel, Queueing, dan Per-Task Speed Limit
    """
    def __init__(
        self,
        task_id: str,
        url: str,
        filename: str,
        save_dir: str,
        category: str = "General",
        connections: int = 8,
        headers: dict = None,
        total_size: int = -1,
        resumable: bool = False,
        status: str = "Queued",
        downloaded_bytes: int = 0,
        added_date: str = None,
        queue_name: str = "Main Queue",
        description: str = "",
        task_speed_limit_enabled: bool = False,
        task_speed_limit_kbps: int = 512,
        segments: list = None,
        is_hls: bool = False,
    ):
        self.id = task_id
        self.url = url
        self.filename = sanitize_filename(filename)
        self.save_dir = save_dir
        self.category = category
        self.connections = max(1, min(32, int(connections)))
        self.headers = headers or {}
        self.total_size = int(total_size)
        self.resumable = bool(resumable)
        self.status = status
        self.downloaded_bytes = int(downloaded_bytes)
        self.added_date = added_date or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.queue_name = queue_name
        self.description = description
        self.is_hls = bool(is_hls or ".m3u8" in url.lower())
        # Per-task speed limiter
        self.task_limiter = TokenBucketLimiter(task_speed_limit_enabled, task_speed_limit_kbps)
        self.open_when_done = False
        self.show_complete_dialog = True
        # Runtime state
        self.segments: list[SegmentInfo] = [SegmentInfo.from_dict(s) for s in (segments or [])]
        self.transfer_rate = 0.0
        self.eta_seconds = -1.0
        self.error_message = ""
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread = None
        self._lock = threading.Lock()
        self._speed_window = []  # list of (timestamp, bytes_delta)
    @property
    def target_path(self) -> pathlib.Path:
        return pathlib.Path(self.save_dir) / self.filename
    @property
    def temp_folder(self) -> pathlib.Path:
        return TEMP_DIR / self.id
    @property
    def progress_percent(self) -> float:
        if self.status == "Complete":
            return 100.0
        if self.total_size > 0:
            return min(100.0, (self.downloaded_bytes / self.total_size) * 100.0)
        return 0.0
    @property
    def active_connections_count(self) -> int:
        return sum(1 for s in self.segments if s.status.startswith("Downloading"))
    def record_bytes(self, delta: int):
        now = time.monotonic()
        with self._lock:
            self.downloaded_bytes += delta
            self._speed_window.append((now, delta))
            cutoff = now - 2.5
            while self._speed_window and self._speed_window[0][0] < cutoff:
                self._speed_window.pop(0)
            window_bytes = sum(b for _, b in self._speed_window)
            span = max(0.25, now - self._speed_window[0][0]) if self._speed_window else 1.0
            self.transfer_rate = window_bytes / span
            if self.total_size > 0 and self.transfer_rate > 0:
                remaining = max(0, self.total_size - self.downloaded_bytes)
                self.eta_seconds = remaining / self.transfer_rate
            else:
                self.eta_seconds = -1.0
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.filename,
            "save_dir": self.save_dir,
            "category": self.category,
            "connections": self.connections,
            "headers": self.headers,
            "total_size": self.total_size,
            "resumable": self.resumable,
            "status": self.status,
            "downloaded_bytes": self.downloaded_bytes,
            "added_date": self.added_date,
            "queue_name": self.queue_name,
            "description": self.description,
            "task_speed_limit_enabled": self.task_limiter.enabled,
            "task_speed_limit_kbps": self.task_limiter.rate_kbps,
            "segments": [s.to_dict() for s in self.segments],
            "is_hls": self.is_hls,
        }
    @classmethod
    def from_dict(cls, data: dict) -> "DownloadTask":
        st = data.get("status", "Paused")
        if st.startswith("Downloading") or st == "Connecting...":
            st = "Paused"
        return cls(
            task_id=data["id"],
            url=data["url"],
            filename=data["filename"],
            save_dir=data.get("save_dir", str(DEFAULT_DOWNLOAD_DIR)),
            category=data.get("category", "General"),
            connections=data.get("connections", 8),
            headers=data.get("headers", {}),
            total_size=data.get("total_size", -1),
            resumable=data.get("resumable", False),
            status=st,
            downloaded_bytes=data.get("downloaded_bytes", 0),
            added_date=data.get("added_date"),
            queue_name=data.get("queue_name", "Main Queue"),
            description=data.get("description", ""),
            task_speed_limit_enabled=data.get("task_speed_limit_enabled", False),
            task_speed_limit_kbps=data.get("task_speed_limit_kbps", 512),
            segments=data.get("segments", []),
            is_hls=data.get("is_hls", False),
        )

# ============================================================================
# ENGINE UTAMA PENGELOLA UNDUHAN (DOWNLOAD MANAGER CORE)
# ============================================================================
class DownloadManagerCore:
    """
    Mengelola seluruh siklus hidup unduhan:
    - Probing URL metadata (ukuran file, nama file, dukungan Range, HLS manifest)
    - Multi-connection worker threads
    - Penggabungan segmen otomatis
    - Penjadwalan antrean (Scheduler) & Speed Limiter Global
    - Penyimpanan state persisten
    """
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.config = {
            "default_download_dir": str(DEFAULT_DOWNLOAD_DIR),
            "default_connections": 8,
            "max_concurrent_downloads": 3,
            "server_port": DEFAULT_PORT,
            "intercept_browser": True,
            "speed_limit_enabled": False,
            "speed_limit_kbps": 1024,
            "schedule_enabled": False,
            "schedule_start_time": "01:00",
            "schedule_stop_time": "06:00",
            "show_complete_dialog": True,
            "auto_startup": True,
            "minimize_to_tray": True,
            "theme": "dark",
            "intercept_extensions": [
                ".zip", ".rar", ".7z", ".tar", ".gz", ".exe", ".msi", ".dmg",
                ".iso", ".apk", ".mp4", ".mkv", ".webm", ".avi", ".mov", ".mp3",
                ".flac", ".wav", ".pdf", ".docx", ".xlsx", ".pptx"
            ],
        }
        self.load_config()
        self.global_limiter = TokenBucketLimiter(
            enabled=self.config["speed_limit_enabled"],
            rate_kbps=self.config["speed_limit_kbps"],
        )
        self.tasks: dict[str, DownloadTask] = {}
        self.task_order: list[str] = []
        self.detected_media: list[dict] = []  # Daftar video/audio yang terdeteksi dari Chrome
        self.queue_running = False
        self._lock = threading.Lock()
        self.ui_callbacks: list = []
        self.ws_clients: set = set()
        self.load_state()
        if self.config.get('auto_startup', True):
            StartupManager.set_enabled(True)
        # Background thread untuk Scheduler & Queue Monitor
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self._scheduler_thread.start()
    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                loaded = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                self.config.update(loaded)
            except Exception:
                pass
    def save_config(self):
        try:
            CONFIG_FILE.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        except Exception:
            pass
    def load_state(self):
        if STATE_FILE.exists():
            try:
                raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                for item in raw.get("tasks", []):
                    t = DownloadTask.from_dict(item)
                    self.tasks[t.id] = t
                    self.task_order.append(t.id)
            except Exception:
                pass
    def save_state(self):
        with self._lock:
            payload = {
                "tasks": [self.tasks[tid].to_dict() for tid in self.task_order if tid in self.tasks]
            }
        try:
            STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass
    def register_ui_callback(self, cb):
        self.ui_callbacks.append(cb)
    def notify_event(self, event_type: str, data: dict = None):
        for cb in self.ui_callbacks:
            try:
                cb(event_type, data or {})
            except Exception:
                pass
    def set_global_speed_limit(self, enabled: bool, rate_kbps: int):
        self.config["speed_limit_enabled"] = bool(enabled)
        self.config["speed_limit_kbps"] = max(10, int(rate_kbps))
        self.global_limiter.set_limit(self.config["speed_limit_enabled"], self.config["speed_limit_kbps"])
        self.save_config()
        self.notify_event("speed_limit_changed", {
            "enabled": self.config["speed_limit_enabled"],
            "rate_kbps": self.config["speed_limit_kbps"],
        })
    # ------------------------------------------------------------------------
    # PROBE URL METADATA (CEK UKURAN, NAMA FILE, DAN DUKUNGAN MULTI-SEGMENT)
    # ------------------------------------------------------------------------
    def probe_url(self, url: str, headers: dict = None, timeout: int = 12) -> dict:
        if is_ytdlp_supported_url(url):
            return YouTubeAndSocialEngine.probe_video_info(url, headers=headers)
        url, headers = GofileResolver.ensure_gofile_headers(url, headers or {})
        req_headers = {
            "User-Agent": (headers or {}).get(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            ),
            "Accept": "*/*",
        }
        if headers:
            for k, v in headers.items():
                if k and v and k.lower() in ("referer", "cookie", "authorization", "origin", "user-agent"):
                    req_headers[k] = v
        parsed = urllib.parse.urlparse(url)
        raw_name = pathlib.Path(urllib.parse.unquote(parsed.path)).name or "download_file"
        info = {
            "url": url,
            "filename": sanitize_filename(raw_name),
            "total_size": -1,
            "resumable": False,
            "mime_type": "",
            "is_hls": ".m3u8" in url.lower(),
            "category": "General",
            "headers": req_headers,
            "is_html_trap": False,
        }
        # 1. Coba request dengan Range: bytes=0-0 beserta Cookie & Referer penuh
        try:
            probe_headers = dict(req_headers)
            probe_headers["Range"] = "bytes=0-0"
            req = urllib.request.Request(url, method="GET")
            with open_url_with_headers(req, probe_headers, timeout=timeout) as resp:
                status_code = getattr(resp, "status", 200)
                resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                info["mime_type"] = resp_headers.get("content-type", "").split(";")[0].strip()
                cd = resp_headers.get("content-disposition", "")
                if "filename=" in cd:
                    m = re.search(r'filename\*?=["\']?(?:UTF-8\'\')?([^"\';\r\n]+)', cd, re.IGNORECASE)
                    if m:
                        info["filename"] = sanitize_filename(m.group(1))
                if status_code == 206 or "bytes" in resp_headers.get("accept-ranges", "").lower():
                    info["resumable"] = True
                cr = resp_headers.get("content-range", "")
                if "/" in cr:
                    total_part = cr.split("/")[-1].strip()
                    if total_part.isdigit():
                        info["total_size"] = int(total_part)
                        info["resumable"] = True
                elif "content-length" in resp_headers and status_code == 200:
                    cl = resp_headers["content-length"].strip()
                    if cl.isdigit():
                        info["total_size"] = int(cl)
                if (
                    status_code == 200
                    and not info["resumable"]
                    and not info["is_hls"]
                    and "mpegurl" not in info["mime_type"].lower()
                    and "text/html" not in info["mime_type"].lower()
                    and (0 < info["total_size"] <= 64 * 1024 * 1024 or "usercontent.google.com" in url.lower())
                ):
                    TEMP_DIR.mkdir(parents=True, exist_ok=True)
                    url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:12]
                    cache_file = TEMP_DIR / f"prefetched_{url_hash}.cache"
                    with open(cache_file, "wb") as cf:
                        shutil.copyfileobj(resp, cf, length=256 * 1024)
                    if cache_file.exists() and cache_file.stat().st_size > 0:
                        info["total_size"] = cache_file.stat().st_size
        except Exception:
            try:
                req = urllib.request.Request(url, method="HEAD")
                with open_url_with_headers(req, req_headers, timeout=timeout) as resp:
                    resp_headers = {k.lower(): v for k, v in resp.headers.items()}
                    info["mime_type"] = resp_headers.get("content-type", "").split(";")[0].strip()
                    if "bytes" in resp_headers.get("accept-ranges", "").lower():
                        info["resumable"] = True
                    cl = resp_headers.get("content-length", "")
                    if cl.isdigit():
                        info["total_size"] = int(cl)
            except Exception:
                pass
        # Deteksi jika server justru mengembalikan halaman web HTML kecil (misal 3.28 KB) padahal ekstensi adalah file biner
        ext_lower = pathlib.Path(info["filename"]).suffix.lower()
        if "text/html" in info["mime_type"].lower() and ext_lower in BINARY_FILE_EXTENSIONS:
            info["is_html_trap"] = True
            info["resumable"] = False
        if "mpegurl" in info["mime_type"].lower() or info["filename"].lower().endswith(".m3u8"):
            info["is_hls"] = True
            if info["filename"].lower().endswith(".m3u8"):
                info["filename"] = info["filename"][:-5] + ".ts"
        if not pathlib.Path(info["filename"]).suffix and info["mime_type"]:
            ext_guess = {
                "video/mp4": ".mp4",
                "video/webm": ".webm",
                "video/x-matroska": ".mkv",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "application/pdf": ".pdf",
                "application/zip": ".zip",
            }.get(info["mime_type"].lower(), "")
            if ext_guess:
                info["filename"] += ext_guess
        info["category"] = detect_category(info["filename"], info["mime_type"])
        return info
    # ------------------------------------------------------------------------
    # MANAJEMEN TUGAS (TAMBAH, MULAI, JEDA, LANJUTKAN, HAPUS)
    # ------------------------------------------------------------------------
    def create_task(
        self,
        url: str,
        filename: str = "",
        save_dir: str = "",
        category: str = "",
        connections: int = 0,
        headers: dict = None,
        total_size: int = -1,
        resumable: bool = False,
        start_immediately: bool = True,
        queue_name: str = "Main Queue",
        description: str = "",
    ) -> DownloadTask:
        url, headers = GofileResolver.ensure_gofile_headers(url, headers or {})
        if not filename or total_size < 0:
            probed = self.probe_url(url, headers=headers)
            url = probed.get("url", url)
            headers = probed.get("headers", headers)
            if not filename:
                filename = probed["filename"]
            if total_size < 0:
                total_size = probed["total_size"]
            resumable = probed["resumable"]
            if not category:
                category = probed["category"]
            is_hls = probed["is_hls"]
        else:
            is_hls = ".m3u8" in url.lower()
        if not category:
            category = detect_category(filename)
        if not pathlib.Path(filename).suffix:
            if category == "Video":
                filename += ".mp4"
            elif category == "Music":
                filename += ".mp3"
        if not save_dir:
            base_dir = pathlib.Path(self.config["default_download_dir"]).resolve()
            sub = CATEGORY_FOLDERS.get(category, "General")
            save_dir = str((base_dir / sub).resolve())
        else:
            save_dir = str(pathlib.Path(save_dir).resolve())
        pathlib.Path(save_dir).mkdir(parents=True, exist_ok=True)
        # Hindari duplikasi nama file di disk
        base_name = pathlib.Path(filename).stem
        ext = pathlib.Path(filename).suffix
        candidate = sanitize_filename(filename)
        counter = 1
        while (pathlib.Path(save_dir) / candidate).exists():
            candidate = f"{base_name}_{counter}{ext}"
            counter += 1
        task_id = hashlib.md5(f"{url}_{time.time()}_{counter}".encode()).hexdigest()[:10]
        conn_count = connections if connections > 0 else self.config["default_connections"]
        task = DownloadTask(
            task_id=task_id,
            url=url,
            filename=candidate,
            save_dir=save_dir,
            category=category,
            connections=conn_count,
            headers=headers or {},
            total_size=total_size,
            resumable=resumable,
            status="Queued",
            queue_name=queue_name,
            description=description,
            is_hls=is_hls,
        )
        with self._lock:
            self.tasks[task.id] = task
            self.task_order.insert(0, task.id)
        self.save_state()
        self.notify_event("task_added", {"task_id": task.id})
        if start_immediately:
            self.start_task(task.id)
        return task
    def start_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        if task._worker_thread and task._worker_thread.is_alive():
            return
        if task.status == "Complete":
            return
        task._stop_event.clear()
        task.error_message = ""
        task.status = "Connecting..."
        task._worker_thread = threading.Thread(target=self._run_download_task, args=(task,), daemon=True)
        task._worker_thread.start()
        self.notify_event("task_started", {"task_id": task.id})
    def pause_task(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            return
        task._stop_event.set()
        if task.status != "Complete":
            task.status = "Paused"
            task.transfer_rate = 0.0
            for seg in task.segments:
                if seg.status.startswith("Downloading") or seg.status == "Connecting":
                    seg.status = "Paused"
        self.save_state()
        self.notify_event("task_paused", {"task_id": task.id})
    def pause_all(self):
        for tid in list(self.task_order):
            t = self.tasks.get(tid)
            if t and (t.status.startswith("Downloading") or t.status == "Connecting..."):
                self.pause_task(tid)
    def delete_task(self, task_id: str, delete_file: bool = False):
        task = self.tasks.get(task_id)
        if not task:
            return
        task._stop_event.set()
        with self._lock:
            self.tasks.pop(task_id, None)
            if task_id in self.task_order:
                self.task_order.remove(task_id)
        if task.temp_folder.exists():
            shutil.rmtree(task.temp_folder, ignore_errors=True)
        if delete_file and task.target_path.exists():
            try:
                task.target_path.unlink()
            except Exception:
                pass
        self.save_state()
        self.notify_event("task_deleted", {"task_id": task_id})
    def delete_completed(self):
        completed_ids = [tid for tid, t in self.tasks.items() if t.status == "Complete"]
        for tid in completed_ids:
            self.delete_task(tid, delete_file=False)
    # ------------------------------------------------------------------------
    # EKSEKUSI MULTI-CONNECTION & HLS STREAMING
    # ------------------------------------------------------------------------
    def _build_request_headers(self, task: DownloadTask) -> dict:
        req_headers = {
            "User-Agent": task.headers.get(
                "User-Agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            ),
            "Accept": "*/*",
        }
        for k, v in task.headers.items():
            if k and v and k.lower() in ("referer", "cookie", "authorization", "origin", "user-agent"):
                req_headers[k] = v
        return req_headers
    def _run_download_task(self, task: DownloadTask):
        try:
            pathlib.Path(task.save_dir).mkdir(parents=True, exist_ok=True)
            task.temp_folder.mkdir(parents=True, exist_ok=True)
            if is_ytdlp_supported_url(task.url):
                YouTubeAndSocialEngine.download_video(self, task)
                return
            if task.is_hls:
                self._download_hls_stream(task)
                return
            url_hash = hashlib.md5(task.url.encode("utf-8")).hexdigest()[:12]
            prefetched_cache = TEMP_DIR / f"prefetched_{url_hash}.cache"
            if prefetched_cache.exists() and prefetched_cache.stat().st_size > 0:
                task.status = "Downloading"
                sz = prefetched_cache.stat().st_size
                task.total_size = sz
                task.downloaded_bytes = sz
                task.segments = [SegmentInfo(index=0, start_byte=0, end_byte=max(0, sz - 1), downloaded=sz, status="Completed")]
                shutil.move(str(prefetched_cache), str(task.target_path))
                shutil.rmtree(task.temp_folder, ignore_errors=True)
                task.status = "Complete"
                task.transfer_rate = 0.0
                task.eta_seconds = 0.0
                self.save_state()
                self.notify_event("task_completed", {"task_id": task.id})
                return
            # Segarkan metadata jika belum pernah di-probe
            if task.total_size < 0 and not task.segments:
                probed = self.probe_url(task.url, headers=task.headers)
                task.total_size = probed["total_size"]
                task.resumable = probed["resumable"]
            # Inisialisasi segmen jika belum ada
            if not task.segments:
                if task.resumable and task.total_size > 64 * 1024 and task.connections > 1:
                    num_conns = task.connections
                    chunk_size = task.total_size // num_conns
                    segments = []
                    for i in range(num_conns):
                        start_b = i * chunk_size
                        end_b = (task.total_size - 1) if (i == num_conns - 1) else ((i + 1) * chunk_size - 1)
                        segments.append(SegmentInfo(index=i, start_byte=start_b, end_byte=end_b, downloaded=0))
                    task.segments = segments
                else:
                    task.connections = 1
                    end_b = (task.total_size - 1) if task.total_size > 0 else -1
                    task.segments = [SegmentInfo(index=0, start_byte=0, end_byte=end_b, downloaded=0)]
            # Hitung ulang total downloaded_bytes dari file segmen yang sudah ada di disk (untuk Resume akurat)
            total_existing = 0
            for seg in task.segments:
                seg_file = task.temp_folder / f"seg_{seg.index}.part"
                if seg_file.exists():
                    actual_size = seg_file.stat().st_size
                    if seg.total_bytes > 0:
                        actual_size = min(actual_size, seg.total_bytes)
                    seg.downloaded = actual_size
                    total_existing += actual_size
                else:
                    seg.downloaded = 0
            task.downloaded_bytes = total_existing
            task.status = "Downloading"
            self.save_state()
            # Jalankan worker thread untuk setiap segmen paralel
            threads = []
            for seg in task.segments:
                if seg.total_bytes > 0 and seg.downloaded >= seg.total_bytes:
                    seg.status = "Completed"
                    continue
                t = threading.Thread(target=self._download_segment_worker, args=(task, seg), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            if task._stop_event.is_set():
                task.status = "Paused"
                task.transfer_rate = 0.0
                self.save_state()
                return
            # Cek apakah semua segmen berhasil diselesaikan
            all_done = all(seg.status == "Completed" for seg in task.segments)
            if not all_done:
                failed = [seg for seg in task.segments if seg.status.startswith("Error")]
                task.status = "Error"
                task.error_message = failed[0].status if failed else "Incomplete download"
                task.transfer_rate = 0.0
                self.save_state()
                self.notify_event("task_error", {"task_id": task.id, "error": task.error_message})
                return
            # Gabungkan seluruh segmen menjadi file akhir
            task.status = "Merging segments..."
            with open(task.target_path, "wb") as out_f:
                for seg in sorted(task.segments, key=lambda s: s.index):
                    seg_file = task.temp_folder / f"seg_{seg.index}.part"
                    if seg_file.exists():
                        with open(seg_file, "rb") as in_f:
                            shutil.copyfileobj(in_f, out_f, length=1024 * 1024)
            shutil.rmtree(task.temp_folder, ignore_errors=True)
            if task.total_size <= 0 and task.target_path.exists():
                task.total_size = task.target_path.stat().st_size
                task.downloaded_bytes = task.total_size
            task.status = "Complete"
            task.transfer_rate = 0.0
            task.eta_seconds = 0.0
            self.save_state()
            self.notify_event("task_completed", {"task_id": task.id})
        except Exception as exc:
            task.status = "Error"
            task.error_message = str(exc)
            task.transfer_rate = 0.0
            self.save_state()
            self.notify_event("task_error", {"task_id": task.id, "error": str(exc)})
    def _download_segment_worker(self, task: DownloadTask, seg: SegmentInfo):
        seg_file = task.temp_folder / f"seg_{seg.index}.part"
        ctx = create_ssl_context()
        retries = 0
        max_retries = 4
        while retries <= max_retries and not task._stop_event.is_set():
            try:
                req_headers = self._build_request_headers(task)
                current_start = seg.start_byte + seg.downloaded
                if seg.end_byte >= 0:
                    if current_start > seg.end_byte:
                        seg.status = "Completed"
                        return
                    if (task.resumable or len(task.segments) > 1 or seg.downloaded > 0) and not (retries > 0 and len(task.segments) == 1):
                        req_headers["Range"] = f"bytes={current_start}-{seg.end_byte}"
                elif seg.downloaded > 0 and task.resumable:
                    req_headers["Range"] = f"bytes={current_start}-"
                seg.status = "Connecting"
                req = urllib.request.Request(task.url, method="GET")
                with open_url_with_headers(req, req_headers, timeout=25) as resp:
                    status_code = getattr(resp, "status", 200)
                    ctype = (resp.headers.get("Content-Type") or "").lower()
                    ext_l = pathlib.Path(task.filename).suffix.lower()
                    if "text/html" in ctype and ext_l in BINARY_FILE_EXTENSIONS:
                        raise RuntimeError(
                            "Server mengembalikan halaman HTML (bukan file biner). Pastikan ekstensi Chrome ArmIDM sudah di-Reload di chrome://extensions agar Cookie sesi (accountToken) terkirim."
                        )
                    # Jika server mengabaikan header Range pada segmen 0, tulis ulang dari awal
                    if status_code == 200 and seg.index == 0 and seg.downloaded > 0:
                        with task._lock:
                            task.downloaded_bytes = max(0, task.downloaded_bytes - seg.downloaded)
                        seg.downloaded = 0
                        mode = "wb"
                    else:
                        mode = "ab" if seg.downloaded > 0 else "wb"
                    seg.status = "Downloading"
                    with open(seg_file, mode) as f:
                        while not task._stop_event.is_set():
                            chunk = resp.read(16384)
                            if not chunk:
                                break
                            # Pastikan tidak melebihi batas segmen
                            if seg.end_byte >= 0:
                                remaining_in_seg = (seg.end_byte - seg.start_byte + 1) - seg.downloaded
                                if remaining_in_seg <= 0:
                                    break
                                if len(chunk) > remaining_in_seg:
                                    chunk = chunk[:remaining_in_seg]
                            f.write(chunk)
                            nbytes = len(chunk)
                            seg.downloaded += nbytes
                            task.record_bytes(nbytes)
                            # Terapkan pembatas kecepatan (Speed Limiter)
                            self.global_limiter.consume(nbytes)
                            task.task_limiter.consume(nbytes)
                            if seg.end_byte >= 0 and seg.downloaded >= (seg.end_byte - seg.start_byte + 1):
                                break
                if task._stop_event.is_set():
                    seg.status = "Paused"
                    return
                if seg.end_byte < 0 or seg.downloaded >= (seg.end_byte - seg.start_byte + 1):
                    seg.status = "Completed"
                    return
                retries += 1
            except Exception as exc:
                retries += 1
                if retries > max_retries:
                    seg.status = f"Error: {exc}"
                    return
                time.sleep(min(2.0 * retries, 5.0))
    def _download_hls_stream(self, task: DownloadTask):
        """
        Mengunduh stream video HLS (.m3u8) secara native dengan mem-parsing daftar segmen .ts
        dan mengunduhnya secara paralel beserta dukungan Speed Limiter.
        """
        ctx = create_ssl_context()
        req_headers = self._build_request_headers(task)
        def fetch_text(u: str) -> str:
            req = urllib.request.Request(u, headers=req_headers, method="GET")
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                return r.read().decode("utf-8", errors="replace")
        manifest_url = task.url
        content = fetch_text(manifest_url)
        # Jika ini master playlist (#EXT-X-STREAM-INF), pilih varian dengan bandwidth tertinggi
        if "#EXT-X-STREAM-INF" in content:
            best_bw = -1
            best_uri = None
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            for i, ln in enumerate(lines):
                if ln.startswith("#EXT-X-STREAM-INF"):
                    m = re.search(r"BANDWIDTH=(\d+)", ln)
                    bw = int(m.group(1)) if m else 0
                    if i + 1 < len(lines) and not lines[i + 1].startswith("#"):
                        if bw >= best_bw:
                            best_bw = bw
                            best_uri = urllib.parse.urljoin(manifest_url, lines[i + 1])
            if best_uri:
                manifest_url = best_uri
                content = fetch_text(manifest_url)
        ts_urls = []
        for ln in content.splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                ts_urls.append(urllib.parse.urljoin(manifest_url, ln))
        if not ts_urls:
            raise RuntimeError("Tidak ditemukan segmen media di dalam playlist M3U8.")
        num_workers = min(task.connections, len(ts_urls))
        task.segments = [
            SegmentInfo(index=i, start_byte=i, end_byte=len(ts_urls) - 1, downloaded=0, status="Downloading")
            for i in range(num_workers)
        ]
        task.status = f"Downloading HLS (0/{len(ts_urls)})"
        q_items = queue.Queue()
        for idx, u in enumerate(ts_urls):
            part_path = task.temp_folder / f"hls_{idx:05d}.ts"
            if not part_path.exists() or part_path.stat().st_size == 0:
                q_items.put((idx, u))
        completed_parts = len(ts_urls) - q_items.qsize()
        def hls_worker(seg_info: SegmentInfo):
            nonlocal completed_parts
            while not task._stop_event.is_set():
                try:
                    idx, seg_url = q_items.get_nowait()
                except queue.Empty:
                    seg_info.status = "Completed"
                    return
                part_path = task.temp_folder / f"hls_{idx:05d}.ts"
                try:
                    req = urllib.request.Request(seg_url, headers=req_headers, method="GET")
                    with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                        data = resp.read()
                        part_path.write_bytes(data)
                        nbytes = len(data)
                        seg_info.downloaded += nbytes
                        task.record_bytes(nbytes)
                        self.global_limiter.consume(nbytes)
                        task.task_limiter.consume(nbytes)
                    with task._lock:
                        completed_parts += 1
                        task.status = f"Downloading HLS ({completed_parts}/{len(ts_urls)})"
                except Exception as e:
                    seg_info.status = f"Error: {e}"
                finally:
                    q_items.task_done()
        workers = [threading.Thread(target=hls_worker, args=(seg,), daemon=True) for seg in task.segments]
        for w in workers:
            w.start()
        for w in workers:
            w.join()
        if task._stop_event.is_set():
            task.status = "Paused"
            task.transfer_rate = 0.0
            self.save_state()
            return
        task.status = "Merging HLS stream..."
        with open(task.target_path, "wb") as out_f:
            for idx in range(len(ts_urls)):
                p = task.temp_folder / f"hls_{idx:05d}.ts"
                if p.exists():
                    out_f.write(p.read_bytes())
        shutil.rmtree(task.temp_folder, ignore_errors=True)
        task.total_size = task.target_path.stat().st_size if task.target_path.exists() else task.downloaded_bytes
        task.downloaded_bytes = task.total_size
        task.status = "Complete"
        task.transfer_rate = 0.0
        self.save_state()
        self.notify_event("task_completed", {"task_id": task.id})
    # ------------------------------------------------------------------------
    # PENANGKAP VIDEO / MEDIA SNIFFER REGISTRY
    # ------------------------------------------------------------------------
    def register_detected_media(self, media_info: dict) -> dict:
        """
        Mencatat stream video/audio yang dikirim oleh Chrome Extension.
        """
        url = (media_info.get("url") or "").strip()
        if not url:
            return {"status": "ignored"}
        with self._lock:
            for existing in self.detected_media:
                if existing["url"] == url:
                    existing.update({k: v for k, v in media_info.items() if v})
                    return existing
            entry = {
                "id": hashlib.md5(url.encode()).hexdigest()[:10],
                "url": url,
                "filename": sanitize_filename(media_info.get("filename") or "video.mp4"),
                "page_title": media_info.get("page_title") or "Web Video",
                "page_url": media_info.get("page_url") or "",
                "mime_type": media_info.get("mime_type") or "video/mp4",
                "size": int(media_info.get("size") or -1),
                "quality": media_info.get("quality") or "HD / Auto",
                "tab_id": media_info.get("tab_id"),
                "headers": media_info.get("headers") or {},
                "detected_at": datetime.datetime.now().strftime("%H:%M:%S"),
            }
            self.detected_media.insert(0, entry)
            if len(self.detected_media) > 150:
                self.detected_media = self.detected_media[:150]
        self.notify_event("media_detected", entry)
        return entry
    # ------------------------------------------------------------------------
    # SCHEDULER & QUEUE LOOP
    # ------------------------------------------------------------------------
    def start_queue(self):
        self.queue_running = True
        self.notify_event("queue_state_changed", {"running": True})
    def stop_queue(self):
        self.queue_running = False
        self.notify_event("queue_state_changed", {"running": False})
    def _scheduler_loop(self):
        while True:
            try:
                if self.config.get("schedule_enabled"):
                    now_hm = datetime.datetime.now().strftime("%H:%M")
                    if now_hm == self.config.get("schedule_start_time"):
                        self.queue_running = True
                    elif now_hm == self.config.get("schedule_stop_time"):
                        self.queue_running = False
                        self.pause_all()
                if self.queue_running:
                    active_count = sum(
                        1 for t in self.tasks.values()
                        if t.status.startswith("Downloading") or t.status == "Connecting..."
                    )
                    max_conc = max(1, int(self.config.get("max_concurrent_downloads", 3)))
                    if active_count < max_conc:
                        for tid in reversed(self.task_order):
                            t = self.tasks.get(tid)
                            if t and t.status == "Queued":
                                self.start_task(tid)
                                active_count += 1
                                if active_count >= max_conc:
                                    break
            except Exception:
                pass
            time.sleep(1.5)

# ============================================================================
# SERVER KOMUNIKASI LOKAL (HTTP REST + NATIVE WEBSOCKET RFC 6455)
# ============================================================================
class LocalIDMServer:
    """
    Server lokal di 127.0.0.1:16888 yang melayani komunikasi HTTP REST & WebSocket
    dengan Chrome Extension ArmIDM.
    """
    def __init__(self, core: DownloadManagerCore, port: int = DEFAULT_PORT):
        self.core = core
        self.port = port
        self.httpd = None
        self._thread = None
    def start(self):
        core_ref = self.core
        class RequestHandler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, fmt, *args):
                pass  # Senyapkan log standar agar terminal tetap bersih
            def _send_cors_headers(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
            def _send_json(self, status_code: int, payload: dict):
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self._send_cors_headers()
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def do_OPTIONS(self):
                self.send_response(204)
                self._send_cors_headers()
                self.send_header("Content-Length", "0")
                self.end_headers()
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                # Dukungan Upgrade WebSocket (ws://127.0.0.1:16888/ws)
                if path == "/ws" and self.headers.get("Upgrade", "").lower() == "websocket":
                    self._handle_websocket()
                    return
                if path in ("/ping", "/api/status"):
                    tasks_summary = []
                    total_speed = 0.0
                    for tid in core_ref.task_order[:25]:
                        t = core_ref.tasks.get(tid)
                        if t:
                            total_speed += t.transfer_rate
                            tasks_summary.append({
                                "id": t.id,
                                "filename": t.filename,
                                "size": t.total_size,
                                "downloaded": t.downloaded_bytes,
                                "progress": round(t.progress_percent, 1),
                                "status": t.status,
                                "speed": round(t.transfer_rate, 1),
                                "speed_Formatted": format_speed(t.transfer_rate),
                                "eta": format_eta(t.eta_seconds),
                                "category": t.category,
                            })
                    self._send_json(200, {
                        "status": "online",
                        "app": APP_NAME,
                        "version": APP_VERSION,
                        "intercept_enabled": core_ref.config["intercept_browser"],
                        "intercept_extensions": core_ref.config["intercept_extensions"],
                        "speed_limit_enabled": core_ref.config["speed_limit_enabled"],
                        "speed_limit_kbps": core_ref.config["speed_limit_kbps"],
                        "total_speed": round(total_speed, 1),
                        "total_speed_formatted": format_speed(total_speed),
                        "tasks": tasks_summary,
                        "detected_media_count": len(core_ref.detected_media),
                    })
                    return
                if path == "/api/media_list":
                    qs = urllib.parse.parse_qs(parsed.query)
                    tab_id = qs.get("tab_id", [None])[0]
                    media = core_ref.detected_media
                    if tab_id is not None and str(tab_id).isdigit():
                        media = [m for m in media if str(m.get("tab_id")) == str(tab_id)]
                    self._send_json(200, {"media": media[:50]})
                    return
                self._send_json(404, {"error": "Endpoint not found"})
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    data = json.loads(raw_body.decode("utf-8"))
                except Exception:
                    data = {}
                path = urllib.parse.urlparse(self.path).path
                if path in ("/add_download", "/api/add_download"):
                    url = (data.get("url") or "").strip()
                    if not url:
                        self._send_json(400, {"error": "Missing url"})
                        return
                    show_dialog = data.get("show_dialog", True)
                    if show_dialog and core_ref.ui_callbacks:
                        # Minta GUI menampilkan dialog konfirmasi "Download File Info" ala IDM
                        core_ref.notify_event("extension_download_request", data)
                        self._send_json(200, {"status": "dialog_opened", "url": url})
                    else:
                        task = core_ref.create_task(
                            url=url,
                            filename=data.get("filename", ""),
                            headers=data.get("headers", {}),
                            description=data.get("description", "Intercepted from Chrome"),
                            start_immediately=True,
                        )
                        self._send_json(200, {"status": "started", "task_id": task.id, "filename": task.filename})
                    return
                if path in ("/report_media", "/api/report_media"):
                    entry = core_ref.register_detected_media(data)
                    self._send_json(200, {"status": "registered", "media": entry})
                    return
                if path == "/api/speed_limit":
                    enabled = bool(data.get("enabled", False))
                    rate_kbps = int(data.get("rate_kbps", 1024))
                    core_ref.set_global_speed_limit(enabled, rate_kbps)
                    self._send_json(200, {
                        "status": "updated",
                        "speed_limit_enabled": core_ref.config["speed_limit_enabled"],
                        "speed_limit_kbps": core_ref.config["speed_limit_kbps"],
                    })
                    return
                if path == "/api/toggle_intercept":
                    core_ref.config["intercept_browser"] = bool(data.get("enabled", True))
                    core_ref.save_config()
                    core_ref.notify_event("intercept_changed", {"enabled": core_ref.config["intercept_browser"]})
                    self._send_json(200, {"status": "updated", "intercept_enabled": core_ref.config["intercept_browser"]})
                    return
                if path == "/api/control_task":
                    tid = data.get("task_id", "")
                    action = data.get("action", "")
                    if action == "pause":
                        core_ref.pause_task(tid)
                    elif action == "resume":
                        core_ref.start_task(tid)
                    elif action == "delete":
                        core_ref.delete_task(tid)
                    self._send_json(200, {"status": "ok"})
                    return
                self._send_json(404, {"error": "Unknown POST endpoint"})
            def _handle_websocket(self):
                key = self.headers.get("Sec-WebSocket-Key", "")
                magic = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
                accept = base64.b64encode(hashlib.sha1((key + magic).encode()).digest()).decode()
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                conn = self.connection
                core_ref.ws_clients.add(conn)
                try:
                    while True:
                        hdr = conn.recv(2)
                        if not hdr or len(hdr) < 2:
                            break
                        opcode = hdr[0] & 0x0F
                        if opcode == 0x8:  # Close frame
                            break
                        masked = bool(hdr[1] & 0x80)
                        payload_len = hdr[1] & 0x7F
                        if payload_len == 126:
                            payload_len = struct.unpack(">H", conn.recv(2))[0]
                        elif payload_len == 127:
                            payload_len = struct.unpack(">Q", conn.recv(8))[0]
                        mask_key = conn.recv(4) if masked else b""
                        raw_payload = bytearray(conn.recv(payload_len))
                        if masked:
                            for i in range(len(raw_payload)):
                                raw_payload[i] ^= mask_key[i % 4]
                        msg = json.loads(raw_payload.decode("utf-8", errors="ignore"))
                        if msg.get("type") == "ping":
                            reply = json.dumps({"type": "pong", "speed_limit_enabled": core_ref.config["speed_limit_enabled"]}).encode()
                            frame = bytearray([0x81, len(reply)]) + reply
                            conn.sendall(frame)
                except Exception:
                    pass
                finally:
                    core_ref.ws_clients.discard(conn)
        class ThreadedHTTPServer(http.server.ThreadingHTTPServer):
            allow_reuse_address = True
        self.httpd = ThreadedHTTPServer(("127.0.0.1", self.port), RequestHandler)
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

# ============================================================================
# ANTARMUKA DESKTOP GUI KLASIK IDM (TKINTER / TTK)
# ============================================================================
class DownloadCompleteDialog:
    """
    Dialog Notifikasi "Download complete" Persis Seperti IDM Asli:
    - Menampilkan ikon dokumen/kategori dengan badge centang sukses
    - Informasi ukuran file yang diunduh
    - Field read-only "From:" (URL sumber) dan "Saved as:" (Lokasi file di disk)
    - Checkbox "Don't show this dialog again"
    - 4 Tombol Aksi Khas IDM: [Open], [Open With...], [Open Folder], [Close]
    """
    def __init__(self, parent, core: DownloadManagerCore, task: DownloadTask):
        self.core = core
        self.task = task
        self.win = tk.Toplevel(parent)
        self.win.title("Download complete")
        center_window_on_screen(self.win, 550, 270)
        self.win.minsize(520, 255)
        self.win.resizable(False, False)
        apply_window_icon(self.win, parent, use_transient=False, is_dark=(self.core.config.get("theme", "dark") == "dark"))
        # Paksa muncul di paling depan (di atas browser) dan bunyikan notifikasi
        try:
            self.win.bell()
        except Exception:
            pass
        bring_window_to_front(self.win, keep_topmost=True)
        main_frame = ttk.Frame(self.win, padding=(16, 14, 16, 14))
        main_frame.pack(fill=tk.BOTH, expand=True)
        # --- BAGIAN ATAS: IKON SUKSES IDM + TEKS HEADER ---
        top_row = ttk.Frame(main_frame)
        top_row.pack(fill=tk.X, pady=(0, 12))
        icon_canvas = tk.Canvas(top_row, width=54, height=54, highlightthickness=0)
        icon_canvas.pack(side=tk.LEFT, padx=(0, 14))
        # Gambar ikon file biru & lingkaran centang hijau ala IDM
        icon_canvas.create_rectangle(8, 4, 40, 46, fill="#EFF6FF", outline="#1D4ED8", width=2)
        icon_canvas.create_line(14, 15, 34, 15, fill="#3B82F6", width=2)
        icon_canvas.create_line(14, 23, 34, 23, fill="#3B82F6", width=2)
        icon_canvas.create_line(14, 31, 26, 31, fill="#3B82F6", width=2)
        icon_canvas.create_oval(26, 26, 51, 51, fill="#16A34A", outline="#FFFFFF", width=2)
        icon_canvas.create_line(32, 39, 37, 44, 46, 33, fill="#FFFFFF", width=3)
        header_text_frame = ttk.Frame(top_row)
        header_text_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(
            header_text_frame,
            text="Download Complete",
            font=("Segoe UI", 12, "bold"),
            foreground="#0F172A",
        ).pack(anchor="w")
        size_bytes_str = f"{task.total_size:,} bytes" if task.total_size > 0 else ""
        dl_summary = f"Downloaded {format_size(task.total_size)}" + (f" ({size_bytes_str})" if size_bytes_str else "")
        ttk.Label(
            header_text_frame,
            text=dl_summary,
            font=("Segoe UI", 9),
            foreground="#334155",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Label(
            header_text_frame,
            text=f"File: {task.filename}   •   Category: {task.category}",
            font=("Segoe UI", 8, "bold"),
            foreground="#1D4ED8",
        ).pack(anchor="w", pady=(2, 0))
        # --- BAGIAN TENGAH: FIELD "From:" & "Saved as:" ---
        fields_frame = ttk.Frame(main_frame)
        fields_frame.pack(fill=tk.X, pady=(2, 10))
        fields_frame.columnconfigure(1, weight=1)
        ttk.Label(fields_frame, text="From:", width=10, anchor="w", font=("Segoe UI", 9)).grid(
            row=0, column=0, sticky="w", pady=4
        )
        clean_from_url = task.url.split("#pyidm_quality=")[0]
        self.from_var = tk.StringVar(master=self.win, value=clean_from_url)
        from_entry = ttk.Entry(fields_frame, textvariable=self.from_var)
        from_entry.delete(0, tk.END)
        from_entry.insert(0, clean_from_url)
        from_entry.configure(state="readonly")
        from_entry.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(fields_frame, text="Saved as:", width=10, anchor="w", font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky="w", pady=4
        )
        full_saved_path = os.path.normpath(os.path.abspath(str(task.target_path)))
        self.saved_var = tk.StringVar(master=self.win, value=full_saved_path)
        saved_entry = ttk.Entry(fields_frame, textvariable=self.saved_var)
        saved_entry.delete(0, tk.END)
        saved_entry.insert(0, full_saved_path)
        saved_entry.configure(state="readonly")
        saved_entry.grid(row=1, column=1, sticky="ew", pady=4)
        # --- CHECKBOX "Don't show this dialog again" ---
        self.dont_show_var = tk.BooleanVar(value=not self.core.config.get("show_complete_dialog", True))
        ttk.Checkbutton(
            main_frame,
            text="Don't show this dialog again",
            variable=self.dont_show_var,
            command=self._on_toggle_dont_show,
        ).pack(anchor="w", pady=(2, 12))
        # --- TOMBOL AKSI BAWAH PERSIS IDM: [Open] [Open With...] [Open Folder] [Close] ---
        btn_bar = ttk.Frame(main_frame)
        btn_bar.pack(fill=tk.X, side=tk.BOTTOM)
        btn_open = ttk.Button(btn_bar, text="📂 Open", width=13, style="Success.TButton", command=self._action_open)
        btn_open.pack(side=tk.LEFT, padx=(0, 8))
        btn_open_with = ttk.Button(btn_bar, text="Open With...", width=14, command=self._action_open_with)
        btn_open_with.pack(side=tk.LEFT, padx=(0, 8))
        btn_open_folder = ttk.Button(btn_bar, text="📁 Open Folder", width=14, style="Accent.TButton", command=self._action_open_folder)
        btn_open_folder.pack(side=tk.LEFT, padx=(0, 8))
        btn_close = ttk.Button(btn_bar, text="Close", width=12, command=self.win.destroy)
        btn_close.pack(side=tk.RIGHT)
        self.win.bind("<Return>", lambda e: self._action_open())
        self.win.bind("<Escape>", lambda e: self.win.destroy())
        btn_open.focus_set()
    def _on_toggle_dont_show(self):
        self.core.config["show_complete_dialog"] = not self.dont_show_var.get()
        self.core.save_config()
    def _action_open(self):
        launch_file_default(self.task.target_path)
        if self.win.winfo_exists():
            self.win.destroy()
    def _action_open_with(self):
        launch_open_with(self.task.target_path)
        if self.win.winfo_exists():
            self.win.destroy()
    def _action_open_folder(self):
        launch_open_folder_select(self.task.target_path, self.task.save_dir)
        if self.win.winfo_exists():
            self.win.destroy()



class ProgressDialogWindow:
    """
    Jendela Progres Unduhan Modern ArmIDM v3.0:
    Memiliki 3 Tab dengan Tema Modern (Dark / Light):
    1. Download status:
       - Header Card dengan Nama File, Kategori, dan Persentase Besar
       - Grid Informasi Real-Time (URL, Status, Size, Downloaded, Speed, ETA, Resume)
       - Progress Bar Modern + Grafik Kecepatan Real-Time (Live Speed Sparkline)
       - Visualisasi Segmen Multi-Koneksi Berwarna Biru/Cyan & Tabel Koneksi
       - Tombol Aksi Berwarna: [<< Hide details], [⏸ Pause / ▶ Start / Resume], dan [⏹ Cancel]
    2. Speed Limiter
    3. Options on completion
    """
    def __init__(self, parent, core: DownloadManagerCore, task: DownloadTask):
        self.core = core
        self.task = task
        self.details_visible = True
        self.speed_history = [0.0] * 35
        is_dark = self.core.config.get("theme", "dark") == "dark"
        self.pal = THEMES["dark" if is_dark else "light"]
        self.win = tk.Toplevel(parent)
        self.win.title(f"{task.progress_percent:.1f}% - {task.filename} | ArmIDM")
        center_window_on_screen(self.win, 660, 545)
        self.win.minsize(610, 500)
        apply_window_icon(self.win, parent, use_transient=False, is_dark=is_dark)
        bring_window_to_front(self.win, keep_topmost=False)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)
        # Header Banner Modern di atas Notebook
        hdr = tk.Frame(self.win, bg=self.pal["bg_header"], padx=16, pady=10)
        hdr.pack(fill=tk.X)
        cat_icon = CAT_ICONS.get(task.category, "📦")
        self.hdr_title_var = tk.StringVar(value=f"{cat_icon}  {task.filename[:55]}")
        tk.Label(
            hdr,
            textvariable=self.hdr_title_var,
            bg=self.pal["bg_header"],
            fg="#F8FAFC",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.hdr_pct_var = tk.StringVar(value=f"{task.progress_percent:.1f}%")
        tk.Label(
            hdr,
            textvariable=self.hdr_pct_var,
            bg="#2563EB",
            fg="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padx=10,
            pady=2,
        ).pack(side=tk.RIGHT)
        notebook = ttk.Notebook(self.win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        # --- TAB 1: DOWNLOAD STATUS ---
        tab_status = ttk.Frame(notebook, padding=(14, 10, 14, 10))
        notebook.add(tab_status, text="  ⚡ Download Status  ")
        top_section = ttk.Frame(tab_status)
        top_section.pack(side=tk.TOP, fill=tk.X)
        info_grid = ttk.Frame(top_section)
        info_grid.pack(fill=tk.X, pady=(0, 6))
        info_grid.columnconfigure(1, weight=1)
        labels = [
            ("Source URL:", "url_val"),
            ("Current Status:", "status_val"),
            ("Total File Size:", "size_val"),
            ("Downloaded:", "dl_val"),
            ("Transfer Rate:", "rate_val"),
            ("Estimated Time Left:", "eta_val"),
            ("Multi-Segment Resume:", "resume_val"),
        ]
        self.lbl_vars = {}
        for row_idx, (title_txt, key) in enumerate(labels):
            ttk.Label(info_grid, text=title_txt, width=20, anchor="w", font=("Segoe UI", 9, "bold")).grid(
                row=row_idx, column=0, sticky="w", pady=1
            )
            var = tk.StringVar(value="-")
            self.lbl_vars[key] = var
            fg_col = self.pal["row_downloading"] if key == "rate_val" else self.pal["fg_primary"]
            ttk.Label(
                info_grid,
                textvariable=var,
                width=58,
                anchor="w",
                foreground=fg_col,
                font=("Segoe UI", 9, "bold" if key in ("rate_val", "status_val") else "normal"),
            ).grid(row=row_idx, column=1, sticky="w", pady=1)
        self.prog_var = tk.DoubleVar(value=task.progress_percent)
        self.prog_bar = ttk.Progressbar(
            top_section,
            variable=self.prog_var,
            maximum=100.0,
            style="IDM.Horizontal.TProgressbar",
        )
        self.prog_bar.pack(fill=tk.X, pady=(6, 8))
        # Baris Tombol Bawah (Selalu Terlihat & Berwarna Modern)
        btn_row = ttk.Frame(tab_status)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 2))
        self.btn_details = ttk.Button(
            btn_row,
            text="<< Hide details",
            width=15,
            command=self._toggle_details,
        )
        self.btn_details.pack(side=tk.LEFT)
        self.btn_cancel = ttk.Button(
            btn_row,
            text="⏹ Cancel",
            width=13,
            style="Danger.TButton",
            command=self._cancel_download,
        )
        self.btn_cancel.pack(side=tk.RIGHT, padx=(6, 0))
        self.btn_toggle = ttk.Button(
            btn_row,
            text="⏸ Pause",
            width=17,
            style="Accent.TButton",
            command=self._toggle_pause_resume,
        )
        self.btn_toggle.pack(side=tk.RIGHT, padx=4)
        # Bagian Tengah: Visualisasi Segmen Biru & Tabel Koneksi Paralel
        self.details_frame = ttk.Frame(tab_status)
        self.details_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        ttk.Label(
            self.details_frame,
            text="Active Multi-Connection Segments Visualization:",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")
        self.seg_canvas = tk.Canvas(
            self.details_frame,
            height=24,
            bg=self.pal["seg_bg"],
            highlightthickness=1,
            highlightbackground=self.pal["border"],
        )
        self.seg_canvas.pack(fill=tk.X, pady=(3, 8))
        tree_container = ttk.Frame(self.details_frame)
        tree_container.pack(fill=tk.BOTH, expand=True)
        cols = ("conn_no", "downloaded", "status")
        self.conn_tree = ttk.Treeview(tree_container, columns=cols, show="headings", height=5)
        self.conn_tree.heading("conn_no", text="#")
        self.conn_tree.heading("downloaded", text="Downloaded")
        self.conn_tree.heading("status", text="Segment Status")
        self.conn_tree.column("conn_no", width=50, anchor="center")
        self.conn_tree.column("downloaded", width=140, anchor="e")
        self.conn_tree.column("status", width=360, anchor="w")
        conn_scroll = ttk.Scrollbar(tree_container, orient="vertical", command=self.conn_tree.yview)
        self.conn_tree.configure(yscrollcommand=conn_scroll.set)
        self.conn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        conn_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        # --- TAB 2: SPEED LIMITER ---
        tab_limit = ttk.Frame(notebook, padding=16)
        notebook.add(tab_limit, text="  🚦 Speed Limiter  ")
        self.task_limit_enabled_var = tk.BooleanVar(value=task.task_limiter.enabled)
        self.task_limit_kbps_var = tk.IntVar(value=task.task_limiter.rate_kbps)
        ttk.Checkbutton(
            tab_limit,
            text="Enable dedicated speed limiter for this download",
            variable=self.task_limit_enabled_var,
            command=self._apply_task_limit,
        ).pack(anchor="w", pady=(0, 12))
        limit_row = ttk.Frame(tab_limit)
        limit_row.pack(fill=tk.X, pady=4)
        ttk.Label(limit_row, text="Maximum speed for this file (KB/s):").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Spinbox(limit_row, from_=10, to=100000, textvariable=self.task_limit_kbps_var, width=10).pack(side=tk.LEFT)
        ttk.Button(limit_row, text="Apply Limit", style="Accent.TButton", command=self._apply_task_limit).pack(side=tk.LEFT, padx=8)
        # --- TAB 3: OPTIONS ON COMPLETION ---
        tab_opt = ttk.Frame(notebook, padding=16)
        notebook.add(tab_opt, text="  ✅ On Completion  ")
        self.show_dlg_var = tk.BooleanVar(value=task.show_complete_dialog)
        ttk.Checkbutton(
            tab_opt,
            text="Show 'Download complete' notification dialog when finished",
            variable=self.show_dlg_var,
            command=lambda: setattr(self.task, "show_complete_dialog", self.show_dlg_var.get()),
        ).pack(anchor="w", pady=6)
        self.open_done_var = tk.BooleanVar(value=task.open_when_done)
        ttk.Checkbutton(
            tab_opt,
            text="Open file automatically when download completes",
            variable=self.open_done_var,
            command=lambda: setattr(self.task, "open_when_done", self.open_done_var.get()),
        ).pack(anchor="w", pady=6)
        self.refresh_ui()
    def _toggle_details(self):
        if self.details_visible:
            self.details_frame.pack_forget()
            self.btn_details.config(text=">> Show details")
            self.win.minsize(610, 320)
            self.win.geometry("660x330")
            self.details_visible = False
        else:
            self.details_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
            self.btn_details.config(text="<< Hide details")
            self.win.minsize(610, 500)
            self.win.geometry("660x545")
            self.details_visible = True
    def _apply_task_limit(self):
        try:
            kbps = max(10, int(self.task_limit_kbps_var.get()))
        except Exception:
            kbps = 512
        self.task.task_limiter.set_limit(self.task_limit_enabled_var.get(), kbps)
        self.core.save_state()
    def _toggle_pause_resume(self):
        if self.task.status.startswith("Downloading") or self.task.status == "Connecting...":
            self.core.pause_task(self.task.id)
        else:
            self.core.start_task(self.task.id)
        self.refresh_ui()
    def _cancel_download(self):
        if self.task.status.startswith("Downloading") or self.task.status == "Connecting...":
            self.core.pause_task(self.task.id)
        if self.win.winfo_exists():
            self.win.destroy()
    def refresh_ui(self):
        if not self.win.winfo_exists():
            return
        t = self.task
        pct = t.progress_percent
        self.win.title(f"{pct:.1f}% - {t.filename} | ArmIDM")
        self.hdr_pct_var.set(f"{pct:.1f}%")
        clean_u = t.url.split("#pyidm_quality=")[0]
        self.lbl_vars["url_val"].set(clean_u[:75] + ("..." if len(clean_u) > 75 else ""))
        self.lbl_vars["status_val"].set(t.status if not t.error_message else f"{t.status} ({t.error_message})")
        self.lbl_vars["size_val"].set(format_size(t.total_size))
        self.lbl_vars["dl_val"].set(f"{format_size(t.downloaded_bytes)} ({pct:.1f}%)")
        is_active = t.status.startswith("Downloading") or t.status == "Connecting..."
        self.lbl_vars["rate_val"].set(format_speed(t.transfer_rate) if is_active else "0 KB/s")
        self.lbl_vars["eta_val"].set(format_eta(t.eta_seconds) if is_active else ("- (Paused)" if t.status == "Paused" else "-"))
        self.lbl_vars["resume_val"].set("Yes (Multi-Segment)" if t.resumable else "Single Connection")
        self.prog_var.set(pct)
        if is_active:
            self.btn_toggle.config(text="⏸ Pause", style="Warning.TButton", state=tk.NORMAL)
        elif t.status == "Complete":
            self.btn_toggle.config(text="✅ Completed", style="Success.TButton", state=tk.DISABLED)
        else:
            self.btn_toggle.config(text="▶ Start / Resume", style="Success.TButton", state=tk.NORMAL)
        if self.details_visible:
            self.seg_canvas.delete("all")
            w = max(220, self.seg_canvas.winfo_width())
            h = 24
            if t.segments:
                seg_w = w / len(t.segments)
                for idx, seg in enumerate(t.segments):
                    x0 = idx * seg_w + 1
                    x1 = (idx + 1) * seg_w - 1
                    self.seg_canvas.create_rectangle(x0, 2, x1, h - 2, fill=self.pal["seg_empty"], outline="")
                    ratio = 1.0 if seg.status == "Completed" else (
                        min(1.0, seg.downloaded / seg.total_bytes) if seg.total_bytes > 0 else 0.5
                    )
                    if ratio > 0:
                        fill_col = self.pal["success"] if seg.status == "Completed" else self.pal["seg_fill"]
                        self.seg_canvas.create_rectangle(x0, 2, x0 + ((x1 - x0) * ratio), h - 2, fill=fill_col, outline="")
            existing = self.conn_tree.get_children()
            if len(existing) != len(t.segments):
                for item in existing:
                    self.conn_tree.delete(item)
                for seg in t.segments:
                    self.conn_tree.insert("", tk.END, iid=str(seg.index), values=(seg.index + 1, format_size(seg.downloaded), seg.status))
            else:
                for seg in t.segments:
                    self.conn_tree.item(str(seg.index), values=(seg.index + 1, format_size(seg.downloaded), seg.status))

class ArmIDMDesktopGUI:
    """
    Jendela Utama Aplikasi ArmIDM v3.0 dengan Antarmuka Modern Fluent (Dark & Light Mode),
    Tombol Aksi Berwarna, Kotak Pencarian Real-Time, Grafik Kecepatan Live Sparkline,
    dan Tabel Unduhan Berwarna per Status.
    """
    def __init__(self, core: DownloadManagerCore, start_in_tray: bool = False):
        self.core = core
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry("1140x680")
        self.root.minsize(960, 560)
        self.theme_mode = self.core.config.get("theme", "dark")
        if self.theme_mode not in THEMES:
            self.theme_mode = "dark"
        self.pal = THEMES[self.theme_mode]
        apply_window_icon(self.root, is_dark=(self.theme_mode == "dark"))
        # Inisialisasi System Tray Icon
        self.tray_icon = Win32SystemTray(self._on_tray_action)
        self.tray_icon.start()
        self._tray_balloon_notified = False
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_window_request)
        self.selected_filter = ("Category", "All Downloads")
        self.search_query_var = tk.StringVar(value="")
        self.search_query_var.trace_add("write", lambda *_: self._refresh_table(full=True))
        self.progress_windows: dict[str, ProgressDialogWindow] = {}
        self.complete_windows: dict[str, DownloadCompleteDialog] = {}
        self.info_dialogs: dict[str, tk.Toplevel] = {}
        self.ui_event_queue = queue.Queue()
        self.speed_history = [0.0] * 40
        self._setup_styles()
        self._build_menubar()
        self._build_header_banner()
        self._build_toolbar()
        self._build_speed_limiter_bar()
        self._build_main_panes()
        self._build_statusbar()
        self.core.register_ui_callback(self._on_core_event)
        self._refresh_table(full=True)
        self._periodic_ui_tick()
        if start_in_tray:
            self.root.after(100, lambda: self.minimize_to_tray(show_balloon=False))
    def _setup_styles(self):
        self.pal = THEMES[self.theme_mode]
        p = self.pal
        self.root.configure(bg=p["bg_root"])
        apply_win32_titlebar_theme(self.root, is_dark=(self.theme_mode == "dark"))
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=p["bg_root"], foreground=p["fg_primary"], font=("Segoe UI", 9))
        style.configure("TFrame", background=p["bg_root"])
        style.configure("Card.TFrame", background=p["bg_panel"])
        style.configure("TLabel", background=p["bg_root"], foreground=p["fg_primary"], font=("Segoe UI", 9))
        style.configure("Muted.TLabel", background=p["bg_root"], foreground=p["fg_secondary"], font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=p["bg_root"], foreground=p["fg_primary"], font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", p["bg_root"])])
        style.configure(
            "TEntry",
            fieldbackground=p["bg_input"],
            foreground=p["fg_primary"],
            insertcolor=p["fg_primary"],
            bordercolor=p["border"],
            lightcolor=p["border"],
            darkcolor=p["border"],
            padding=4,
        )
        style.configure(
            "TSpinbox",
            fieldbackground=p["bg_input"],
            foreground=p["fg_primary"],
            arrowcolor=p["fg_primary"],
            bordercolor=p["border"],
            padding=3,
        )
        style.configure(
            "TCombobox",
            fieldbackground=p["bg_input"],
            background=p["bg_panel"],
            foreground=p["fg_primary"],
            arrowcolor=p["fg_primary"],
            padding=3,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", p["bg_input"])],
            foreground=[("readonly", p["fg_primary"])],
        )
        # Notebook Modern Tabs
        style.configure("TNotebook", background=p["bg_root"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=p["bg_panel"],
            foreground=p["fg_secondary"],
            padding=(12, 6),
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", p["accent"])],
            foreground=[("selected", "#FFFFFF")],
        )
        # Treeview Modern Styling (Sidebar & Tabel Utama)
        style.configure(
            "Treeview",
            background=p["tree_bg"],
            fieldbackground=p["tree_bg"],
            foreground=p["tree_fg"],
            rowheight=30,
            font=("Segoe UI", 9),
            borderwidth=0,
            relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", p["tree_sel_bg"])],
            foreground=[("selected", p["tree_sel_fg"])],
        )
        style.configure(
            "Treeview.Heading",
            background=p["tree_head_bg"],
            foreground=p["tree_head_fg"],
            font=("Segoe UI", 9, "bold"),
            padding=(8, 7),
            relief="flat",
        )
        style.map("Treeview.Heading", background=[("active", p["border"])])
        # Tombol-Tombol Berwarna Modern
        btn_base = {"font": ("Segoe UI", 9, "bold"), "padding": (9, 5), "borderwidth": 0, "relief": "flat"}
        style.configure("TButton", background=p["bg_panel"], foreground=p["fg_primary"], **btn_base)
        style.map("TButton", background=[("active", p["border"])])
        style.configure("Toolbar.TButton", background=p["bg_panel"], foreground=p["fg_primary"], **btn_base)
        style.map("Toolbar.TButton", background=[("active", p["border"])])
        style.configure("Accent.TButton", background=p["accent"], foreground="#FFFFFF", **btn_base)
        style.map("Accent.TButton", background=[("active", p["accent_hover"])])
        style.configure("Success.TButton", background=p["success"], foreground="#FFFFFF", **btn_base)
        style.map("Success.TButton", background=[("active", p["success_hover"])])
        style.configure("Warning.TButton", background=p["warning"], foreground="#FFFFFF", **btn_base)
        style.map("Warning.TButton", background=[("active", "#B45309")])
        style.configure("Danger.TButton", background=p["danger"], foreground="#FFFFFF", **btn_base)
        style.map("Danger.TButton", background=[("active", "#B91C1C")])
        style.configure("Purple.TButton", background=p["purple"], foreground="#FFFFFF", **btn_base)
        style.map("Purple.TButton", background=[("active", "#6D28D9")])
        style.configure(
            "IDM.Horizontal.TProgressbar",
            troughcolor=p["seg_bg"],
            background=p["success"],
            bordercolor=p["border"],
            lightcolor=p["success"],
            darkcolor=p["success"],
            thickness=18,
        )
    def toggle_theme(self):
        self.theme_mode = "light" if self.theme_mode == "dark" else "dark"
        self.core.config["theme"] = self.theme_mode
        self.core.save_config()
        self._setup_styles()
        if hasattr(self, "theme_btn"):
            self.theme_btn.config(text="☀️ Light Mode" if self.theme_mode == "dark" else "🌙 Dark Mode")
        if hasattr(self, "spark_canvas"):
            self.spark_canvas.config(bg=self.pal["seg_bg"], highlightbackground=self.pal["border"])
        self._configure_table_tags()
        self._refresh_table(full=True)
    def _build_menubar(self):
        menubar = tk.Menu(self.root)
        m_tasks = tk.Menu(menubar, tearoff=0)
        m_tasks.add_command(label="Add new download...", accelerator="Ctrl+N", command=self.open_add_url_dialog)
        m_tasks.add_command(label="Detected Videos (Video Sniffer)...", accelerator="Ctrl+V", command=self.open_video_sniffer_window)
        m_tasks.add_separator()
        m_tasks.add_command(label="Toggle Dark / Light Theme", command=self.toggle_theme)
        m_tasks.add_command(label="Minimize to System Tray", accelerator="Ctrl+M", command=self.minimize_to_tray)
        m_tasks.add_command(label="Exit ArmIDM Completely", command=self.exit_application)
        menubar.add_cascade(label="Tasks", menu=m_tasks)
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Resume Selected", command=self.resume_selected)
        m_file.add_command(label="Pause / Stop Selected", command=self.pause_selected)
        m_file.add_command(label="Stop All Active Downloads", command=self.core.pause_all)
        m_file.add_separator()
        m_file.add_command(label="Delete Selected", command=self.delete_selected)
        m_file.add_command(label="Delete All Completed", command=self.confirm_delete_completed)
        menubar.add_cascade(label="File", menu=m_file)
        m_dl = tk.Menu(menubar, tearoff=0)
        m_dl.add_command(label="Start Queue", command=self.core.start_queue)
        m_dl.add_command(label="Stop Queue", command=self.core.stop_queue)
        m_dl.add_command(label="Scheduler & Queue Settings...", command=self.open_scheduler_dialog)
        m_dl.add_separator()
        m_dl.add_command(label="Options / Settings...", command=self.open_options_dialog)
        menubar.add_cascade(label="Downloads", menu=m_dl)
        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="Browser Extension Setup Guide", command=self.show_extension_guide)
        m_help.add_command(label="About ArmIDM", command=self.show_about_dialog)
        menubar.add_cascade(label="Help", menu=m_help)
        self.root.config(menu=menubar)
        self.root.bind("<Control-n>", lambda e: self.open_add_url_dialog())
        self.root.bind("<Control-v>", lambda e: self.open_video_sniffer_window())
    def _build_header_banner(self):
        """Header Modern dengan Logo Vektor ArmIDM, Statistik Ringkas, Pencarian, dan Tombol Tema."""
        hdr = tk.Frame(self.root, bg="#0B1120", padx=14, pady=9)
        hdr.pack(fill=tk.X)
        # Logo Badge Vektor
        logo_cv = tk.Canvas(hdr, width=36, height=36, bg="#0B1120", highlightthickness=0)
        logo_cv.pack(side=tk.LEFT, padx=(0, 10))
        logo_cv.create_oval(2, 2, 34, 34, fill="#2563EB", outline="#60A5FA", width=1.5)
        logo_cv.create_polygon(18, 8, 18, 20, 12, 20, 18, 28, 24, 20, 18, 20, fill="#FFFFFF", outline="#FFFFFF")
        title_box = tk.Frame(hdr, bg="#0B1120")
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text="ArmIDM",
            bg="#0B1120",
            fg="#F8FAFC",
            font=("Segoe UI", 14, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text=f"v{APP_VERSION} ULTRA",
            bg="#1D4ED8",
            fg="#E0F2FE",
            font=("Segoe UI", 7, "bold"),
            padx=6,
            pady=1,
        ).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(
            title_box,
            text="Multi-Connection Accelerator & Video Sniffer",
            bg="#0B1120",
            fg="#94A3B8",
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(12, 0))
        # Kanan Header: Toggle Tema & Kotak Pencarian Cepat
        self.theme_btn = tk.Button(
            hdr,
            text=("☀️ Light Mode" if self.theme_mode == "dark" else "🌙 Dark Mode"),
            bg="#1E293B",
            fg="#F8FAFC",
            activebackground="#334155",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            padx=10,
            pady=4,
            cursor="hand2",
            command=self.toggle_theme,
        )
        self.theme_btn.pack(side=tk.RIGHT, padx=(8, 0))
        search_frame = tk.Frame(hdr, bg="#1E293B", padx=8, pady=3)
        search_frame.pack(side=tk.RIGHT, padx=6)
        tk.Label(search_frame, text="🔍", bg="#1E293B", fg="#94A3B8", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        search_ent = tk.Entry(
            search_frame,
            textvariable=self.search_query_var,
            bg="#1E293B",
            fg="#F8FAFC",
            insertbackground="#F8FAFC",
            relief="flat",
            width=24,
            font=("Segoe UI", 9),
        )
        search_ent.pack(side=tk.LEFT, padx=4)
        self.stats_pill_var = tk.StringVar(value="Active: 0  •  Done: 0")
        tk.Label(
            hdr,
            textvariable=self.stats_pill_var,
            bg="#1E293B",
            fg="#38BDF8",
            font=("Segoe UI", 8, "bold"),
            padx=10,
            pady=4,
        ).pack(side=tk.RIGHT, padx=6)
    def _build_toolbar(self):
        toolbar = ttk.Frame(self.root, padding=(10, 8))
        toolbar.pack(fill=tk.X)
        buttons = [
            ("add_url", "➕ Add URL", "Accent.TButton", self.open_add_url_dialog),
            ("resume", "▶ Resume", "Success.TButton", self.resume_selected),
            ("stop", "⏸ Pause", "Warning.TButton", self.pause_selected),
            ("stop_all", "⏹ Stop All", "Toolbar.TButton", self.core.pause_all),
            ("delete", "🗑 Delete", "Danger.TButton", self.delete_selected),
            ("clear_done", "🧹 Clear Done", "Toolbar.TButton", self.confirm_delete_completed),
            ("video_sniffer", "🎬 Videos (0)", "Purple.TButton", self.open_video_sniffer_window),
            ("scheduler", "⏰ Scheduler", "Toolbar.TButton", self.open_scheduler_dialog),
            ("start_queue", "▶ Start Queue", "Toolbar.TButton", self.core.start_queue),
            ("stop_queue", "⏹ Stop Queue", "Toolbar.TButton", self.core.stop_queue),
            ("options", "⚙ Options", "Toolbar.TButton", self.open_options_dialog),
            ("to_tray", "🔽 To Tray", "Toolbar.TButton", self.minimize_to_tray),
        ]
        self.toolbar_btns = {}
        for key, label, btn_style, cmd in buttons:
            btn = ttk.Button(toolbar, text=label, style=btn_style, command=cmd)
            btn.pack(side=tk.LEFT, padx=2)
            self.toolbar_btns[key] = btn
    def _build_speed_limiter_bar(self):
        bar = ttk.Frame(self.root, padding=(12, 4))
        bar.pack(fill=tk.X)
        self.intercept_var = tk.BooleanVar(value=self.core.config["intercept_browser"])
        ttk.Checkbutton(
            bar,
            text="🌐 Tangkap Unduhan Browser",
            variable=self.intercept_var,
            command=self._on_toggle_intercept,
        ).pack(side=tk.LEFT, padx=(0, 12))
        self.autostart_var = tk.BooleanVar(value=self.core.config.get("auto_startup", True))
        ttk.Checkbutton(
            bar,
            text="🚀 Auto-Run Saat PC Menyala",
            variable=self.autostart_var,
            command=self._on_toggle_autostart,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=6)
        self.speed_limit_var = tk.BooleanVar(value=self.core.config["speed_limit_enabled"])
        self.speed_kbps_var = tk.IntVar(value=self.core.config["speed_limit_kbps"])
        ttk.Checkbutton(
            bar,
            text="⚡ Speed Limiter Global:",
            variable=self.speed_limit_var,
            command=self._on_apply_speed_limit,
        ).pack(side=tk.LEFT, padx=(6, 6))
        ttk.Spinbox(
            bar,
            from_=10,
            to=200000,
            increment=128,
            textvariable=self.speed_kbps_var,
            width=7,
        ).pack(side=tk.LEFT)
        ttk.Label(bar, text="KB/s").pack(side=tk.LEFT, padx=(4, 6))
        ttk.Button(bar, text="Terapkan", style="Accent.TButton", command=self._on_apply_speed_limit).pack(side=tk.LEFT)
        # Mini Live Speed Sparkline Graph di sisi kanan
        spark_box = ttk.Frame(bar)
        spark_box.pack(side=tk.RIGHT, padx=(8, 0))
        self.live_speed_lbl = tk.StringVar(value="⚡ 0 KB/s")
        ttk.Label(spark_box, textvariable=self.live_speed_lbl, font=("Segoe UI", 9, "bold"), foreground="#38BDF8").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        self.spark_canvas = tk.Canvas(
            spark_box,
            width=125,
            height=24,
            bg=self.pal["seg_bg"],
            highlightthickness=1,
            highlightbackground=self.pal["border"],
        )
        self.spark_canvas.pack(side=tk.LEFT)
    def _build_main_panes(self):
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        # Panel Kiri: Tree Kategori & Antrean Modern
        left_frame = ttk.Frame(paned, width=195)
        paned.add(left_frame, weight=0)
        self.cat_tree = ttk.Treeview(left_frame, show="tree", selectmode="browse")
        self.cat_tree.pack(fill=tk.BOTH, expand=True)
        root_cat = self.cat_tree.insert("", tk.END, iid="cat_all", text=" 📂  All Downloads", open=True)
        for cat_name, icon in [
            ("Compressed", "🗜"),
            ("Documents", "📄"),
            ("Music", "🎵"),
            ("Programs", "⚙"),
            ("Video", "🎬"),
            ("General", "📦"),
        ]:
            self.cat_tree.insert(root_cat, tk.END, iid=f"cat_{cat_name}", text=f" {icon}  {cat_name}")
        self.cat_tree.insert("", tk.END, iid="status_Unfinished", text=" ⏳  Unfinished")
        self.cat_tree.insert("", tk.END, iid="status_Finished", text=" ✅  Finished")
        root_q = self.cat_tree.insert("", tk.END, iid="queues_root", text=" 📋  Queues", open=True)
        self.cat_tree.insert(root_q, tk.END, iid="queue_Main Queue", text=" 🕒  Main Queue")
        self.cat_tree.insert(root_q, tk.END, iid="queue_Scheduled Queue", text=" ⏰  Scheduled Queue")
        self.cat_tree.selection_set("cat_all")
        self.cat_tree.bind("<<TreeviewSelect>>", self._on_category_selected)
        # Panel Kanan: Tabel Daftar Unduhan Modern
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)
        cols = ("filename", "size", "status", "eta", "speed", "conns", "category", "added")
        self.dl_tree = ttk.Treeview(right_frame, columns=cols, show="headings", selectmode="extended")
        headings = [
            ("filename", "File Name", 285, "w"),
            ("size", "Size", 85, "e"),
            ("status", "Status & Progress", 145, "center"),
            ("eta", "Time Left", 85, "center"),
            ("speed", "Transfer Rate", 100, "e"),
            ("conns", "Conns", 65, "center"),
            ("category", "Category", 85, "center"),
            ("added", "Added Date", 130, "center"),
        ]
        for col_id, text, width, anchor in headings:
            self.dl_tree.heading(col_id, text=text)
            self.dl_tree.column(col_id, width=width, anchor=anchor)
        self._configure_table_tags()
        vsb = ttk.Scrollbar(right_frame, orient="vertical", command=self.dl_tree.yview)
        hsb = ttk.Scrollbar(right_frame, orient="horizontal", command=self.dl_tree.xview)
        self.dl_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.dl_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        right_frame.rowconfigure(0, weight=1)
        right_frame.columnconfigure(0, weight=1)
        self.dl_tree.bind("<Double-1>", lambda e: self.open_selected_progress_window())
        self.dl_tree.bind("<Button-3>", self._show_table_context_menu)
        self.dl_tree.bind("<Delete>", lambda e: self.delete_selected(with_file=False))
        self.ctx_menu = tk.Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(label="📊 Show Progress / Details", command=self.open_selected_progress_window)
        self.ctx_menu.add_command(label="📂 Open Downloaded File", command=self.open_selected_file)
        self.ctx_menu.add_command(label="📁 Open Containing Folder", command=self.open_selected_folder)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="▶ Resume Download", command=self.resume_selected)
        self.ctx_menu.add_command(label="⏸ Pause / Stop Download", command=self.pause_selected)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="🔗 Copy Download URL", command=self.copy_selected_url)
        self.ctx_menu.add_command(label="🗑 Delete from List", command=self.delete_selected)
        self.ctx_menu.add_command(label="🔥 Delete with File on Disk", command=lambda: self.delete_selected(with_file=True))
    def _configure_table_tags(self):
        p = self.pal
        self.dl_tree.tag_configure("even", background=p["tree_bg"])
        self.dl_tree.tag_configure("odd", background=p["tree_alt"])
        self.dl_tree.tag_configure("downloading", foreground=p["row_downloading"])
        self.dl_tree.tag_configure("complete", foreground=p["row_complete"])
        self.dl_tree.tag_configure("paused", foreground=p["row_paused"])
        self.dl_tree.tag_configure("error", foreground=p["row_error"])
    def _build_statusbar(self):
        status_frame = tk.Frame(self.root, bg="#0B1120", padx=12, pady=5)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_left_var = tk.StringVar(
            value=f"🟢 Local Server Active: http://127.0.0.1:{self.core.config['server_port']}  •  Ready for Chrome, Firefox, Edge, Brave & Opera"
        )
        self.status_right_var = tk.StringVar(value="Queue: Idle  |  Speed: 0 KB/s  |  Limiter: OFF")
        tk.Label(status_frame, textvariable=self.status_left_var, bg="#0B1120", fg="#94A3B8", font=("Segoe UI", 8)).pack(
            side=tk.LEFT
        )
        tk.Label(
            status_frame,
            textvariable=self.status_right_var,
            bg="#0B1120",
            fg="#38BDF8",
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.RIGHT)
    # ------------------------------------------------------------------------
    # EVENT HANDLERS & DIALOGS
    # ------------------------------------------------------------------------
    def _on_toggle_intercept(self):
        self.core.config["intercept_browser"] = self.intercept_var.get()
        self.core.save_config()
    def _on_toggle_autostart(self):
        enabled = bool(self.autostart_var.get())
        self.core.config["auto_startup"] = enabled
        self.core.save_config()
        StartupManager.set_enabled(enabled)
    def _on_close_window_request(self):
        if self.core.config.get("minimize_to_tray", True) and sys.platform.startswith("win"):
            self.minimize_to_tray(show_balloon=not self._tray_balloon_notified)
            self._tray_balloon_notified = True
        else:
            self.exit_application()
    def minimize_to_tray(self, show_balloon: bool = True):
        self.root.withdraw()
        if show_balloon and sys.platform.startswith("win"):
            self.tray_icon.show_balloon(
                "ArmIDM Berjalan di Latar Belakang",
                "ArmIDM tetap aktif di System Tray untuk menangkap unduhan & video dari Browser. Klik ikon ArmIDM di System Tray untuk membuka kembali.",
            )
    def restore_from_tray(self):
        try:
            self.root.deiconify()
            self.root.state("normal")
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass
    def exit_application(self):
        try:
            self.tray_icon.stop()
        except Exception:
            pass
        self.core.save_state()
        self.root.quit()
        self.root.destroy()
    def _on_tray_action(self, action: str):
        self.ui_event_queue.put(("tray_action", {"action": action}))
    def _on_apply_speed_limit(self):
        try:
            kbps = max(10, int(self.speed_kbps_var.get()))
        except Exception:
            kbps = 1024
        self.core.set_global_speed_limit(self.speed_limit_var.get(), kbps)
    def _on_category_selected(self, _event=None):
        sel = self.cat_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid == "cat_all":
            self.selected_filter = ("Category", "All Downloads")
        elif iid.startswith("cat_"):
            self.selected_filter = ("Category", iid[4:])
        elif iid.startswith("status_"):
            self.selected_filter = ("Status", iid[7:])
        elif iid.startswith("queue_"):
            self.selected_filter = ("Queue", iid[6:])
        else:
            self.selected_filter = ("Category", "All Downloads")
        self._refresh_table(full=True)
    def _task_matches_filter(self, task: DownloadTask) -> bool:
        q = self.search_query_var.get().strip().lower()
        if q and q not in task.filename.lower() and q not in task.category.lower():
            return False
        ftype, fval = self.selected_filter
        if ftype == "Category":
            return fval == "All Downloads" or task.category == fval
        if ftype == "Status":
            if fval == "Finished":
                return task.status == "Complete"
            return task.status != "Complete"
        if ftype == "Queue":
            return task.queue_name == fval
        return True
    def _get_row_tags(self, task: DownloadTask, row_idx: int) -> tuple:
        stripe = "even" if row_idx % 2 == 0 else "odd"
        st = task.status
        if st.startswith("Downloading") or st == "Connecting...":
            return (stripe, "downloading")
        if st == "Complete":
            return (stripe, "complete")
        if st == "Paused":
            return (stripe, "paused")
        if st.startswith("Error"):
            return (stripe, "error")
        return (stripe,)
    def _refresh_table(self, full: bool = False):
        if full:
            for item in self.dl_tree.get_children():
                self.dl_tree.delete(item)
        existing = set(self.dl_tree.get_children())
        visible_idx = 0
        for tid in self.core.task_order:
            t = self.core.tasks.get(tid)
            if not t or not self._task_matches_filter(t):
                if tid in existing:
                    self.dl_tree.delete(tid)
                continue
            if t.status.startswith("Downloading"):
                status_text = f"⬇ Downloading ({t.progress_percent:.1f}%)"
            elif t.status == "Complete":
                status_text = "✅ Complete (100%)"
            elif t.status == "Paused" and t.total_size > 0:
                status_text = f"⏸ Paused ({t.progress_percent:.1f}%)"
            elif t.status.startswith("Error"):
                status_text = "⚠ Error"
            else:
                status_text = t.status
            icon = CAT_ICONS.get(t.category, "📦")
            vals = (
                f"{icon}  {t.filename}",
                format_size(t.total_size),
                status_text,
                format_eta(t.eta_seconds) if t.status.startswith("Downloading") else "-",
                format_speed(t.transfer_rate) if t.status.startswith("Downloading") else "-",
                f"{t.active_connections_count}/{t.connections}",
                t.category,
                t.added_date,
            )
            tags = self._get_row_tags(t, visible_idx)
            visible_idx += 1
            if tid in existing:
                self.dl_tree.item(tid, values=vals, tags=tags)
            else:
                self.dl_tree.insert("", tk.END, iid=tid, values=vals, tags=tags)
    def _draw_sparkline(self, current_speed: float):
        self.speed_history.append(current_speed)
        if len(self.speed_history) > 40:
            self.speed_history.pop(0)
        if not hasattr(self, "spark_canvas") or not self.spark_canvas.winfo_exists():
            return
        cv = self.spark_canvas
        cv.delete("all")
        w = 125
        h = 24
        max_s = max(max(self.speed_history), 1024.0)
        pts = []
        step = w / max(1, len(self.speed_history) - 1)
        for i, val in enumerate(self.speed_history):
            x = i * step
            y = h - 3 - ((val / max_s) * (h - 6))
            pts.extend([x, y])
        if len(pts) >= 4:
            poly = [0, h] + pts + [w, h]
            cv.create_polygon(*poly, fill="#1E3A8A", outline="")
            cv.create_line(*pts, fill="#38BDF8", width=1.5)
    def _on_core_event(self, event_type: str, data: dict):
        self.ui_event_queue.put((event_type, data))
    def _periodic_ui_tick(self):
        while not self.ui_event_queue.empty():
            ev, data = self.ui_event_queue.get_nowait()
            if ev == "tray_action":
                act = data.get("action")
                if act == "restore":
                    self.restore_from_tray()
                elif act == "add_url":
                    self.open_add_url_dialog()
                elif act == "video_sniffer":
                    self.open_video_sniffer_window()
                elif act == "start_queue":
                    self.core.start_queue()
                elif act == "stop_queue":
                    self.core.stop_queue()
                elif act == "pause_all":
                    self.core.pause_all()
                elif act == "toggle_limit":
                    new_st = not self.core.config.get("speed_limit_enabled", False)
                    self.core.set_global_speed_limit(new_st, self.core.config.get("speed_limit_kbps", 1024))
                elif act == "exit":
                    self.exit_application()
                    return
            elif ev == "extension_download_request":
                self.open_add_url_dialog(prefill=data)
            elif ev == "task_started":
                tid = data.get("task_id")
                t = self.core.tasks.get(tid)
                if t and tid not in self.progress_windows:
                    self.progress_windows[tid] = ProgressDialogWindow(self.root, self.core, t)
            elif ev == "speed_limit_changed":
                self.speed_limit_var.set(data["enabled"])
                self.speed_kbps_var.set(data["rate_kbps"])
            elif ev == "intercept_changed":
                self.intercept_var.set(data["enabled"])
            elif ev == "task_completed":
                tid = data.get("task_id")
                pwin = self.progress_windows.pop(tid, None)
                if pwin and pwin.win.winfo_exists():
                    pwin.win.destroy()
                self._refresh_table(full=True)
                t = self.core.tasks.get(tid)
                if t:
                    if t.open_when_done:
                        launch_file_default(t.target_path)
                    elif self.core.config.get("show_complete_dialog", True) and t.show_complete_dialog:
                        self.complete_windows[tid] = DownloadCompleteDialog(self.root, self.core, t)
            elif ev in ("task_added", "task_deleted"):
                self._refresh_table(full=True)
        self._refresh_table(full=False)
        for tid, pwin in list(self.progress_windows.items()):
            if not pwin.win.winfo_exists():
                self.progress_windows.pop(tid, None)
            elif pwin.task.status == "Complete":
                pwin.win.destroy()
                self.progress_windows.pop(tid, None)
            else:
                pwin.refresh_ui()
        vid_btn = self.toolbar_btns.get("video_sniffer")
        if vid_btn:
            vid_btn.config(text=f"🎬 Videos ({len(self.core.detected_media)})")
        active_cnt = sum(1 for t in self.core.tasks.values() if t.status.startswith("Downloading") or t.status == "Connecting...")
        done_cnt = sum(1 for t in self.core.tasks.values() if t.status == "Complete")
        self.stats_pill_var.set(f"Active: {active_cnt}  •  Completed: {done_cnt}")
        total_speed = sum(t.transfer_rate for t in self.core.tasks.values() if t.status.startswith("Downloading"))
        self.live_speed_lbl.set(f"⚡ {format_speed(total_speed)}")
        self._draw_sparkline(total_speed)
        lim_str = f"ON ({self.core.config['speed_limit_kbps']} KB/s)" if self.core.config["speed_limit_enabled"] else "OFF"
        q_str = "Running" if self.core.queue_running else "Idle"
        self.status_right_var.set(f"Queue: {q_str}  |  Total Speed: {format_speed(total_speed)}  |  Speed Limiter: {lim_str}")
        self.root.after(400, self._periodic_ui_tick)
    # ------------------------------------------------------------------------
    # DIALOG "DOWNLOAD FILE INFO" MODERN (SAAT TAMBAH URL / DARI EXTENSION)
    # ------------------------------------------------------------------------
    def open_add_url_dialog(self, prefill: dict = None):
        prefill = prefill or {}
        req_url = (prefill.get("url") or "").strip()
        for k, existing_win in list(self.info_dialogs.items()):
            if not existing_win.winfo_exists():
                self.info_dialogs.pop(k, None)
        if req_url and req_url in self.info_dialogs:
            bring_window_to_front(self.info_dialogs[req_url], keep_topmost=True)
            return
        is_dark = self.theme_mode == "dark"
        dlg = tk.Toplevel(self.root)
        if req_url:
            self.info_dialogs[req_url] = dlg
        dlg.title("Download File Info - ArmIDM")
        center_window_on_screen(dlg, 610, 410)
        apply_window_icon(dlg, self.root, use_transient=False, is_dark=is_dark)
        bring_window_to_front(dlg, keep_topmost=True)
        # Header Banner Modern
        hdr = tk.Frame(dlg, bg="#0B1120", padx=16, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text="⬇  New Download File Information",
            bg="#0B1120",
            fg="#F8FAFC",
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        tk.Label(
            hdr,
            text="Multi-Segment Ready",
            bg="#2563EB",
            fg="#FFFFFF",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=2,
        ).pack(side=tk.RIGHT)
        frame = ttk.Frame(dlg, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        url_var = tk.StringVar(value=prefill.get("url", ""))
        fname_var = tk.StringVar(value=sanitize_filename(prefill.get("filename", "")))
        cat_var = tk.StringVar(value=prefill.get("category") or detect_category(fname_var.get() or url_var.get()))
        base_dir = pathlib.Path(self.core.config["default_download_dir"])
        save_dir_var = tk.StringVar(value=str(base_dir / CATEGORY_FOLDERS.get(cat_var.get(), "General")))
        conns_var = tk.IntVar(value=self.core.config["default_connections"])
        known_ext_size = int(prefill.get("file_size") or -1)
        size_lbl_var = tk.StringVar(
            value=(f"{format_size(known_ext_size)} (Verifying Range support...)" if known_ext_size > 0 else ("Probing size..." if url_var.get() else "Enter URL and click Check URL"))
        )
        headers_dict = dict(prefill.get("headers") or {})
        probed_size_holder = [known_ext_size]
        probed_resumable_holder = [known_ext_size > 0]
        ttk.Label(frame, text="Download URL:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        url_entry = ttk.Entry(frame, textvariable=url_var, width=54)
        url_entry.grid(row=0, column=1, sticky="ew", pady=5)
        def do_probe():
            u = url_var.get().strip()
            if not u:
                return
            size_lbl_var.set("Checking server headers & session cookies...")
            def bg_probe():
                info = self.core.probe_url(u, headers=headers_dict)
                def update_fields():
                    if info.get("url") and info["url"] != u:
                        url_var.set(info["url"])
                    if info.get("headers"):
                        headers_dict.update(info["headers"])
                    cur_fn = fname_var.get().strip()
                    url_basename = u.split("?")[0].split("/")[-1]
                    if (
                        not cur_fn
                        or cur_fn in ("download", "download_file", url_basename)
                        or (not pathlib.Path(cur_fn).suffix and pathlib.Path(info["filename"]).suffix)
                    ):
                        if info.get("filename") and info["filename"] not in ("download", "download_file"):
                            fname_var.set(info["filename"])
                    cat_var.set(info["category"])
                    save_dir_var.set(str(base_dir / CATEGORY_FOLDERS.get(info["category"], "General")))
                    if info.get("is_html_trap"):
                        if known_ext_size > 0:
                            size_lbl_var.set(f"{format_size(known_ext_size)} | Cookie Auth Active")
                        else:
                            size_lbl_var.set("⚠ HTML Page Detected (Reload Extension for Cookie Auth)")
                    else:
                        final_sz = info["total_size"] if info["total_size"] > 0 else known_ext_size
                        probed_size_holder[0] = final_sz
                        probed_resumable_holder[0] = info["resumable"]
                        r_txt = "Yes (Multi-Segment Ready)" if info["resumable"] else "Single Stream"
                        size_lbl_var.set(f"{format_size(final_sz)}  •  Resume: {r_txt}")
                dlg.after(0, update_fields)
            threading.Thread(target=bg_probe, daemon=True).start()
        ttk.Button(frame, text="🔍 Check URL", command=do_probe).grid(row=0, column=2, padx=(6, 0), pady=5)
        ttk.Label(frame, text="File Name:").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=fname_var, width=54).grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        ttk.Label(frame, text="Category:").grid(row=2, column=0, sticky="w", pady=5)
        cat_cb = ttk.Combobox(
            frame,
            textvariable=cat_var,
            values=["Compressed", "Documents", "Music", "Programs", "Video", "General"],
            state="readonly",
            width=25,
        )
        cat_cb.grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(frame, text="Save To Folder:").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Entry(frame, textvariable=save_dir_var, width=54).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Button(
            frame,
            text="📁 Browse...",
            command=lambda: save_dir_var.set(filedialog.askdirectory(initialdir=save_dir_var.get()) or save_dir_var.get()),
        ).grid(row=3, column=2, padx=(6, 0), pady=5)
        ttk.Label(frame, text="Parallel Connections:").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Spinbox(frame, from_=1, to=32, textvariable=conns_var, width=10).grid(row=4, column=1, sticky="w", pady=5)
        ttk.Label(frame, text="Server File Info:").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Label(
            frame,
            textvariable=size_lbl_var,
            foreground=self.pal["row_downloading"],
            font=("Segoe UI", 9, "bold"),
        ).grid(row=5, column=1, columnspan=2, sticky="w", pady=5)
        frame.columnconfigure(1, weight=1)
        btn_bar = ttk.Frame(frame)
        btn_bar.grid(row=6, column=0, columnspan=3, sticky="e", pady=(22, 0))
        def confirm(start_now: bool):
            u = url_var.get().strip()
            if not u:
                messagebox.showwarning("URL Kosong", "Masukkan URL unduhan terlebih dahulu.", parent=dlg)
                return
            dlg.destroy()
            self.core.create_task(
                url=u,
                filename=fname_var.get().strip(),
                save_dir=save_dir_var.get().strip(),
                category=cat_var.get(),
                connections=conns_var.get(),
                headers=headers_dict,
                total_size=probed_size_holder[0],
                resumable=probed_resumable_holder[0],
                start_immediately=start_now,
            )
        ttk.Button(btn_bar, text="▶ Start Download", style="Success.TButton", command=lambda: confirm(True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="🕒 Download Later (Queue)", style="Accent.TButton", command=lambda: confirm(False)).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT, padx=4)
        dlg.bind("<Return>", lambda e: confirm(True))
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.after(80, lambda: dlg.winfo_exists() and bring_window_to_front(dlg, keep_topmost=True))
        if url_var.get():
            do_probe()
    # ------------------------------------------------------------------------
    # JENDELA PENDETEKSI VIDEO (VIDEO SNIFFER / GRABBED VIDEOS)
    # ------------------------------------------------------------------------
    def open_video_sniffer_window(self):
        win = tk.Toplevel(self.root)
        win.title("🎬 ArmIDM Video Sniffer - Video & Media Terdeteksi dari Browser")
        win.geometry("880x460")
        apply_window_icon(win, self.root, is_dark=(self.theme_mode == "dark"))
        hdr = tk.Frame(win, bg="#0B1120", padx=16, pady=10)
        hdr.pack(fill=tk.X)
        tk.Label(
            hdr,
            text="🎬  ArmIDM Video & Media Stream Sniffer",
            bg="#0B1120",
            fg="#F8FAFC",
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        cols = ("time", "page_title", "filename", "quality", "mime", "size", "url")
        tree = ttk.Treeview(win, columns=cols, show="headings", selectmode="browse")
        tree.heading("time", text="Waktu")
        tree.heading("page_title", text="Judul Halaman")
        tree.heading("filename", text="Nama File Video")
        tree.heading("quality", text="Kualitas/Tipe")
        tree.heading("mime", text="Format MIME")
        tree.heading("size", text="Ukuran")
        tree.heading("url", text="Stream URL")
        tree.column("time", width=70, anchor="center")
        tree.column("page_title", width=180, anchor="w")
        tree.column("filename", width=165, anchor="w")
        tree.column("quality", width=95, anchor="center")
        tree.column("mime", width=110, anchor="center")
        tree.column("size", width=85, anchor="e")
        tree.column("url", width=220, anchor="w")
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        def populate():
            for item in tree.get_children():
                tree.delete(item)
            for idx, m in enumerate(self.core.detected_media):
                tree.insert(
                    "",
                    tk.END,
                    iid=str(idx),
                    values=(
                        m.get("detected_at", ""),
                        m.get("page_title", ""),
                        m.get("filename", ""),
                        m.get("quality", ""),
                        m.get("mime_type", ""),
                        format_size(m.get("size", -1)),
                        m.get("url", ""),
                    ),
                )
        populate()
        btn_bar = ttk.Frame(win, padding=10)
        btn_bar.pack(fill=tk.X)
        def download_selected_video():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Pilih Video", "Pilih salah satu stream video pada tabel terlebih dahulu.", parent=win)
                return
            idx = int(sel[0])
            if 0 <= idx < len(self.core.detected_media):
                m = self.core.detected_media[idx]
                self.open_add_url_dialog(prefill={
                    "url": m["url"],
                    "filename": m["filename"],
                    "category": "Video",
                    "headers": m.get("headers", {}),
                })
        ttk.Button(btn_bar, text="⬇ Download Video Terpilih", style="Success.TButton", command=download_selected_video).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_bar, text="🔄 Refresh", style="Accent.TButton", command=populate).pack(side=tk.LEFT, padx=4)
        ttk.Button(
            btn_bar,
            text="🧹 Bersihkan Daftar",
            style="Danger.TButton",
            command=lambda: (self.core.detected_media.clear(), populate()),
        ).pack(side=tk.LEFT, padx=4)
    # ------------------------------------------------------------------------
    # DIALOG SCHEDULER & OPTIONS
    # ------------------------------------------------------------------------
    def open_scheduler_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("⏰ Scheduler & Queue Manager - ArmIDM")
        dlg.geometry("460x300")
        apply_window_icon(dlg, self.root, is_dark=(self.theme_mode == "dark"))
        f = ttk.Frame(dlg, padding=16)
        f.pack(fill=tk.BOTH, expand=True)
        sched_en = tk.BooleanVar(value=self.core.config.get("schedule_enabled", False))
        start_t = tk.StringVar(value=self.core.config.get("schedule_start_time", "01:00"))
        stop_t = tk.StringVar(value=self.core.config.get("schedule_stop_time", "06:00"))
        max_c = tk.IntVar(value=self.core.config.get("max_concurrent_downloads", 3))
        ttk.Checkbutton(f, text="Aktifkan Penjadwalan Antrean Otomatis (Scheduler)", variable=sched_en).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(f, text="Waktu Mulai Antrean (HH:MM):").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(f, textvariable=start_t, width=12).grid(row=1, column=1, sticky="w", pady=5)
        ttk.Label(f, text="Waktu Berhenti Antrean (HH:MM):").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(f, textvariable=stop_t, width=12).grid(row=2, column=1, sticky="w", pady=5)
        ttk.Label(f, text="Maksimum Unduhan Bersamaan di Antrean:").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Spinbox(f, from_=1, to=16, textvariable=max_c, width=10).grid(row=3, column=1, sticky="w", pady=5)
        def save_sched():
            self.core.config["schedule_enabled"] = sched_en.get()
            self.core.config["schedule_start_time"] = start_t.get().strip()
            self.core.config["schedule_stop_time"] = stop_t.get().strip()
            self.core.config["max_concurrent_downloads"] = max(1, int(max_c.get()))
            self.core.save_config()
            dlg.destroy()
        btn_row = ttk.Frame(f)
        btn_row.grid(row=4, column=0, columnspan=2, pady=(20, 0), sticky="e")
        ttk.Button(btn_row, text="▶ Start Queue Now", style="Success.TButton", command=lambda: (self.core.start_queue(), save_sched())).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_row, text="Save Schedule", style="Accent.TButton", command=save_sched).pack(side=tk.LEFT, padx=4)
    def open_options_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("⚙ ArmIDM Options & Configuration")
        dlg.geometry("600x420")
        apply_window_icon(dlg, self.root, is_dark=(self.theme_mode == "dark"))
        f = ttk.Frame(dlg, padding=16)
        f.pack(fill=tk.BOTH, expand=True)
        dl_dir = tk.StringVar(value=self.core.config["default_download_dir"])
        def_conns = tk.IntVar(value=self.core.config["default_connections"])
        exts_var = tk.StringVar(value=", ".join(self.core.config["intercept_extensions"]))
        auto_start_opt = tk.BooleanVar(value=self.core.config.get("auto_startup", True))
        min_tray_opt = tk.BooleanVar(value=self.core.config.get("minimize_to_tray", True))
        show_comp_opt = tk.BooleanVar(value=self.core.config.get("show_complete_dialog", True))
        ttk.Label(f, text="Folder Unduhan Utama:").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Entry(f, textvariable=dl_dir, width=42).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(
            f,
            text="Browse...",
            command=lambda: dl_dir.set(filedialog.askdirectory(initialdir=dl_dir.get()) or dl_dir.get()),
        ).grid(row=0, column=2, padx=4)
        ttk.Label(f, text="Jumlah Koneksi Default (1-32):").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Spinbox(f, from_=1, to=32, textvariable=def_conns, width=10).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(f, text="Ekstensi File yang Diintersepsi:").grid(row=2, column=0, sticky="nw", pady=6)
        ttk.Entry(f, textvariable=exts_var, width=42).grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Checkbutton(
            f,
            text="🚀 Jalankan ArmIDM otomatis saat komputer dinyalakan (Start with Windows in System Tray)",
            variable=auto_start_opt,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(
            f,
            text="📥 Minimize ke System Tray saat tombol Close (X) ditekan",
            variable=min_tray_opt,
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(
            f,
            text="✅ Tampilkan dialog notifikasi 'Download complete' saat unduhan selesai",
            variable=show_comp_opt,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=4)
        def save_opts():
            self.core.config["default_download_dir"] = dl_dir.get().strip()
            self.core.config["default_connections"] = max(1, min(32, int(def_conns.get())))
            self.core.config["intercept_extensions"] = [
                x.strip().lower() for x in exts_var.get().split(",") if x.strip()
            ]
            self.core.config["auto_startup"] = bool(auto_start_opt.get())
            self.core.config["minimize_to_tray"] = bool(min_tray_opt.get())
            self.core.config["show_complete_dialog"] = bool(show_comp_opt.get())
            self.autostart_var.set(self.core.config["auto_startup"])
            StartupManager.set_enabled(self.core.config["auto_startup"])
            self.core.save_config()
            dlg.destroy()
        ttk.Button(f, text="💾 Simpan Pengaturan", style="Success.TButton", command=save_opts).grid(
            row=7, column=1, columnspan=2, sticky="e", pady=16
        )
    # ------------------------------------------------------------------------
    # AKSI BARIS TABEL
    # ------------------------------------------------------------------------
    def _get_selected_ids(self) -> list[str]:
        return list(self.dl_tree.selection())
    def resume_selected(self):
        for tid in self._get_selected_ids():
            self.core.start_task(tid)
    def pause_selected(self):
        for tid in self._get_selected_ids():
            self.core.pause_task(tid)
    def delete_selected(self, with_file: bool = False):
        sel = self._get_selected_ids()
        if not sel:
            messagebox.showinfo(
                "Pilih Item Unduhan",
                "Pilih salah satu atau beberapa item unduhan pada tabel yang ingin dihapus terlebih dahulu.",
                parent=self.root,
            )
            return
        selected_tasks = [self.core.tasks[tid] for tid in sel if tid in self.core.tasks]
        if not selected_tasks:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Delete File(s) Confirmation - ArmIDM")
        center_window_on_screen(dlg, 520, 245)
        dlg.resizable(False, False)
        apply_window_icon(dlg, self.root, use_transient=True, is_dark=(self.theme_mode == "dark"))
        bring_window_to_front(dlg, keep_topmost=True)
        try:
            dlg.grab_set()
        except Exception:
            pass
        main_f = ttk.Frame(dlg, padding=(16, 14, 16, 14))
        main_f.pack(fill=tk.BOTH, expand=True)
        top_row = ttk.Frame(main_f)
        top_row.pack(fill=tk.X, pady=(0, 10))
        ic = tk.Canvas(top_row, width=48, height=48, bg=self.pal["bg_root"], highlightthickness=0)
        ic.pack(side=tk.LEFT, padx=(0, 12))
        ic.create_oval(4, 4, 44, 44, fill="#FEE2E2", outline="#DC2626", width=2)
        ic.create_rectangle(16, 17, 32, 36, fill="#EF4444", outline="#B91C1C", width=1)
        ic.create_line(13, 14, 35, 14, fill="#B91C1C", width=3)
        ic.create_line(21, 11, 27, 11, fill="#B91C1C", width=3)
        ic.create_line(21, 21, 21, 32, fill="#FFFFFF", width=2)
        ic.create_line(27, 21, 27, 32, fill="#FFFFFF", width=2)
        txt_frame = ttk.Frame(top_row)
        txt_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if len(selected_tasks) == 1:
            t0 = selected_tasks[0]
            title_msg = "Apakah Anda yakin ingin menghapus item ini dari daftar?"
            sub_msg = f"📄 {t0.filename[:58]} ({t0.status} • {format_size(t0.total_size)})"
        else:
            title_msg = f"Apakah Anda yakin ingin menghapus {len(selected_tasks)} item terpilih dari daftar?"
            sub_msg = f"📄 {selected_tasks[0].filename[:42]} dan {len(selected_tasks) - 1} file lainnya"
        ttk.Label(
            txt_frame,
            text=title_msg,
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            txt_frame,
            text=sub_msg,
            font=("Segoe UI", 9),
            foreground=self.pal["row_downloading"],
        ).pack(anchor="w", pady=(4, 0))
        ttk.Separator(main_f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 10))
        del_disk_var = tk.BooleanVar(value=bool(with_file))
        ttk.Checkbutton(
            main_f,
            text="Hapus juga file yang sudah selesai dari Hard Disk (Folder Downloads)",
            variable=del_disk_var,
        ).pack(anchor="w", pady=(0, 4))
        ttk.Label(
            main_f,
            text="*Potongan file sementara (.part) yang belum selesai akan selalu dibersihkan otomatis.",
            font=("Segoe UI", 8),
            foreground=self.pal["fg_secondary"],
        ).pack(anchor="w", pady=(0, 10))
        btn_bar = ttk.Frame(main_f)
        btn_bar.pack(side=tk.BOTTOM, fill=tk.X)
        def do_confirm_delete():
            delete_from_disk = bool(del_disk_var.get())
            dlg.destroy()
            for tid in sel:
                pwin = self.progress_windows.pop(tid, None)
                if pwin and pwin.win.winfo_exists():
                    pwin.win.destroy()
                cwin = self.complete_windows.pop(tid, None)
                if cwin and cwin.win.winfo_exists():
                    cwin.win.destroy()
                self.core.delete_task(tid, delete_file=delete_from_disk)
        btn_ok = ttk.Button(btn_bar, text="🗑 Hapus (Delete)", width=16, style="Danger.TButton", command=do_confirm_delete)
        btn_ok.pack(side=tk.RIGHT, padx=(6, 0))
        btn_cancel = ttk.Button(btn_bar, text="Batal (Cancel)", width=14, command=dlg.destroy)
        btn_cancel.pack(side=tk.RIGHT)
        dlg.bind("<Return>", lambda e: do_confirm_delete())
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        btn_ok.focus_set()
    def confirm_delete_completed(self):
        completed_ids = [tid for tid, t in self.core.tasks.items() if t.status == "Complete"]
        if not completed_ids:
            messagebox.showinfo(
                "Tidak Ada Unduhan Selesai",
                "Belum ada item berstatus Complete di daftar tabel.",
                parent=self.root,
            )
            return
        ans = messagebox.askyesno(
            "Konfirmasi Clear Completed - ArmIDM",
            f"Apakah Anda yakin ingin menghapus {len(completed_ids)} riwayat unduhan yang sudah selesai (Complete) dari daftar tabel?\n\n"
            "(File asli di folder Downloads Anda tetap aman dan TIDAK akan dihapus.)",
            parent=self.root,
        )
        if ans:
            self.core.delete_completed()
    def open_selected_progress_window(self):
        sel = self._get_selected_ids()
        if not sel:
            return
        tid = sel[0]
        t = self.core.tasks.get(tid)
        if not t:
            return
        if t.status == "Complete":
            if tid in self.complete_windows and self.complete_windows[tid].win.winfo_exists():
                self.complete_windows[tid].win.lift()
            else:
                self.complete_windows[tid] = DownloadCompleteDialog(self.root, self.core, t)
            return
        if tid in self.progress_windows and self.progress_windows[tid].win.winfo_exists():
            self.progress_windows[tid].win.lift()
        else:
            self.progress_windows[tid] = ProgressDialogWindow(self.root, self.core, t)
    def open_selected_file(self):
        sel = self._get_selected_ids()
        if not sel:
            return
        t = self.core.tasks.get(sel[0])
        if t:
            launch_file_default(t.target_path)
    def open_selected_folder(self):
        sel = self._get_selected_ids()
        if not sel:
            return
        t = self.core.tasks.get(sel[0])
        if t:
            launch_open_folder_select(t.target_path, t.save_dir)
    def copy_selected_url(self):
        sel = self._get_selected_ids()
        if not sel:
            return
        t = self.core.tasks.get(sel[0])
        if t:
            self.root.clipboard_clear()
            self.root.clipboard_append(t.url)
    def _show_table_context_menu(self, event):
        row_id = self.dl_tree.identify_row(event.y)
        if row_id:
            if row_id not in self.dl_tree.selection():
                self.dl_tree.selection_set(row_id)
            self.ctx_menu.tk_popup(event.x_root, event.y_root)
    def show_extension_guide(self):
        messagebox.showinfo(
            "Panduan Pasang Browser Extension ArmIDM",
            "Cara Memasang Ekstensi Browser ArmIDM:\n\n"
            "• Chrome / Edge / Brave / Opera:\n"
            "  1. Buka chrome://extensions\n"
            "  2. Aktifkan Developer mode di pojok kanan atas.\n"
            "  3. Klik Load unpacked dan pilih folder chrome_extension.\n\n"
            "• Mozilla Firefox:\n"
            "  1. Buka about:debugging#/runtime/this-firefox\n"
            "  2. Klik Load Temporary Add-on... dan pilih file armidm_firefox.xpi.",
        )
    def show_about_dialog(self):
        messagebox.showinfo(
            "About ArmIDM",
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "100% Free & Open Source Download Manager (Tanpa Lisensi / Tanpa Trial).\n"
            "Fitur Modern v3.0:\n"
            "• Modern Fluent Dark & Light Theme + Live Speed Sparkline Graph\n"
            "• Multi-connection Segmented Accelerator (hingga 32 koneksi)\n"
            "• Pause & Resume kapan saja\n"
            "• Real-time Token-Bucket Speed Limiter\n"
            "• Multi-Browser Extension & YouTube Multi-Resolution Video Sniffer",
        )
    def run(self):
        self.root.mainloop()

# ============================================================================
# ENTRY POINT
# ============================================================================
def main():
    core = DownloadManagerCore()
    server = LocalIDMServer(core, port=core.config.get("server_port", DEFAULT_PORT))
    server.start()
    if "--headless" in sys.argv or not TKINTER_AVAILABLE:
        print(f"[{APP_NAME}] Berjalan dalam mode Headless Server di http://127.0.0.1:{server.port}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.stop()
    else:
        start_minimized = ("--tray" in sys.argv) or ("--minimized" in sys.argv)
        gui = ArmIDMDesktopGUI(core, start_in_tray=start_minimized)
        gui.run()
        server.stop()

if __name__ == "__main__":
    main()
