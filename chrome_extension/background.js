// ArmIDM Integration Module - Cross-Browser Background Script (Firefox & Chromium) v2.7.0
const PYIDM_HTTP_BASE = "http://127.0.0.1:16888";
const PYIDM_WS_URL = "ws://127.0.0.1:16888/ws";

const extApi = typeof chrome !== "undefined" ? chrome : browser;
const badgeApi = extApi.action || extApi.browserAction;
const isFirefox = typeof browser !== "undefined" && typeof runtime !== "undefined" || navigator.userAgent.includes("Firefox");

let serverOnline = true; // Optimistic default, diverifikasi berkala oleh heartbeat
let interceptEnabled = true;
let floatingBarEnabled = true;
let wsConnection = null;
let interceptExtensions = [
  ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".exe", ".msi", ".dmg",
  ".iso", ".apk", ".mp4", ".mkv", ".webm", ".avi", ".mov", ".mp3",
  ".flac", ".wav", ".pdf", ".docx", ".xlsx", ".pptx", ".nsp", ".xci", ".nsz"
];

// Ekstensi file arsip/program yang selalu diambil alih di level jaringan (termasuk XHR/Fetch seperti VikingFile)
const ARCHIVE_BINARY_EXTENSIONS = [
  ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".exe", ".msi", ".dmg",
  ".iso", ".apk", ".nsp", ".xci", ".nsz"
];

const tabMediaMap = {};
const recentRequestHeaders = new Map();
const recentlyInterceptedUrls = new Map(); // url -> timestamp (mencegah duplikasi pop-up)

function wasRecentlyIntercepted(url) {
  const now = Date.now();
  for (const [k, ts] of recentlyInterceptedUrls.entries()) {
    if (now - ts > 8000) recentlyInterceptedUrls.delete(k);
  }
  if (recentlyInterceptedUrls.has(url)) return true;
  recentlyInterceptedUrls.set(url, now);
  return false;
}

extApi.storage.local.get(["interceptEnabled", "floatingBarEnabled"], (res) => {
  if (res && typeof res.interceptEnabled === "boolean") interceptEnabled = res.interceptEnabled;
  if (res && typeof res.floatingBarEnabled === "boolean") floatingBarEnabled = res.floatingBarEnabled;
});

// Deteksi dukungan extraHeaders
const reqHeaderSpecs = ["requestHeaders"];
if (
  extApi.webRequest &&
  extApi.webRequest.OnBeforeSendHeadersOptions &&
  extApi.webRequest.OnBeforeSendHeadersOptions.EXTRA_HEADERS
) {
  reqHeaderSpecs.push("extraHeaders");
}

try {
  extApi.webRequest.onBeforeSendHeaders.addListener(
    (details) => {
      if (!details.url || !details.url.startsWith("http")) return;
      // Jangan tangkap request dari ArmIDM sendiri
      if (details.url.startsWith(PYIDM_HTTP_BASE)) return;
      const hdrs = {};
      for (const h of details.requestHeaders || []) {
        const name = h.name.toLowerCase();
        if (name === "cookie" || name === "referer" || name === "authorization" || name === "user-agent") {
          hdrs[h.name] = h.value;
        }
      }
      if (Object.keys(hdrs).length > 0) {
        recentRequestHeaders.set(details.url, { headers: hdrs, tabId: details.tabId, ts: Date.now() });
        if (recentRequestHeaders.size > 250) {
          const oldestKey = recentRequestHeaders.keys().next().value;
          recentRequestHeaders.delete(oldestKey);
        }
      }
    },
    { urls: ["<all_urls>"] },
    reqHeaderSpecs
  );
} catch (e) {}

function getBaseDomain(hostname) {
  const parts = (hostname || "").split(".").filter(Boolean);
  if (parts.length <= 2) return hostname;
  return parts.slice(-2).join(".");
}

function withTimeout(promise, ms, fallbackVal) {
  return Promise.race([
    promise,
    new Promise((resolve) => setTimeout(() => resolve(fallbackVal), ms))
  ]);
}

function getCookiesAsync(filterObj) {
  return withTimeout(
    new Promise((resolve) => {
      try {
        if (typeof browser !== "undefined" && browser.cookies && browser.cookies.getAll) {
          browser.cookies.getAll(filterObj).then(resolve).catch(() => resolve([]));
        } else {
          extApi.cookies.getAll(filterObj, (cookies) => resolve(cookies || []));
        }
      } catch (e) {
        resolve([]);
      }
    }),
    500,
    []
  );
}

