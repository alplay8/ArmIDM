// ==UserScript==
// @name         ArmIDM Universal Integration & Video Grabber
// @namespace    http://127.0.0.1:16888/
// @version      2.6.0
// @description  Integrasi Universal ArmIDM untuk semua browser (Safari, Firefox, Opera, Vivaldi, Edge, dll.): tombol floating Download Video & klik tautan unduhan langsung ke ArmIDM Desktop.
// @author       ArmIDM Open Source
// @match        *://*/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

(function() {
  'use strict';
  const PYIDM_HTTP_BASE = "http://127.0.0.1:16888";
  const EXT_LIST = [".zip", ".rar", ".7z", ".tar", ".gz", ".exe", ".msi", ".dmg", ".iso", ".apk", ".mp4", ".mkv", ".webm", ".mp3", ".flac", ".pdf", ".nsp", ".xci"];

  async function sendToArmIDM(url, filename, category = "") {
    try {
      const resp = await fetch(`${PYIDM_HTTP_BASE}/api/add_download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: url,
          filename: filename || "",
          category: category,
          headers: {
            "Referer": location.href,
            "User-Agent": navigator.userAgent,
            "Cookie": document.cookie || ""
          },
          description: `From ${document.title}`,
          show_dialog: true
        })
      });
      return resp.ok;
    } catch (e) {
      return false;
    }
  }

  // Tangkap klik pada tautan unduhan jika tombol Alt ditekan atau ekstensi cocok
  document.addEventListener("click", async (e) => {
    const a = e.target.closest("a[href]");
    if (!a) return;
    const href = a.href || "";
    if (!href.startsWith("http")) return;
    const clean = href.split("?")[0].toLowerCase();
    if (e.altKey || EXT_LIST.some((ext) => clean.endsWith(ext))) {
      const ok = await sendToArmIDM(href, a.download || "");
      if (ok) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
  }, true);
})();
