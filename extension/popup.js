const CAPTURE_API = "https://apix.chillcreative.ru/wb-audit/api/v1/captures/analyze";
const WB_PUBLIC_ANALYZE_API = "https://apix.chillcreative.ru/wb-audit/api/v1/sources/wb-public/analyze";
const WB_PUBLIC_EVIDENCE_API = "https://apix.chillcreative.ru/wb-audit/api/v1/sources/wb-public/evidence";
const WB_CATALOG_API = "https://catalog.wb.ru/sellers/v4/catalog";

const statusEl = document.getElementById("status");
const toggleEl = document.getElementById("toggle");

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function getState() {
  return chrome.storage.local.get({
    capture_enabled: false,
    captures: []
  });
}

async function render() {
  const state = await getState();
  toggleEl.textContent = state.capture_enabled ? "Остановить перехват MPStats" : "Включить перехват MPStats";
  statusEl.textContent =
    (state.capture_enabled ? "Перехват MPStats включён" : "Перехват MPStats выключен") +
    "\nОтветов: " + (state.captures || []).length;
}

function sellerId() {
  return Number(document.getElementById("seller").value) || null;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"content-type": "application/json"},
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(data));
  return data;
}

async function fetchCatalogPage(seller, page) {
  const url = new URL(WB_CATALOG_API);
  url.search = new URLSearchParams({
    ab_testing: "false",
    appType: "1",
    curr: "rub",
    dest: "-1257786",
    hide_dtype: "13",
    lang: "ru",
    limit: "100",
    page: String(page),
    sort: "popular",
    spp: "30",
    supplier: String(seller)
  }).toString();

  let lastError = null;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch(url.toString(), {
        headers: {accept: "application/json, text/plain, */*"}
      });
      if (response.ok) return response.json();

      lastError = new Error("WB HTTP " + response.status);
      if (![403, 429, 498].includes(response.status)) break;
    } catch (error) {
      lastError = error;
    }
    await sleep(700 * (attempt + 1));
  }

  throw lastError || new Error("WB public API недоступен");
}

async function fetchSellerCatalog(seller, maxPages = 50) {
  const pages = [];
  let collected = 0;
  let total = null;

  for (let page = 1; page <= maxPages; page += 1) {
    statusEl.textContent =
      "WB public: загружаю страницу " + page +
      (total === null ? "" : "\nТоваров: " + collected + " / " + total);

    const payload = await fetchCatalogPage(seller, page);
    const products = payload?.data?.products || payload?.products || [];
    if (!Array.isArray(products) || products.length === 0) break;

    pages.push(payload);
    collected += products.length;

    const rawTotal = Number(payload?.data?.total ?? payload?.total);
    if (Number.isFinite(rawTotal) && rawTotal >= 0) total = rawTotal;
    if (total !== null && collected >= total) break;

    await sleep(220);
  }

  return pages;
}

toggleEl.onclick = async () => {
  const state = await getState();
  await chrome.storage.local.set({capture_enabled: !state.capture_enabled});
  await render();
};

document.getElementById("publicAudit").onclick = async () => {
  const seller = sellerId();
  if (!seller) {
    statusEl.textContent = "Укажи Seller ID.";
    return;
  }

  try {
    statusEl.textContent = "WB public: начинаю сбор...";
    const pages = await fetchSellerCatalog(seller);
    if (pages.length === 0) throw new Error("WB не вернул товары продавца");

    statusEl.textContent = "Разбираю текущий каталог...";
    const catalog = await postJson(WB_PUBLIC_ANALYZE_API, {
      seller_id: seller,
      pages
    });

    statusEl.textContent =
      "Товаров: " + catalog.products +
      "\nКандидатов на маркировку: " + catalog.marked_candidates +
      "\nПроверяю card.json, КИЗ, цены и отзывы...";

    const evidence = await postJson(WB_PUBLIC_EVIDENCE_API, {
      seller_id: seller,
      pages,
      marked_only: true,
      max_items: 30
    });

    statusEl.textContent =
      "Источник: WB public" +
      "\nТоваров: " + catalog.products +
      "\nКандидатов на маркировку: " + catalog.marked_candidates +
      "\nWB need_kiz=true: " + evidence.wb_need_kiz_true +
      "\nСамая ранняя карточка: " + (evidence.earliest_marked_card_created || "—") +
      "\nСамый ранний найденный отзыв: " + (evidence.earliest_marked_observed_review || "—") +
      "\n\nОтзыв = подтверждённый выкуп не позднее этой даты." +
      "\nИсторическую выручку считаем только по отдельному источнику/отчётам.";
  } catch (error) {
    statusEl.textContent = "Ошибка WB public: " + error.message;
  }
};

document.getElementById("analyze").onclick = async () => {
  const state = await getState();
  const captures = state.captures || [];
  statusEl.textContent = "Отправляю " + captures.length + " ответов...";
  try {
    const data = await postJson(CAPTURE_API, {
      seller_id: sellerId(),
      captures
    });
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