function queryActiveTabAsync() {
  return withTimeout(
    new Promise((resolve) => {
      try {
        if (typeof browser !== "undefined" && browser.tabs && browser.tabs.query) {
          browser.tabs.query({ active: true, currentWindow: true }).then((tabs) => resolve((tabs && tabs[0]) || null)).catch(() => resolve(null));
        } else {
          extApi.tabs.query({ active: true, currentWindow: true }, (tabs) => resolve((tabs && tabs[0]) || null));
        }
      } catch (e) {
        resolve(null);
      }
    }),
    400,
    null
  );
}

async function buildAuthenticatedHeaders(targetUrl, referrerUrl) {
  const cached = recentRequestHeaders.get(targetUrl);
  const headers = {
    "User-Agent": navigator.userAgent
  };

  if (cached && cached.headers) {
    Object.assign(headers, cached.headers);
  }

  let finalReferer = referrerUrl || headers["Referer"] || headers["referer"] || "";
  if (!finalReferer) {
    const activeTab = await queryActiveTabAsync();
    if (activeTab && activeTab.url && activeTab.url.startsWith("http")) {
      finalReferer = activeTab.url;
    }
  }
  if (finalReferer) {
    headers["Referer"] = finalReferer;
  }

  const cookieMap = new Map();
  try {
    const urlsToQuery = [targetUrl];
    if (finalReferer && finalReferer.startsWith("http")) {
      urlsToQuery.push(finalReferer);
    }
    for (const u of urlsToQuery) {
      const ckList = await getCookiesAsync({ url: u });
      for (const c of ckList || []) {
        cookieMap.set(c.name, c.value);
      }
    }

    const uObj = new URL(targetUrl);
    const baseDom = getBaseDomain(uObj.hostname);
    if (baseDom) {
      const domCookies = await getCookiesAsync({ domain: baseDom });
      for (const c of domCookies || []) {
        if (!cookieMap.has(c.name)) {
          cookieMap.set(c.name, c.value);
        }
      }
    }
  } catch (e) {}

  if (cookieMap.size > 0) {
    headers["Cookie"] = Array.from(cookieMap.entries())
      .map(([k, v]) => `${k}=${v}`)
      .join("; ");
  }

  return headers;
}

function setTabBadge(tabId, count) {
  if (!badgeApi) return;
  try {
    badgeApi.setBadgeText({ tabId: tabId, text: count > 0 ? String(count) : "" });
    badgeApi.setBadgeBackgroundColor({ tabId: tabId, color: "#16A34A" });
  } catch (e) {}
}

function setupContextMenus() {
  try {
    extApi.contextMenus.removeAll(() => {
      extApi.contextMenus.create({
        id: "pyidm_download_link",
        title: "⬇ Download dengan ArmIDM",
        contexts: ["link", "video", "audio", "image"]
      });
      extApi.contextMenus.create({
        id: "pyidm_download_page_videos",
        title: "🎬 Lihat Video Terdeteksi di Halaman Ini (ArmIDM)",
        contexts: ["page"]
      });
    });
  } catch (e) {}
}

extApi.runtime.onInstalled.addListener(setupContextMenus);
setupContextMenus();

extApi.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId === "pyidm_download_link") {
    const targetUrl = info.linkUrl || info.srcUrl;
    if (targetUrl) {
      const refUrl = info.pageUrl || (tab ? tab.url : "");
      const authHeaders = await buildAuthenticatedHeaders(targetUrl, refUrl);
      sendDownloadToArmIDM({
        url: targetUrl,
        filename: guessFilenameFromUrl(targetUrl),
        headers: authHeaders,
        description: "Context Menu Download"
      });
    }
  } else if (info.menuItemId === "pyidm_download_page_videos" && tab && tab.id) {
    try {
      extApi.tabs.sendMessage(tab.id, { type: "FORCE_SHOW_PANEL" });
    } catch (e) {}
  }
});

function connectWebSocket() {
  try {
    if (wsConnection && (wsConnection.readyState === WebSocket.OPEN || wsConnection.readyState === WebSocket.CONNECTING)) {
      return;
    }
    wsConnection = new WebSocket(PYIDM_WS_URL);
    wsConnection.onopen = () => {
      serverOnline = true;
      wsConnection.send(JSON.stringify({ type: "ping" }));
    };
    wsConnection.onclose = () => {
      wsConnection = null;
    };
    wsConnection.onerror = () => {
      wsConnection = null;
    };
  } catch (err) {
    wsConnection = null;
  }
}

