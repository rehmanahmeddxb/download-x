// Dashboard: stats cards + charts, polled every 3s.

let chartDays, chartDisk;

async function refreshDashboard() {
  let stats;
  try {
    stats = await apiGet("/api/stats");
  } catch (e) { return; }

  document.getElementById("stat-total").textContent = stats.total_downloads;
  document.getElementById("stat-completed").textContent = stats.completed_downloads;
  document.getElementById("stat-active").textContent = stats.active_downloads;
  document.getElementById("stat-queued").textContent = stats.queued_downloads;
  document.getElementById("stat-today").textContent = formatBytes(stats.downloaded_session_bytes);
  document.getElementById("stat-month").textContent = stats.failed_downloads;
  document.getElementById("stat-totalgb").textContent = stats.total_gb_downloaded;
  document.getElementById("stat-success").textContent = stats.success_rate + "%";
  document.getElementById("top-uploader").textContent = stats.top_uploader;
  document.getElementById("top-format").textContent = stats.top_format;

  const ctx1 = document.getElementById("chartDays");
  if (chartDays) {
    chartDays.data.labels = stats.chart_days_labels;
    chartDays.data.datasets[0].data = stats.chart_days_counts;
    chartDays.update();
  } else {
    chartDays = new Chart(ctx1, {
      type: "bar",
      data: {
        labels: stats.chart_days_labels,
        datasets: [{ label: "Downloads", data: stats.chart_days_counts, backgroundColor: "#3ea6ff" }],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#8b95ab" }, grid: { color: "rgba(255,255,255,0.05)" } },
          y: { ticks: { color: "#8b95ab" }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true },
        },
      },
    });
  }

  const ctx2 = document.getElementById("chartDisk");
  const usedGB = stats.disk_used_bytes / (1024 ** 3);
  const freeGB = stats.disk_free_bytes / (1024 ** 3);
  if (chartDisk) {
    chartDisk.data.datasets[0].data = [usedGB.toFixed(1), freeGB.toFixed(1)];
    chartDisk.update();
  } else {
    chartDisk = new Chart(ctx2, {
      type: "doughnut",
      data: {
        labels: ["Used", "Free"],
        datasets: [{ data: [usedGB.toFixed(1), freeGB.toFixed(1)], backgroundColor: ["#3ea6ff", "#232b3d"] }],
      },
      options: { plugins: { legend: { labels: { color: "#8b95ab" } } } },
    });
  }
}

async function refreshActivity() {
  let history;
  try { history = await apiGet("/api/history?scope=session"); } catch (e) { return; }
  const feed = document.getElementById("recent-activity");
  if (!history.length) { feed.innerHTML = '<div class="text-muted small">No activity yet.</div>'; return; }
  feed.innerHTML = history.slice(0, 10).map(h => `
    <div class="activity-item">
      <b>${h.title}</b> -- ${h.status} -- ${new Date(h.date_completed * 1000).toLocaleString()}
    </div>
  `).join("");
}

refreshDashboard();
refreshActivity();
setInterval(refreshDashboard, 3000);
setInterval(refreshActivity, 5000);
