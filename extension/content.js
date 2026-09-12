(() => {
  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("page-hook.js");
  script.onload = () => script.remove();
  (document.documentElement || document.head).appendChild(script);

  window.addEventListener("message", async (event) => {
    if (event.source !== window || event.data?.source !== "WB_SELLER_AUDIT") return;
    const stored = await chrome.storage.local.get({ captures: [] });
    const captures = stored.captures || [];
    captures.push(event.data.capture);
    await chrome.storage.local.set({ captures: captures.slice(-100) });
  });
})();