async function checkServerStatus() {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1500);
    const resp = await fetch(`${PYIDM_HTTP_BASE}/api/status`, { signal: controller.signal });
    clearTimeout(timer);
    if (resp.ok) {
      const data = await resp.json();
      serverOnline = true;
      interceptEnabled = Boolean(data.intercept_enabled);
      if (Array.isArray(data.intercept_extensions)) {
        interceptExtensions = data.intercept_extensions;
      }
      connectWebSocket();
      return data;
    }
  } catch (e) {
    serverOnline = false;
  }
  return null;
}

if (extApi.alarms) {
  extApi.alarms.create("pyidm_heartbeat", { periodInMinutes: 0.25 });
  extApi.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === "pyidm_heartbeat") {
      checkServerStatus();
    }
  });
}
setInterval(checkServerStatus, 5000);
checkServerStatus();

function guessFilenameFromUrl(url, pageTitle = "") {
  try {
    const u = new URL(url);
    let base = decodeURIComponent(u.pathname.split("/").pop() || "");
    if (!base || base === "videoplayback" || base === "download" || base.length < 3) {
      const cleanTitle = (pageTitle || "download_file").replace(/[^a-zA-Z0-9._ -]/g, "_").slice(0, 65);
      if (url.includes(".m3u8")) return `${cleanTitle}.ts`;
      return cleanTitle;
    }
    return base;
  } catch (e) {
    return "download_file";
  }
}

