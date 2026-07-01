const ALL_PAGE_IDS = [
  "dashboard", "analytics", "members", "joins", "member-stats",
  "exceptions", "server-joins", "leaves", "events", "message-logs",
  "qna", "automations",
];

export function getAdminPage() {
  const seg = window.location.pathname.replace(/^\/admin\/?/, "").split("/")[0];
  return ALL_PAGE_IDS.includes(seg) ? seg : "dashboard";
}

export function getUrlParam(key, fallback = "") {
  return new URLSearchParams(window.location.search).get(key) ?? fallback;
}

export function pushAdminPage(pageId) {
  history.pushState(null, "", `/admin/${pageId}`);
}

export function replaceUrlParams(updates) {
  const sp = new URLSearchParams(window.location.search);
  for (const [k, v] of Object.entries(updates)) {
    if (v === null || v === undefined || v === "") sp.delete(k);
    else sp.set(k, v);
  }
  const qs = sp.toString();
  history.replaceState(null, "", `${window.location.pathname}${qs ? `?${qs}` : ""}`);
}
