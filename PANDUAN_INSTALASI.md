# ArmIDM - Aplikasi Download Manager & Multi-Browser Extension (Tanpa Lisensi)

Aplikasi **ArmIDM** dirancang dengan tata letak dan fitur lengkap layaknya **Internet Download Manager (IDM)** serta mendukung integrasi lintas browser (**Mozilla Firefox**, **Google Chrome**, **Microsoft Edge**, **Brave**, **Opera / Opera GX**, **Vivaldi**, **Zen Browser**, dan **LibreWolf**) melalui server lokal `127.0.0.1:16888`.

## Daftar Folder & File Ekstensi Browser di Dalam Paket

| Folder / File Ekstensi | Browser yang Didukung |
| :--- | :--- |
| `firefox_extension/` & `armidm_firefox.xpi` | **Mozilla Firefox**, **Zen Browser**, **LibreWolf**, **Waterfox**, dan **Floorp**. |
| `chrome_extension/` | **Google Chrome**, **Microsoft Edge**, **Brave Browser**, **Opera / Opera GX**, dan **Vivaldi**. |
| `armidm_universal.user.js` | **Safari**, **Maxthon**, **Pale Moon**, dan semua browser yang memiliki ekstensi *Tampermonkey* / *Violentmonkey*. |

## 1. Cara Memasang di Mozilla Firefox (dan Turunannya)

Ada dua cara mudah untuk memasang ekstensi ArmIDM di Mozilla Firefox:

* **Cara A — Melalui Menu Debugging Resmi Firefox (Berlaku di Semua Versi Firefox)**:
  1. Buka Mozilla Firefox, ketik **`about:debugging#/runtime/this-firefox`** di bilah alamat, lalu tekan **Enter**.
  2. Klik tombol **Load Temporary Add-on...** (*Muat Pengaya Sementara...*).
  3. Masuk ke folder `firefox_extension` dan pilih file **`manifest.json`** (atau pilih file **`armidm_firefox.xpi`**).
* **Cara B — Pemasangan Permanen File `armidm_firefox.xpi` (Untuk Firefox Developer / ESR / LibreWolf / Waterfox)**:
  1. Buka **`about:config`** di Firefox, cari **`xpinstall.signatures.required`**, lalu ubah nilainya menjadi **`false`**.
  2. Buka **`about:addons`**, klik ikon gerigi (⚙) di pojok kanan atas, pilih **Install Add-on From File...**, lalu pilih file **`armidm_firefox.xpi`**.

## 2. Cara Memasang di Google Chrome, Microsoft Edge, Brave, Opera, & Vivaldi

Semua browser berbasis Chromium menggunakan folder **`chrome_extension`** dengan langkah yang sama:

* **Google Chrome**: Buka `chrome://extensions` → Aktifkan **Developer mode** → Klik **Load unpacked** → Pilih folder `chrome_extension`.
* **Microsoft Edge**: Buka `edge://extensions` → Aktifkan **Developer mode** (di menu kiri) → Klik **Load unpacked** → Pilih folder `chrome_extension`.
* **Brave Browser**: Buka `brave://extensions` → Aktifkan **Developer mode** → Klik **Load unpacked** → Pilih folder `chrome_extension`.
* **Opera / Opera GX**: Buka `opera://extensions` → Aktifkan **Developer mode** → Klik **Load unpacked** → Pilih folder `chrome_extension`.
* **Vivaldi**: Buka `vivaldi://extensions` → Aktifkan **Developer mode** → Klik **Load unpacked** → Pilih folder `chrome_extension`.

## 3. Cara Memasang di Browser Lain (Safari, dll. via Tampermonkey)

1. Pasang ekstensi *Tampermonkey* atau *Violentmonkey* di browser Anda.
2. Buka *Dashboard* Tampermonkey → tab **Utilities** → **Import from file**, lalu pilih file **`armidm_universal.user.js`**.