function extractFilenameFromContentDisposition(cd) {
  if (!cd) return "";
  const mStar = cd.match(/filename\*=UTF-8''([^;\r\n]+)/i);
  if (mStar && mStar[1]) {
    try {
      return decodeURIComponent(mStar[1].replace(/["']/g, "").trim());
    } catch (e) {}
  }
  const m = cd.match(/filename=["']?([^"';\r\n]+)["']?/i);
  if (m && m[1]) {
    try {
      return decodeURIComponent(m[1].trim());
    } catch (e) {
      return m[1].trim();
    }
  }
  return "";
}

async function sendDownloadToArmIDM(payload) {
  try {
    const resp = await fetch(`${PYIDM_HTTP_BASE}/api/add_download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: payload.url,
        filename: payload.filename || "",
        category: payload.category || "",
        file_size: payload.file_size || -1,
        headers: payload.headers || {},
        description: payload.description || "Intercepted by Browser Extension",
        show_dialog: true
      })
    });
    return resp.ok;
  } catch (e) {
    return false;
  }
}

function cancelAndEraseBrowserDownload(downloadId) {
  const doErase = () => {
    try {
      if (typeof browser !== "undefined" && browser.downloads && browser.downloads.erase) {
        browser.downloads.erase({ id: downloadId }).catch(() => {});
      } else {
        extApi.downloads.erase({ id: downloadId }, () => {});
      }
    } catch (e) {}
  };

  try {
    if (typeof browser !== "undefined" && browser.downloads && browser.downloads.cancel) {
      browser.downloads.cancel(downloadId).then(doErase).catch(doErase);
    } else {
      extApi.downloads.cancel(downloadId, doErase);
    }
  } catch (e) {
    doErase();
  }
  setTimeout(doErase, 250);
  setTimeout(doErase, 800);
}

// ============================================================================
// 1. INTERSEPSI UNDUHAN VIA DOWNLOADS API (CHROME & FIREFOX)
// ============================================================================
const handledDownloadIds = new Set();

function shouldInterceptDownload(url, filename, mime, knownSize) {
  const lowerUrl = (url || "").split("?")[0].toLowerCase();
  const lowerFilename = (filename || "").toLowerCase();
  const lowerMime = (mime || "").toLowerCase();

  const matchesExt = interceptExtensions.some(
    (ext) => lowerUrl.endsWith(ext) || lowerFilename.endsWith(ext)
  );
  const isBinaryMime =
    lowerMime.includes("application/octet-stream") ||
    lowerMime.includes("application/x-rar") ||
    lowerMime.includes("application/vnd.rar") ||
    lowerMime.includes("application/zip") ||
    lowerMime.includes("application/x-zip") ||
    lowerMime.includes("application/x-7z") ||
    lowerMime.includes("application/x-compressed") ||
    lowerMime.includes("application/pdf") ||
    lowerMime.includes("video/") ||
    lowerMime.includes("audio/");

  return matchesExt || isBinaryMime || knownSize > 1024 * 1024;
}

function handleBrowserDownloadItem(downloadItem, suggestedFilename = "") {
  // 1. PENTING: Abaikan riwayat unduhan lama yang dimuat ulang oleh Chrome saat browser baru dibuka!
  //    Unduhan baru yang benar-benar sedang berjalan selalu berstatus "in_progress" dan memiliki startTime <= 10 detik terakhir.
  if (downloadItem.state && downloadItem.state !== "in_progress") return;
  if (downloadItem.paused === true) return;
  if (downloadItem.startTime) {
    const startMs = new Date(downloadItem.startTime).getTime();
    if (!isNaN(startMs) && (Date.now() - startMs > 10000)) {
      return;
    }
  }

  // Gunakan status serverOnline & interceptEnabled secara SINKRON agar cancel() dieksekusi
  // di tick yang sama sebelum Chrome sempat memunculkan dialog "Save As"!
  if (!interceptEnabled || !serverOnline) return;
  const url = downloadItem.finalUrl || downloadItem.url || "";
  if (!url.startsWith("http://") && !url.startsWith("https://")) return;

  if (handledDownloadIds.has(downloadItem.id) || recentlyInterceptedUrls.has(url)) {
    cancelAndEraseBrowserDownload(downloadItem.id);
    return;
  }

  const rawFilename = suggestedFilename || downloadItem.filename || "";
  const cleanName = rawFilename ? rawFilename.split(/[/\\]/).pop() : "";
  const knownSize = downloadItem.totalBytes || downloadItem.fileSize || -1;

  const hasOnDetermining = Boolean(extApi.downloads && extApi.downloads.onDeterminingFilename);
  if (!cleanName && hasOnDetermining && !shouldInterceptDownload(url, "", downloadItem.mime, knownSize)) {
    return;
  }

  if (!shouldInterceptDownload(url, cleanName, downloadItem.mime, knownSize)) {
    return;
  }

  // BATALKAN UNDUHAN CHROME SECARA SINKRON SEKARANG JUGA (Sebelum ada proses async/await!)
  handledDownloadIds.add(downloadItem.id);
  wasRecentlyIntercepted(url);
  try {
    extApi.downloads.pause(downloadItem.id, () => {});
  } catch (e) {}
  cancelAndEraseBrowserDownload(downloadItem.id);

  // Setelah unduhan browser dibatalkan secara sinkron, kumpulkan Cookie & kirim ke ArmIDM
  (async () => {
    const authHeaders = await buildAuthenticatedHeaders(url, downloadItem.referrer || "");
    await sendDownloadToArmIDM({
      url: url,
      filename: cleanName || guessFilenameFromUrl(url),
      file_size: knownSize > 0 ? knownSize : -1,
      headers: authHeaders,
      description: "Auto-intercepted from Browser"
    });
  })();
}

extApi.downloads.onCreated.addListener((downloadItem) => {
  handleBrowserDownloadItem(downloadItem, "");
});

// Khusus Chrome/Edge/Brave: onDeterminingFilename memberikan nama file asli dari Content-Disposition (misal ArmIDM_Full_Package.zip)
if (extApi.downloads && extApi.downloads.onDeterminingFilename) {
  extApi.downloads.onDeterminingFilename.addListener((downloadItem, suggest) => {
    handleBrowserDownloadItem(downloadItem, downloadItem.filename || "");
  });
}

// ============================================================================
// 2. INTERSEPSI JARINGAN LANGSUNG (KHUSUS FIREFOX BLOCKING & XHR IN-PAGE VIKINGFILE)
// ============================================================================
const MEDIA_MIME_PATTERNS = [
  "video/",
  "audio/",
  "application/vnd.apple.mpegurl",
  "application/x-mpegurl",
  "application/dash+xml"
];

const MEDIA_EXT_REGEX = /\.(mp4|webm|mkv|m3u8|mpd|flv|mov|m4v|mp3|aac|flac)(\?|$)/i;

function detectQualityLabel(url, sizeBytes, mime) {
  const lower = url.toLowerCase();
  if (lower.includes("2160") || lower.includes("4k")) return "4K UHD";
  if (lower.includes("1080")) return "1080p Full HD";
  if (lower.includes("720")) return "720p HD";
  if (lower.includes("480")) return "480p SD";
  if (lower.includes("360")) return "360p";
  if (lower.includes(".m3u8") || mime.includes("mpegurl")) return "HLS Stream (M3U8)";
  if (lower.includes(".mpd") || mime.includes("dash")) return "DASH Stream";
  if (sizeBytes > 50 * 1024 * 1024) return "High Quality";
  return "Direct Media";
}

const respHeaderSpecs = ["responseHeaders"];
try {
  if (typeof browser !== "undefined" && browser.runtime && browser.runtime.getBrowserInfo) {
    respHeaderSpecs.push("blocking");
  }
} catch (e) {}

extApi.webRequest.onHeadersReceived.addListener(
  (details) => {
    const url = details.url || "";
    if (!url.startsWith("http") || url.startsWith(PYIDM_HTTP_BASE)) return;
    if (details.method !== "GET") return;

    let contentType = "";
    let contentLength = -1;
    let contentDisposition = "";
    for (const h of details.responseHeaders || []) {
      const name = h.name.toLowerCase();
      if (name === "content-type") contentType = (h.value || "").toLowerCase().split(";")[0].trim();
      else if (name === "content-length") contentLength = parseInt(h.value || "-1", 10);
      else if (name === "content-disposition") contentDisposition = h.value || "";
    }

    const cdFilename = extractFilenameFromContentDisposition(contentDisposition);
    const lowerUrlPath = url.split("?")[0].toLowerCase();
    const lowerCdName = cdFilename.toLowerCase();

    // --- A. INTERSEPSI STREAM UNDUHAN ARSIP ---
    // Di Firefox (yang mendukung blocking), kita bisa memblokir semua unduhan arsip langsung di level jaringan.
    // Di Chrome (tanpa blocking), hanya intersep jika request berasal dari XMLHttpRequest/Fetch in-page berukuran besar (> 5 MB, seperti VikingFile)
    // agar unduhan tautan biasa di Chrome ditangani secara bersih oleh chrome.downloads.onDeterminingFilename tanpa duplikasi!
    const isBlockingSupported = respHeaderSpecs.includes("blocking");
    const isInPageXhrArchive = details.type === "xmlhttprequest" && contentLength > 5 * 1024 * 1024;

    if (isBlockingSupported || isInPageXhrArchive) {
      const isAttachment = contentDisposition.toLowerCase().includes("attachment");
      const hasArchiveExt = ARCHIVE_BINARY_EXTENSIONS.some(
        (ext) => lowerUrlPath.endsWith(ext) || lowerCdName.endsWith(ext)
      );
      const isBinaryMime =
        contentType.includes("application/octet-stream") ||
        contentType.includes("application/x-rar") ||
        contentType.includes("application/vnd.rar") ||
        contentType.includes("application/zip") ||
        contentType.includes("application/x-7z");

      if (
        interceptEnabled &&
        serverOnline &&
        details.statusCode === 200 &&
        (hasArchiveExt || (isAttachment && isBinaryMime)) &&
        contentLength > 300 * 1024
      ) {
        if (!wasRecentlyIntercepted(url)) {
          const finalName = cdFilename || guessFilenameFromUrl(url);
          const refHeader = details.originUrl || details.initiator || "";
          buildAuthenticatedHeaders(url, refHeader).then((authHeaders) => {
            sendDownloadToArmIDM({
              url: url,
              filename: finalName,
              file_size: contentLength,
              headers: authHeaders,
              description: "Network Stream Intercepted"
            });
          });
        }
        if (isBlockingSupported) {
          return { cancel: true };
        }
        return;
      }
    }

    // --- B. NETWORK VIDEO & AUDIO SNIFFER ---
    if (details.tabId < 0) return;
    if (url.includes("googlevideo.com/videoplayback") || url.includes("youtube.com/api/stats")) return;

    const isMediaMime = MEDIA_MIME_PATTERNS.some((p) => contentType.includes(p));
    const isMediaExt = MEDIA_EXT_REGEX.test(url);
    if (!isMediaMime && !isMediaExt) return;

    const isManifest = url.toLowerCase().includes(".m3u8") || contentType.includes("mpegurl") || url.toLowerCase().includes(".mpd");
    if (!isManifest && contentLength > 0 && contentLength < 120 * 1024) return;
    if (url.toLowerCase().includes(".ts") && !isManifest && contentLength < 1024 * 1024) return;

    extApi.tabs.get(details.tabId, async (tab) => {
      if (extApi.runtime.lastError || !tab) return;
      const pageTitle = tab.title || "Web Video";
      const pageUrl = tab.url || "";
      const filename = cdFilename || guessFilenameFromUrl(url, pageTitle);
      const quality = detectQualityLabel(url, contentLength, contentType);
      const authHeaders = await buildAuthenticatedHeaders(url, pageUrl);

      const mediaItem = {
        id: btoa(url).slice(0, 16),
        url: url,
        filename: filename,
        page_title: pageTitle,
        page_url: pageUrl,
        mime_type: contentType || "video/mp4",
        size: contentLength,
        quality: quality,
        tab_id: details.tabId,
        headers: authHeaders
      };

      if (!tabMediaMap[details.tabId]) {
        tabMediaMap[details.tabId] = [];
      }
      const list = tabMediaMap[details.tabId];
      if (!list.some((item) => item.url === url)) {
        list.unshift(mediaItem);
        if (list.length > 30) list.pop();

        setTabBadge(details.tabId, list.length);

        if (floatingBarEnabled) {
          try {
            extApi.tabs.sendMessage(details.tabId, {
              type: "MEDIA_DETECTED",
              mediaList: list
            });
          } catch (e) {}
        }

        fetch(`${PYIDM_HTTP_BASE}/api/report_media`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(mediaItem)
        }).catch(() => {});
      }
    });
  },
  { urls: ["<all_urls>"] },
  respHeaderSpecs
);

extApi.tabs.onRemoved.addListener((tabId) => {
  delete tabMediaMap[tabId];
});

extApi.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "GET_TAB_MEDIA") {
    const tabId = msg.tabId || (sender.tab ? sender.tab.id : -1);
    sendResponse({
      mediaList: tabMediaMap[tabId] || [],
      floatingBarEnabled: floatingBarEnabled,
      interceptEnabled: interceptEnabled
    });
    return true;
  }

  if (msg.type === "YOUTUBE_STREAMS_FOUND" && sender.tab && Array.isArray(msg.streams)) {
    const tabId = sender.tab.id;
    tabMediaMap[tabId] = msg.streams;
    setTabBadge(tabId, msg.streams.length);
    for (const st of msg.streams) {
      fetch(`${PYIDM_HTTP_BASE}/api/report_media`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({}, st, { tab_id: tabId }))
      }).catch(() => {});
    }
    sendResponse({ mediaList: msg.streams });
    return true;
  }

  if (msg.type === "DOM_VIDEO_FOUND" && sender.tab) {
    const tabId = sender.tab.id;
    const url = msg.url;
    if (url && url.startsWith("http")) {
      if (!tabMediaMap[tabId]) tabMediaMap[tabId] = [];
      const list = tabMediaMap[tabId];
      if (!list.some((x) => x.url === url)) {
        buildAuthenticatedHeaders(url, sender.tab.url || "").then((authHeaders) => {
          const item = {
            id: btoa(url).slice(0, 16),
            url: url,
            filename: guessFilenameFromUrl(url, sender.tab.title),
            page_title: sender.tab.title || "HTML5 Video",
            page_url: sender.tab.url || "",
            mime_type: "video/mp4",
            size: -1,
            quality: msg.quality || "HTML5 Video",
            tab_id: tabId,
            headers: authHeaders
          };
          list.unshift(item);
          setTabBadge(tabId, list.length);
          fetch(`${PYIDM_HTTP_BASE}/api/report_media`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(item)
          }).catch(() => {});
          sendResponse({ mediaList: list });
        });
        return true;
      }
      sendResponse({ mediaList: list });
    }
    return true;
  }

  if (msg.type === "DOWNLOAD_WITH_PYIDM") {
    const payload = msg.payload || {};
    buildAuthenticatedHeaders(payload.url || "", (payload.headers && payload.headers.Referer) || "").then((authHeaders) => {
      payload.headers = Object.assign({}, authHeaders, payload.headers || {});
      if (authHeaders["Cookie"]) payload.headers["Cookie"] = authHeaders["Cookie"];
      sendDownloadToArmIDM(payload).then((ok) => {
        sendResponse({ ok });
      });
    });
    return true;
  }

  if (msg.type === "SET_PREFS") {
    if (typeof msg.interceptEnabled === "boolean") {
      interceptEnabled = msg.interceptEnabled;
      extApi.storage.local.set({ interceptEnabled });
      fetch(`${PYIDM_HTTP_BASE}/api/toggle_intercept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: interceptEnabled })
      }).catch(() => {});
    }
    if (typeof msg.floatingBarEnabled === "boolean") {
      floatingBarEnabled = msg.floatingBarEnabled;
      extApi.storage.local.set({ floatingBarEnabled });
    }
    sendResponse({ ok: true });
    return true;
  }
});
