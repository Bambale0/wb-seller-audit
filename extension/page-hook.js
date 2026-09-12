(() => {
  if (window.__WB_SELLER_AUDIT_HOOKED__) return;
  window.__WB_SELLER_AUDIT_HOOKED__ = true;

  const emit = (url, status, body) => {
    try {
      const serialized = JSON.stringify(body);
      if (serialized.length > 5000000) return;
      window.postMessage({
        source: "WB_SELLER_AUDIT",
        capture: { url, status, captured_at: new Date().toISOString(), body }
      }, "*");
    } catch (_) {}
  };

  const originalFetch = window.fetch;
  window.fetch = async (...args) => {
    const response = await originalFetch(...args);
    try {
      const url = String(response.url || args[0] || "");
      const type = response.headers.get("content-type") || "";
      if (url.includes("mpstats") && type.includes("json")) {
        emit(url, response.status, await response.clone().json());
      }
    } catch (_) {}
    return response;
  };

  const originalOpen = XMLHttpRequest.prototype.open;
  const originalSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    this.__wbsa_url = String(url || "");
    return originalOpen.call(this, method, url, ...rest);
  };
  XMLHttpRequest.prototype.send = function(...args) {
    this.addEventListener("load", function() {
      try {
        const type = this.getResponseHeader("content-type") || "";
        if (this.__wbsa_url && this.__wbsa_url.includes("mpstats") && type.includes("json")) {
          const body = typeof this.response === "string" ? JSON.parse(this.response) : this.response;
          emit(this.__wbsa_url, this.status, body);
        }
      } catch (_) {}
    });
    return originalSend.apply(this, args);
  };
})();
