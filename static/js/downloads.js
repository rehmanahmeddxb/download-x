// Downloads & Queue page: fetch video/playlist/channel, select items,
// add to queue, then poll and render the live queue with progress,
// pause/resume/cancel/retry/reorder controls.

let currentEntries = [];
let knownStatuses = {};   // task_id -> last seen status (for completion notifications)

const fetchBtn = document.getElementById("fetchBtn");
const fetchUrl = document.getElementById("fetchUrl");

fetchBtn.addEventListener("click", doFetch);
fetchUrl.addEventListener("keydown", (e) => { if (e.key === "Enter") doFetch(); });

async function doFetch() {
  const url = fetchUrl.value.trim();
  if (!url) { toast("warning", "Paste a link first"); return; }

  fetchBtn.disabled = true;
  fetchBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Fetching...';
  try {
    const result = await apiPost("/api/fetch", { url });
    if (result.error) {
      toast("error", result.error);
      return;
    }
    currentEntries = result.entries.map(e => ({ ...e, selected: true }));
    document.getElementById("fetchResultTitle").textContent =
      `${result.title} (${result.entries.length} item${result.entries.length > 1 ? "s" : ""})`;
    document.getElementById("fetchTypeBadge").innerHTML =
      `<span class="status-badge status-downloading">${result.type}</span>`;
    document.getElementById("fetchResults").classList.remove("d-none");
    renderEntries();
  } catch (e) {
    toast("error", "Network error while fetching");
  } finally {
    fetchBtn.disabled = false;
    fetchBtn.innerHTML = '<i class="fa-solid fa-magnifying-glass"></i> Fetch';
  }
}

function renderEntries(filter = "") {
  const list = document.getElementById("entryList");
  const f = filter.toLowerCase();
  const visible = currentEntries.filter(e => !f || e.title.toLowerCase().includes(f));

  if (!visible.length) {
    list.innerHTML = '<div class="text-muted small">No matching items.</div>';
  } else {
    list.innerHTML = visible.map((e, idx) => `
      <div class="entry-row">
        <input type="checkbox" class="form-check-input entry-checkbox" data-id="${e.id}" ${e.selected ? "checked" : ""}>
        <img src="${e.thumbnail || ''}" onerror="this.style.visibility='hidden'">
        <div class="flex-fill">
          <div class="entry-title">${e.title}</div>
          <div class="entry-meta">${e.uploader || ''} ${e.duration ? '&middot; ' + formatEta(e.duration) : ''}</div>
          <div class="fmt-list d-none" id="fmt-${cssId(e.id)}"></div>
        </div>
        <button class="btn-fmt-toggle" data-entry-id="${e.id}" data-url="${encodeURIComponent(e.url)}" data-title="${(e.title || 'video').replace(/"/g, '&quot;')}">
          <i class="fa-solid fa-bolt"></i> Direct Download
        </button>
      </div>
    `).join("");
  }

  list.querySelectorAll(".entry-checkbox").forEach(cb => {
    cb.addEventListener("change", () => {
      const entry = currentEntries.find(x => String(x.id) === cb.dataset.id);
      if (entry) entry.selected = cb.checked;
      updateEstimate();
    });
  });
  list.querySelectorAll(".btn-fmt-toggle").forEach(btn => {
    btn.addEventListener("click", () => toggleDirectFormats(btn.dataset.entryId, decodeURIComponent(btn.dataset.url), btn.dataset.title));
  });
  updateEstimate();
}

// Turns an arbitrary video id into a safe DOM id fragment.
function cssId(id) { return String(id).replace(/[^a-zA-Z0-9_-]/g, "_"); }

