const API = "https://apix.chillcreative.ru/wb-audit/api/v1/captures/analyze";
const statusEl = document.getElementById("status");
const toggleEl = document.getElementById("toggle");

async function getState() {
  return chrome.storage.local.get({
    capture_enabled: false,
    captures: []
  });
}

async function render() {
  const state = await getState();
  toggleEl.textContent = state.capture_enabled ? "Остановить перехват" : "Включить перехват";
  statusEl.textContent =
    (state.capture_enabled ? "Перехват включён" : "Перехват выключен") +
    "\nОтветов: " + (state.captures || []).length;
}

toggleEl.onclick = async () => {
  const state = await getState();
  await chrome.storage.local.set({capture_enabled: !state.capture_enabled});
  await render();
};

document.getElementById("analyze").onclick = async () => {
  const state = await getState();
  const captures = state.captures || [];
  statusEl.textContent = "Отправляю " + captures.length + " ответов...";
  try {
    const response = await fetch(API, {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({
        seller_id: Number(document.getElementById("seller").value) || null,
        captures
      })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(data));
    statusEl.textContent =
      "Записей: " + data.records +
      "\nВыручка: " + data.total_revenue +
      "\nПервая маркируемая: " + (data.first_marked_candidate_sale || "—") +
      "\nЛимит НПД: " + (data.first_npd_limit_exceeded || "—");
  } catch (error) {
    statusEl.textContent = "Ошибка: " + error.message;
  }
};

document.getElementById("export").onclick = async () => {
  const state = await getState();
  const captures = state.captures || [];
  const blob = new Blob([JSON.stringify(captures, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({url, filename: "mpstats-captures.json", saveAs: true});
};

document.getElementById("clear").onclick = async () => {
  await chrome.storage.local.set({captures: []});
  await render();
};

render();
