// Shared helpers used across pages: sidebar toggle, fetch wrapper, toasts,
// formatting utilities, and browser notifications.

document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("sidebarToggle");
  const sidebar = document.querySelector(".sidebar");
  if (toggle && sidebar) {
    toggle.addEventListener("click", () => sidebar.classList.toggle("open"));
    document.addEventListener("click", (e) => {
      if (window.innerWidth < 992 && sidebar.classList.contains("open") &&
          !sidebar.contains(e.target) && e.target !== toggle) {
        sidebar.classList.remove("open");
      }
    });
  }

  if ("Notification" in window && Notification.permission === "default") {
    // Ask quietly; user can ignore. Needed for "download completed" alerts.
    Notification.requestPermission().catch(() => {});
  }
});

async function apiGet(path) {
  const res = await fetch(path);
  return res.json();
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return res.json();
}

async function apiDelete(path) {
  const res = await fetch(path, { method: "DELETE" });
  return res.json();
}

function formatBytes(n) {
  if (!n || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let size = n;
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++; }
  return `${size.toFixed(1)} ${units[i]}`;
}

function formatSpeed(bps) {
  if (!bps || bps <= 0) return "-";
  return formatBytes(bps) + "/s";
}

function formatEta(seconds) {
  if (!seconds || seconds <= 0) return "-";
  seconds = Math.round(seconds);
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h) return `${h}h ${m}m`;
  if (m) return `${m}m ${s}s`;
  return `${s}s`;
}

function toast(icon, title) {
  if (window.Swal) {
    Swal.fire({
      toast: true, position: "top-end", icon, title,
      showConfirmButton: false, timer: 2500, timerProgressBar: true,
      background: "#141a29", color: "#e8ecf5",
    });
  }
}

function notifyBrowser(title, body, onClick) {
  if ("Notification" in window && Notification.permission === "granted") {
    try {
      const n = new Notification(title, { body });
      if (onClick) {
        n.onclick = () => { window.focus(); onClick(); n.close(); };
      }
    } catch (e) { /* ignore */ }
  }
}

// Triggers a direct browser download of a finished server-side file.
// Uses a temporary <a download> click instead of fetching the bytes into
// JS first, so the transfer streams straight from the server to disk --
// fast, and no memory spent buffering large files in the tab.
function downloadTaskFile(taskId) {
  const a = document.createElement("a");
  a.href = `/api/tasks/${taskId}/file`;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
