// ArmIDM Content Script v3.0 - Modern Floating Video Downloader + YouTube Multi-Quality Support
(() => {
  const extApi = typeof chrome !== "undefined" ? chrome : browser;
  let detectedMedia = [];
  let panelHiddenByUser = false;
  let containerEl = null;
  let dropdownOpen = false;
  let lastYouTubeUrl = "";

  const INLINE_CSS = `
    #armidm-floating-container, #pyidm-floating-container {
      position: fixed !important;
      top: 16px;
      right: 16px;
      z-index: 2147483647 !important;
      font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif !important;
      font-size: 12px !important;
      line-height: 1.4 !important;
      user-select: none !important;
      pointer-events: auto !important;
      filter: drop-shadow(0 8px 20px rgba(0, 0, 0, 0.45));
    }
    .armidm-main-btn {
      display: inline-flex !important;
      align-items: center !important;
      gap: 8px !important;
      background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 50%, #2563eb 100%) !important;
      color: #f8fafc !important;
      padding: 7px 14px !important;
      border-radius: 999px !important;
      border: 1px solid rgba(96, 165, 250, 0.55) !important;
      box-shadow: 0 4px 16px rgba(15, 23, 42, 0.65) !important;
      cursor: pointer !important;
      font-weight: 600 !important;
      font-size: 12px !important;
      backdrop-filter: blur(10px) !important;
      transition: all 0.18s ease !important;
    }
    .armidm-main-btn:hover {
      background: linear-gradient(135deg, #1e293b 0%, #1d4ed8 50%, #3b82f6 100%) !important;
      border-color: rgba(147, 197, 253, 0.9) !important;
      transform: translateY(-1px) !important;
    }
    .armidm-badge {
      background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
      color: #ffffff !important;
      font-weight: 700 !important;
      padding: 1px 7px !important;
      border-radius: 999px !important;
      font-size: 11px !important;
    }
    .armidm-close-x {
      margin-left: 2px !important;
      opacity: 0.75 !important;
      font-weight: bold !important;
      padding: 1px 5px !important;
      border-radius: 50% !important;
      color: #cbd5e1 !important;
    }
    .armidm-close-x:hover {
      opacity: 1 !important;
      background: rgba(239, 68, 68, 0.25) !important;
      color: #fca5a5 !important;
    }
    .armidm-dropdown {
      margin-top: 8px !important;
      background: rgba(15, 23, 42, 0.96) !important;
      color: #f8fafc !important;
      border: 1px solid rgba(51, 65, 85, 0.95) !important;
      border-radius: 12px !important;
      box-shadow: 0 12px 32px rgba(0, 0, 0, 0.65) !important;
      width: 345px !important;
      max-height: 295px !important;
      overflow-y: auto !important;
      display: none !important;
      backdrop-filter: blur(12px) !important;
      padding: 4px 0 !important;
    }
    .armidm-dropdown.open {
      display: block !important;
    }
    .armidm-stream-item {
      display: flex !important;
      justify-content: space-between !important;
      align-items: center !important;
      padding: 9px 13px !important;
      border-bottom: 1px solid rgba(30, 41, 59, 0.85) !important;
      cursor: pointer !important;
      transition: background 0.15s ease !important;
    }
    .armidm-stream-item:last-child {
      border-bottom: none !important;
    }
    .armidm-stream-item:hover {
      background: rgba(37, 99, 235, 0.25) !important;
    }
    .armidm-stream-title {
      font-weight: 600 !important;
      color: #f1f5f9 !important;
      white-space: nowrap !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      max-width: 190px !important;
      font-size: 12px !important;
    }
    .armidm-stream-meta {
      font-size: 11px !important;
      color: #38bdf8 !important;
      font-weight: 600 !important;
      background: rgba(56, 189, 248, 0.14) !important;
      padding: 2px 7px !important;
      border-radius: 6px !important;
      white-space: nowrap !important;
    }
  `;

  function ensureInlineStyles() {
    if (!document.getElementById("armidm-inline-styles")) {
      const styleEl = document.createElement("style");
      styleEl.id = "armidm-inline-styles";
      styleEl.textContent = INLINE_CSS;
      (document.head || document.documentElement).appendChild(styleEl);
    }
  }

  function formatBytes(bytes) {
    if (!bytes || bytes < 0) return "Ready";
    const units = ["B", "KB", "MB", "GB"];
    let i = 0;
    let val = bytes;
    while (val >= 1024 && i < units.length - 1) {
      val /= 1024;
      i++;
    }
    return `${val.toFixed(1)} ${units[i]}`;
  }

  function cleanVideoTitle(rawTitle) {
    return (rawTitle || "Video")
      .replace(/^\(\d+\)\s*/, "")
      .replace(/\s*-\s*YouTube$/i, "")
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
      .trim()
      .slice(0, 80) || "Video";
  }

  function isYouTubeVideoPage() {
    const host = location.hostname.toLowerCase();
    if (!host.includes("youtube.com")) return false;
    return location.pathname.startsWith("/watch") || location.pathname.startsWith("/shorts/");
  }

  function buildYouTubeQualityStreams() {
    const cleanUrl = location.href.split("&list=")[0];
    const title = cleanVideoTitle(document.title);
    const qualities = [
      { label: "🎬 1080p Full HD", fmt: "1080p", ext: "mp4" },
      { label: "🎬 720p HD", fmt: "720p", ext: "mp4" },
      { label: "🎬 480p SD", fmt: "480p", ext: "mp4" },
      { label: "🎬 360p Fast", fmt: "360p", ext: "mp4" },
      { label: "🎵 Audio Only (M4A)", fmt: "audio", ext: "m4a" }
    ];
    return qualities.map((q) => ({
      id: `yt_${q.fmt}_${btoa(cleanUrl).slice(0, 10)}`,
      url: `${cleanUrl}#pyidm_quality=${q.fmt}`,
      filename: `${title} [${q.fmt}].${q.ext}`,
      page_title: title,
      page_url: cleanUrl,
      mime_type: q.ext === "m4a" ? "audio/mp4" : "video/mp4",
      size: -1,
      quality: q.label,
      headers: {
        "Referer": cleanUrl,
        "User-Agent": navigator.userAgent
      }
    }));
  }

  function ensureFloatingPanel() {
    ensureInlineStyles();
    if (panelHiddenByUser || detectedMedia.length === 0) {
      if (containerEl) containerEl.style.display = "none";
      return;
    }

    if (!containerEl) {
      containerEl = document.createElement("div");
      containerEl.id = "armidm-floating-container";
      document.documentElement.appendChild(containerEl);
    }

    containerEl.style.display = "block";
    const videoEl = document.querySelector("video.html5-main-video") || document.querySelector("video");
    if (videoEl) {
      const rect = videoEl.getBoundingClientRect();
      if (rect.width > 160 && rect.height > 90 && rect.top >= 0 && rect.top < window.innerHeight) {
        containerEl.style.top = `${Math.max(12, rect.top + 12)}px`;
        containerEl.style.right = `${Math.max(12, window.innerWidth - rect.right + 12)}px`;
      }
    }

    const itemsHtml = detectedMedia.map((m, idx) => `
      <div class="armidm-stream-item" data-idx="${idx}">
        <div>
          <div class="armidm-stream-title" title="${m.filename}">${m.filename}</div>
          <div style="font-size:10px;color:#94a3b8;margin-top:1px;">${m.mime_type || "video/mp4"} • Klik untuk Unduh</div>
        </div>
        <div class="armidm-stream-meta">${m.quality || "Video"}</div>
      </div>
    `).join("");

    containerEl.innerHTML = `
      <div class="armidm-main-btn" id="armidm-toggle-btn">
        <span>⚡ Download Video Ini (ArmIDM)</span>
        <span class="armidm-badge">${detectedMedia.length}</span>
        <span class="armidm-close-x" id="armidm-close-btn" title="Sembunyikan">✕</span>
      </div>
      <div class="armidm-dropdown ${dropdownOpen ? "open" : ""}" id="armidm-stream-list">
        ${itemsHtml}
      </div>
    `;

    const toggleBtn = containerEl.querySelector("#armidm-toggle-btn");
    const closeBtn = containerEl.querySelector("#armidm-close-btn");
    const dropdown = containerEl.querySelector("#armidm-stream-list");

    toggleBtn.addEventListener("click", (e) => {
      if (e.target === closeBtn) return;
      dropdownOpen = !dropdownOpen;
      dropdown.classList.toggle("open", dropdownOpen);
    });

    closeBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      panelHiddenByUser = true;
      containerEl.style.display = "none";
    });

    containerEl.querySelectorAll(".armidm-stream-item").forEach((row) => {
      row.addEventListener("click", () => {
        const idx = parseInt(row.getAttribute("data-idx"), 10);
        const item = detectedMedia[idx];
        if (!item) return;
        extApi.runtime.sendMessage({
          type: "DOWNLOAD_WITH_PYIDM",
          payload: {
            url: item.url,
            filename: item.filename,
            category: item.mime_type && item.mime_type.startsWith("audio/") ? "Music" : "Video",
            headers: item.headers || {
              "Referer": location.href,
              "User-Agent": navigator.userAgent
            },
            description: `Video from ${document.title}`
          }
        });
        dropdownOpen = false;
        dropdown.classList.remove("open");
      });
    });
  }

  function syncYouTubeVideosIfNeeded() {
    if (!isYouTubeVideoPage()) return false;
    const currentKey = `${location.href}__${document.title}`;
    const streams = buildYouTubeQualityStreams();
    detectedMedia = streams;
    ensureFloatingPanel();
    if (currentKey !== lastYouTubeUrl) {
      lastYouTubeUrl = currentKey;
      try {
        extApi.runtime.sendMessage({
          type: "YOUTUBE_STREAMS_FOUND",
          streams: streams
        });
      } catch (e) {}
    }
    return true;
  }

  function scanDomVideos() {
    if (syncYouTubeVideosIfNeeded()) return;

    const videos = document.querySelectorAll("video, video source");
    videos.forEach((v) => {
      const src = v.currentSrc || v.src;
      if (src && (src.startsWith("http://") || src.startsWith("https://")) && !src.includes("googlevideo.com/videoplayback")) {
        try {
          extApi.runtime.sendMessage({
            type: "DOM_VIDEO_FOUND",
            url: src,
            pageTitle: cleanVideoTitle(document.title),
            quality: v.videoHeight ? `${v.videoHeight}p HTML5` : "HTML5 Video"
          }, (res) => {
            if (res && Array.isArray(res.mediaList)) {
              detectedMedia = res.mediaList;
              ensureFloatingPanel();
            }
          });
        } catch (e) {}
      }
    });
  }

  window.addEventListener("yt-navigate-finish", () => {
    panelHiddenByUser = false;
    dropdownOpen = false;
    setTimeout(syncYouTubeVideosIfNeeded, 600);
    setTimeout(syncYouTubeVideosIfNeeded, 1800);
  });

  extApi.runtime.onMessage.addListener((msg) => {
    if (msg.type === "MEDIA_DETECTED" && Array.isArray(msg.mediaList)) {
      if (!isYouTubeVideoPage()) {
        detectedMedia = msg.mediaList;
        ensureFloatingPanel();
      }
    } else if (msg.type === "FORCE_SHOW_PANEL") {
      panelHiddenByUser = false;
      dropdownOpen = true;
      if (!syncYouTubeVideosIfNeeded()) {
        ensureFloatingPanel();
      }
    }
  });

  try {
    extApi.runtime.sendMessage({ type: "GET_TAB_MEDIA" }, (res) => {
      if (res && res.floatingBarEnabled !== false) {
        if (!syncYouTubeVideosIfNeeded() && Array.isArray(res.mediaList)) {
          detectedMedia = res.mediaList;
          ensureFloatingPanel();
        }
      }
    });
  } catch (e) {}

  setTimeout(scanDomVideos, 800);
  setInterval(scanDomVideos, 3000);
})();
