// Settings page: load current settings into the form, save on submit.

const form = document.getElementById("settingsForm");

async function loadSettings() {
  const s = await apiGet("/api/settings");
  for (const el of form.elements) {
    if (!el.name || !(el.name in s)) continue;
    if (el.type === "checkbox") el.checked = !!s[el.name];
    else el.value = s[el.name];
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    data[el.name] = el.type === "checkbox" ? el.checked : el.value;
  }
  await apiPost("/api/settings", data);
  toast("success", "Settings saved");
});

loadSettings();
