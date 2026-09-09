// History page: list, search, delete, redownload, CSV export (link only).

async function refreshHistory(search = "") {
  const list = document.getElementById("historyList");
  let entries;
  try {
    entries = await apiGet(`/api/history?search=${encodeURIComponent(search)}`);
  } catch (e) { return; }

  if (!entries.length) {
    list.innerHTML = '<div class="text-muted small">No history yet.</div>';
    return;
  }

  list.innerHTML = entries.map(h => `
    <div class="history-row" data-id="${h.id}">
      <img src="${h.thumbnail || ''}" onerror="this.style.visibility='hidden'">
      <div class="flex-fill">
        <div class="history-title">${h.title}</div>
        <div class="history-meta">
          ${h.uploader || ''} &middot; ${new Date(h.date_completed * 1000).toLocaleString()}
          &middot; ${h.quality_label || ''} &middot; ${formatBytes(h.size_bytes)}
          &middot; <span class="status-badge status-${h.status}">${h.status}</span>
        </div>
      </div>
      <div class="queue-actions">
        <button data-action="redownload" data-id="${h.id}"><i class="fa-solid fa-rotate-right"></i> Redownload</button>
        <button data-action="delete" data-id="${h.id}"><i class="fa-solid fa-trash"></i> Delete</button>
      </div>
    </div>
  `).join("");

  list.querySelectorAll('[data-action="delete"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      await apiDelete(`/api/history/${btn.dataset.id}`);
      toast("success", "Removed from history");
      refreshHistory(document.getElementById("historySearch").value);
    });
  });
  list.querySelectorAll('[data-action="redownload"]').forEach(btn => {
    btn.addEventListener("click", async () => {
      const url = prompt("Re-enter the original YouTube URL to redownload:");
      if (!url) return;
      const result = await apiPost(`/api/history/${btn.dataset.id}/redownload`, { url });
      if (result.error) { toast("error", result.error); return; }
      toast("success", "Added back to queue -- see Downloads & Queue page");
    });
  });
}

document.getElementById("historySearch").addEventListener("input", (e) => refreshHistory(e.target.value));
refreshHistory();
setInterval(() => refreshHistory(document.getElementById("historySearch").value), 5000);
