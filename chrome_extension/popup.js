const PYIDM_HTTP_BASE = "http://127.0.0.1:16888";

const statusEl = document.getElementById("server-status");
const speedPill = document.getElementById("total-speed-pill");
const chkIntercept = document.getElementById("chk-intercept");
const chkFloating = document.getElementById("chk-floating");
const chkSpeedLimit = document.getElementById("chk-speed-limit");
const numSpeedKbps = document.getElementById("num-speed-kbps");
const btnApplyLimit = document.getElementById("btn-apply-limit");
const inpQuickUrl = document.getElementById("inp-quick-url");
const btnQuickDl = document.getElementById("btn-quick-dl");
const videoCountEl = document.getElementById("video-count");
const videoListEl = document.getElementById("video-list");
const tasksListEl = document.getElementById("tasks-list");

function formatBytes(bytes) {
  if (!bytes || bytes < 0) return "Stream";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(1)} ${units[i]}`;
}

async function refreshServerStatus() {
  try {
    const resp = await fetch(`${PYIDM_HTTP_BASE}/api/status`);
    if (!resp.ok) throw new Error("Offline");
    const data = await resp.json();
    statusEl.textContent = "🟢 Terhubung ke ArmIDM Desktop";
    statusEl.style.color = "#4ade80";
    speedPill.textContent = data.total_speed_formatted || "0 KB/s";

    if (document.activeElement !== numSpeedKbps) {
      chkSpeedLimit.checked = Boolean(data.speed_limit_enabled);
      numSpeedKbps.value = data.speed_limit_kbps || 1024;
    }

    renderTasks(data.tasks || []);
  } catch (e) {
    statusEl.textContent = "🔴 ArmIDM Desktop Belum Dijalankan";
    statusEl.style.color = "#f87171";
  }
}

function renderTasks(tasks) {
  if (!tasks.length) {
    tasksListEl.innerHTML = `<div class="empty-msg">Tidak ada unduhan di daftar ArmIDM.</div>`;
    return;
  }
  tasksListEl.innerHTML = tasks.slice(0, 8).map((t) => `
    <div class="item-row">
      <div>
        <div class="item-name" title="${t.filename}">${t.filename}</div>
        <div class="item-sub">${t.status} • ${t.progress}% • ${t.speed_Formatted}</div>
      </div>
      <button class="btn-sm task-act-btn" data-id="${t.id}" data-act="${t.status.startsWith("Downloading") ? "pause" : "resume"}">
        ${t.status.startsWith("Downloading") ? "⏸" : "▶"}
      </button>
    </div>
  `).join("");

  tasksListEl.querySelectorAll(".task-act-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await fetch(`${PYIDM_HTTP_BASE}/api/control_task`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          task_id: btn.getAttribute("data-id"),
          action: btn.getAttribute("data-act")
        })
      });
      refreshServerStatus();
    });
  });
}

function loadActiveTabMedia() {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const activeTab = tabs[0];
    if (!activeTab) return;
    chrome.runtime.sendMessage({ type: "GET_TAB_MEDIA", tabId: activeTab.id }, (res) => {
      if (!res) return;
      chkIntercept.checked = res.interceptEnabled !== false;
      chkFloating.checked = res.floatingBarEnabled !== false;
      const list = res.mediaList || [];
      videoCountEl.textContent = String(list.length);
      if (!list.length) {
        videoListEl.innerHTML = `<div class="empty-msg">Belum ada stream video terdeteksi di tab ini.</div>`;
        return;
      }
      videoListEl.innerHTML = list.map((m, idx) => `
        <div class="item-row">
          <div>
            <div class="item-name" title="${m.filename}">${m.filename}</div>
            <div class="item-sub">${m.quality} • ${formatBytes(m.size)}</div>
          </div>
          <button class="btn-primary dl-vid-btn" data-idx="${idx}">⬇ Unduh</button>
        </div>
      `).join("");

      videoListEl.querySelectorAll(".dl-vid-btn").forEach((b) => {
        b.addEventListener("click", () => {
          const item = list[parseInt(b.getAttribute("data-idx"), 10)];
          if (!item) return;
          chrome.runtime.sendMessage({
            type: "DOWNLOAD_WITH_PYIDM",
            payload: {
              url: item.url,
              filename: item.filename,
              category: "Video",
              headers: item.headers || {},
              description: `Video from ${activeTab.title || "Chrome"}`
            }
          });
          window.close();
        });
      });
    });
  });
}

chkIntercept.addEventListener("change", () => {
  chrome.runtime.sendMessage({ type: "SET_PREFS", interceptEnabled: chkIntercept.checked });
});

chkFloating.addEventListener("change", () => {
  chrome.runtime.sendMessage({ type: "SET_PREFS", floatingBarEnabled: chkFloating.checked });
});

async function applySpeedLimit() {
  try {
    await fetch(`${PYIDM_HTTP_BASE}/api/speed_limit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: chkSpeedLimit.checked,
        rate_kbps: parseInt(numSpeedKbps.value || "1024", 10)
      })
    });
    refreshServerStatus();
  } catch (e) {}
}

chkSpeedLimit.addEventListener("change", applySpeedLimit);
btnApplyLimit.addEventListener("click", applySpeedLimit);

btnQuickDl.addEventListener("click", () => {
  const url = inpQuickUrl.value.trim();
  if (!url) return;
  chrome.runtime.sendMessage({
    type: "DOWNLOAD_WITH_PYIDM",
    payload: { url: url, description: "Added from Extension Popup" }
  }, () => {
    inpQuickUrl.value = "";
    refreshServerStatus();
  });
});

loadActiveTabMedia();
refreshServerStatus();
setInterval(refreshServerStatus, 1500);