// Fetches the real per-video quality list and lets the user pick one to
// stream straight to their device -- nothing lands on the server.
async function toggleDirectFormats(entryId, url, title) {
  const box = document.getElementById(`fmt-${cssId(entryId)}`);
  if (!box) return;
  if (box.dataset.loaded) { box.classList.toggle("d-none"); return; }

  box.classList.remove("d-none");
  box.innerHTML = '<span class="small text-muted"><i class="fa-solid fa-spinner fa-spin"></i> Loading qualities...</span>';

  let data;
  try { data = await apiPost("/api/fetch_formats", { url }); }
  catch (e) { box.innerHTML = '<span class="small text-danger">Failed to load qualities.</span>'; return; }
  if (data.error) { box.innerHTML = `<span class="small text-danger">${data.error}</span>`; return; }

  const seen = new Set();
  const usable = (data.formats || []).filter(f => {
    if (f.vcodec === "none" && f.acodec === "none") return false;
    const key = f.is_audio_only ? "audio" : f.resolution;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (!usable.length) {
    box.innerHTML = '<span class="small text-muted">No formats found.</span>';
    return;
  }

  box.innerHTML = usable.map(f => {
    const progressive = f.vcodec !== "none" && f.acodec !== "none";
    const resumable = progressive || f.is_audio_only;   // single-stream: real Range-based resume
    const label = f.is_audio_only ? `Audio (${f.ext})` : `${f.resolution} (${f.ext})`;
    const formatId = f.is_video_only ? `${f.format_id}+bestaudio` : f.format_id;
    return `<button class="fmt-pick" data-fid="${formatId}"
              title="${resumable ? "Supports pause/resume" : "Restarts from the beginning if interrupted"}">
              ${label} ${resumable ? '<i class="fa-solid fa-arrows-rotate"></i>' : '<i class="fa-solid fa-triangle-exclamation"></i>'}
            </button>`;
  }).join("");
  box.dataset.loaded = "1";

  box.querySelectorAll(".fmt-pick").forEach(btn => {
    btn.addEventListener("click", () => {
      const q = new URLSearchParams({ url, format_id: btn.dataset.fid, title });
      window.location.href = `/api/direct/download?${q.toString()}`;
      toast("success", "Streaming straight to your device...");
    });
  });
}

function updateEstimate() {
  const selectedCount = currentEntries.filter(e => e.selected).length;
  document.getElementById("estimateLine").textContent =
    `${selectedCount} of ${currentEntries.length} selected for download.`;
}

document.getElementById("entrySearch").addEventListener("input", (e) => renderEntries(e.target.value));
document.getElementById("selectAllBtn").addEventListener("click", () => { currentEntries.forEach(e => e.selected = true); renderEntries(document.getElementById("entrySearch").value); });
document.getElementById("selectNoneBtn").addEventListener("click", () => { currentEntries.forEach(e => e.selected = false); renderEntries(document.getElementById("entrySearch").value); });
document.getElementById("invertBtn").addEventListener("click", () => { currentEntries.forEach(e => e.selected = !e.selected); renderEntries(document.getElementById("entrySearch").value); });

document.getElementById("addToQueueBtn").addEventListener("click", async () => {
  const quality = document.getElementById("qualitySelect");
  const qualityLabel = quality.options[quality.selectedIndex].text;
  const selected = currentEntries.filter(e => e.selected);
  if (!selected.length) { toast("warning", "Select at least one item"); return; }

  const items = selected.map(e => ({
    url: e.url, title: e.title, thumbnail: e.thumbnail, uploader: e.uploader,
    format_id: quality.value, quality_label: qualityLabel,
  }));
  const result = await apiPost("/api/queue/add", { items });
  toast("success", `Added ${result.count} item(s) to queue`);
  refreshQueue();
});

// ---------------------------------------------------------------- queue
async function refreshQueue() {
  let tasks;
  try { tasks = await apiGet("/api/tasks"); } catch (e) { return; }

  const list = document.getElementById("queueList");
  const summary = document.getElementById("queueSummary");
  const activeCount = tasks.filter(t => t.status === "downloading").length;
  const queuedCount = tasks.filter(t => t.status === "queued").length;
  summary.textContent = `${activeCount} active, ${queuedCount} queued, ${tasks.length} total`;

  if (!tasks.length) {
    list.innerHTML = '<div class="text-muted small">No downloads yet.</div>';
    return;
  }

  list.innerHTML = tasks.map(renderTaskCard).join("");

  tasks.forEach(t => {
    const prevStatus = knownStatuses[t.id];
    if (prevStatus && prevStatus !== t.status) {
      if (t.status === "completed") {
        toast("success", `Ready on server: ${t.title} -- click Download to save it to your device`);
        notifyBrowser("Download ready on server", `${t.title} -- click to save to your device`, () => downloadTaskFile(t.id));
      } else if (t.status === "failed") {
        toast("error", `Failed: ${t.title}`);
        notifyBrowser("Download failed", t.title);
      }
    }
    knownStatuses[t.id] = t.status;
  });

  bindQueueActions();
}

function renderTaskCard(t) {
  const pct = Math.round(t.progress || 0);
  const canPause = t.status === "downloading" || t.status === "queued";
  const canResume = t.status === "paused";
  const canCancel = ["downloading", "queued", "paused"].includes(t.status);
  const canRetry = ["failed", "cancelled"].includes(t.status);
  const canRemove = ["completed", "failed", "cancelled"].includes(t.status);
  const canDownload = t.status === "completed";

  return `
  <div class="queue-card" data-id="${t.id}">
    <div class="queue-top">
      <img src="${t.thumbnail || ''}" onerror="this.style.visibility='hidden'">
      <div class="queue-body">
        <div class="queue-title">${t.title}</div>
        <div class="queue-meta">${t.quality_label || ''} &middot; <span class="status-badge status-${t.status}">${t.status}</span></div>
      </div>
    </div>
    <div class="progress mt-2"><div class="progress-bar" style="width:${pct}%"></div></div>
    <div class="queue-meta mt-1">
      ${pct}% &middot; ${formatSpeed(t.speed)} &middot; ETA ${formatEta(t.eta_seconds)}
      &middot; ${formatBytes(t.downloaded_bytes)} / ${formatBytes(t.total_bytes)}
      ${t.error_message ? `<br><span class="text-danger">${t.error_message}</span>` : ""}
    </div>
    <div class="queue-actions">
      ${canDownload ? `<button data-download-id="${t.id}"><i class="fa-solid fa-download"></i> Download to your device</button>` : ""}
      ${canPause ? `<button data-action="pause" data-id="${t.id}"><i class="fa-solid fa-pause"></i> Pause</button>` : ""}
      ${canResume ? `<button data-action="resume" data-id="${t.id}"><i class="fa-solid fa-play"></i> Resume</button>` : ""}
      ${canCancel ? `<button data-action="cancel" data-id="${t.id}"><i class="fa-solid fa-xmark"></i> Cancel</button>` : ""}
      ${canRetry ? `<button data-action="retry" data-id="${t.id}"><i class="fa-solid fa-rotate-right"></i> Retry</button>` : ""}
      ${t.status === "queued" ? `<button data-action="priority_up" data-id="${t.id}"><i class="fa-solid fa-arrow-up"></i></button>` : ""}
      ${t.status === "queued" ? `<button data-action="priority_down" data-id="${t.id}"><i class="fa-solid fa-arrow-down"></i></button>` : ""}
      ${canRemove ? `<button data-action="remove" data-id="${t.id}"><i class="fa-solid fa-trash"></i> Remove</button>` : ""}
    </div>
  </div>`;
}

function bindQueueActions() {
  document.querySelectorAll("#queueList [data-action]").forEach(btn => {
    btn.addEventListener("click", async () => {
      await apiPost(`/api/tasks/${btn.dataset.id}/${btn.dataset.action}`, {});
      refreshQueue();
    });
  });
  document.querySelectorAll("#queueList [data-download-id]").forEach(btn => {
    btn.addEventListener("click", () => downloadTaskFile(btn.dataset.downloadId));
  });
}

refreshQueue();
setInterval(refreshQueue, 1500);
