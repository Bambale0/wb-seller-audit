const API = "https://apix.chillcreative.ru/wb-audit/api/v1/captures/analyze";
const statusEl = document.getElementById("status");

async function getCaptures() {
  const stored = await chrome.storage.local.get({ captures: [] });
  return stored.captures || [];
}

document.getElementById("analyze").onclick = async () => {
  const captures = await getCaptures();
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
  const captures = await getCaptures();
  const blob = new Blob([JSON.stringify(captures, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({url, filename: "mpstats-captures.json", saveAs: true});
};

document.getElementById("clear").onclick = async () => {
  await chrome.storage.local.set({captures: []});
  statusEl.textContent = "Перехват очищен";
};

getCaptures().then((captures) => {
  statusEl.textContent = "Перехвачено ответов: " + captures.length;
});
