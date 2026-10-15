# 🚀 ArmIDM - Open Source Internet Download Manager & Multi-Browser Extension

**ArmIDM** adalah aplikasi *Download Manager* desktop berbasis Python (Tkinter/TTK) dengan tata letak dan fitur lengkap layaknya **Internet Download Manager (IDM)** tanpa lisensi/batasan *trial*, dilengkapi ekstensi browser untuk **Google Chrome, Mozilla Firefox, Microsoft Edge, Brave, Opera, dan Vivaldi**.

---

## ✨ Fitur Utama

- **⚡ Multi-Connection Dynamic Segmented Downloader (1–32 Koneksi)**: Memecah unduhan menjadi beberapa segmen paralel (*HTTP Byte-Range*) dengan visualisasi bar segmen biru secara *real-time*.
- **⏯ Pause & Resume Kapan Saja**: Menyimpan *state* setiap segmen secara persisten di `~/.armidm/` sehingga unduhan dapat dilanjutkan kapan pun.
- **🚦 Real-Time Speed Limiter (Token Bucket)**: Pembatas kecepatan unduhan global maupun per-file dalam satuan `KB/s`.
- **🎬 Video Sniffer & YouTube Multi-Resolusi**: Menampilkan tombol melayang **"⬇ Download Video Ini (ArmIDM)"** di atas pemutar video web (termasuk YouTube *Watch* & *Shorts* pada resolusi 1080p, 720p, 480p, 360p, dan Audio Only, serta stream HLS `.m3u8`).
- **🍪 Dukungan Cookie & Sesi Otomatis**: Meneruskan *Cookie* autentikasi dan *Referer* dari browser secara otomatis untuk mengunduh dari situs penyimpanan seperti **Gofile.io**, **VikingFile**, **MediaFire**, dan **Pixeldrain**.
- **📥 Native Windows System Tray & Auto-Run Startup**: Berjalan otomatis di *System Tray* saat komputer dinyalakan tanpa memerlukan pustaka eksternal tambahan.

---

## 📂 Struktur Proyek

| File / Folder | Deskripsi |
| :--- | :--- |
| `armidm.py` | Kode sumber utama aplikasi desktop Python (GUI, Download Engine, Local Server HTTP/WebSocket `127.0.0.1:16888`, System Tray, dan YouTube Engine). |
| `chrome_extension/` | Ekstensi Manifest V3 untuk **Google Chrome, Microsoft Edge, Brave, Opera, dan Vivaldi**. |
| `firefox_extension/` & `armidm_firefox.xpi` | Ekstensi Manifest V2 (`webRequestBlocking`) untuk **Mozilla Firefox, Zen Browser, LibreWolf, dan Waterfox**. |
| ` armidm_universal.user.js` | *Userscript* universal untuk *Tampermonkey / Violentmonkey* di browser lainnya. |
| `build_exe_windows.bat` | Skrip kompilasi 1-klik untuk membungkus `armidm.py` menjadi file mandiri **`ArmIDM.exe`**. |
| `.github/workflows/build_exe.yml` | Workflow *GitHub Actions* untuk mem-build `ArmIDM.exe` secara otomatis di *cloud* setiap kali ada *push*. |

---

## 🛠️ Cara Menjalankan & Build `.EXE`

### 1. Menjalankan Langsung dengan Python
```bash
python armidm.py
```

### 2. Membuat File Mandiri `ArmIDM.exe` di Windows
Klik ganda file **`build_exe_windows.bat`**, atau jalankan perintah berikut:
```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --clean --name "ArmIDM" --icon "armidm.ico" armidm.py
```

---

## 🌐 Cara Memasang Ekstensi Browser

- **Google Chrome / Edge / Brave / Opera**: Buka `chrome://extensions` → Aktifkan **Developer mode** → Klik **Load unpacked** → Pilih folder `chrome_extension`.
- **Mozilla Firefox**: Buka `about:debugging#/runtime/this-firefox` → Klik **Load Temporary Add-on...** → Pilih file `manifest.json` di dalam folder `firefox_extension` (atau pasang `armidm_firefox.xpi`).
