/* Loads the conversation panel on first use. It is a self-contained widget in a
   shadow tree (talk/web/panel.js), fetched only when the button is first pressed,
   so a reader that is never used for speaking pays nothing for it. */
(function () {
  "use strict";
  const btn = document.getElementById("talkBtn");
  let panel = null, loading = false;
  const t = (k, p) => window.LumenI18n.t(k, p);

  fetch("/api/talk-available")
    .then((r) => r.json())
    .then((d) => { if (d.available) btn.hidden = false; })
    .catch(() => {});

  function here() {
    const { S, P } = window.LumenApp;
    const u = S.units[P.idx];
    return S.doc ? { doc_id: S.doc.doc_id, para: u ? u.pi : 0 } : null;
  }

  btn.onclick = async () => {
    const { P } = window.LumenApp;
    if (panel) { panel.toggle(); btn.setAttribute("aria-pressed", panel.visible()); return; }
    if (loading) return;
    loading = true;
    btn.textContent = t("header.talk_loading");
    try {
      if (!window.mountTalkPanel) {
        await new Promise((ok, no) => {
          const s = document.createElement("script");
          s.src = "/talk/panel.js";
          s.onload = ok; s.onerror = () => no(new Error("load failed"));
          document.head.appendChild(s);
        });
      }
      panel = window.mountTalkPanel({
        getContext: here,
        i18n: window.LumenI18n,
        getTargetLang: () => window.LumenApp.targetLang(),
        getSettings: () => window.LumenApp.S.settings,
        // talking over the reader should stop the reader, not compete with it
        pauseHost: () => { if (P.playing) window.dispatchEvent(new CustomEvent("lumen:pause")); },
      });
      btn.setAttribute("aria-pressed", "true");
    } catch (e) {
      window.LumenApp.sayKey("talk.load_failed", null, 4000);
    }
    btn.textContent = t("header.talk");
    loading = false;
  };

  window.addEventListener("lumen:langchange", () => {
    if (!loading) btn.textContent = t("header.talk");
  });
})();
