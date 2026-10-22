/* Settings, About and first-run onboarding.
 *
 * All three are plain panels declared in index.html with data-i18n markup; this
 * file only wires values to controls and re-fills the few parts that are built
 * from data (model lists, voice list, OCR status, licence table). Changing the
 * language here goes through the same path as the header switch. */
(function () {
  "use strict";
  const A = window.LumenApp;
  const { S, t, $ } = { S: A.S, t: A.t, $: (id) => document.getElementById(id) };

  /* ------------------------------------------------------------ settings panel */
  function mtRows() {
    const list = $("mtList");
    list.innerHTML = "";
    const cfg = S.cfg;
    if (!cfg) return;
    const target = A.targetLang();
    cfg.mt.backends.filter((b) => b.targets.includes(target)).forEach((b) => {
      if (!b.available) {
        const row = document.createElement("div");
        row.className = "mopt";
        const name = document.createElement("span");
        name.textContent = b.label; name.dir = "ltr";
        const why = document.createElement("span");
        why.className = "mwhy"; why.dir = "ltr";
        why.textContent = `${b.reason} — ${b.notes}`;
        row.append(name, why);
        list.appendChild(row);
        return;
      }
      b.models.filter((m) => m.targets.includes(target)).forEach((m) => {
        const row = document.createElement("div");
        const sel = S.mt.backend === b.id && S.mt.model === m.id;
        row.className = "mopt" + (sel ? " sel" : "");
        row.tabIndex = 0;
        row.setAttribute("role", "radio");
        row.setAttribute("aria-checked", String(sel));
        const name = document.createElement("span");
        name.textContent = m.label; name.dir = "ltr";
        const why = document.createElement("span");
        why.className = "mwhy"; why.dir = "ltr";
        why.textContent = m.license ? `${b.id} · ${m.license}` : b.id;
        row.append(name, why);
        const choose = async () => {
          const choice = { ...(S.settings.mt_choice || {}), [target]: { backend: b.id, model: m.id } };
          A.saveSettings({ mt_choice: choice });
          A.syncMt();
          A.resetTranslations();
          refresh();
          A.sayKey("settings.mt_changed", { model: m.id });
        };
        row.onclick = choose;
        row.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(); } };
        list.appendChild(row);
      });
    });
    if (!list.childElementCount) {
      const p = document.createElement("p");
      p.className = "set-note";
      p.textContent = t("settings.no_mt");
      list.appendChild(p);
    }
  }

  function voiceRows() {
    const sel = $("setVoice");
    sel.innerHTML = "";
    A.readingVoices().forEach((v) => {
      const o = document.createElement("option");
      o.value = v.key;
      o.textContent = `${v.label} (${v.engine})`;
      if (v.engine === S.engine && v.id === S.voice) o.selected = true;
      sel.appendChild(o);
    });
    if (!sel.options.length) {
      const o = document.createElement("option");
      o.textContent = t("voice.none");
      sel.appendChild(o);
    }
  }

  function ocrNote() {
    const o = (S.cfg && S.cfg.ocr) || {};
    const el = $("ocrStatus");
    if (o.available) {
      el.textContent = t(o.has_ara ? "settings.ocr_ready_ara" : "settings.ocr_ready", { version: o.version });
    } else {
      el.textContent = t(`settings.ocr_${o.reason || "no_tesseract"}`);
    }
    $("setOcrAr").disabled = !o.available || !o.has_ara;
  }

  function refresh() {
    const s = S.settings;
    $("setLang").value = window.LumenI18n.pref;
    $("setTheme").value = s.theme || "system";
    $("setScale").value = String(s.text_scale || 100);
    $("setShowTr").checked = !!s.show_translation;
    $("setTarget").value = s.translation_target;
    $("setAutoHints").checked = !!s.arabic_hints;
    $("setOcr").checked = !!s.ocr_enabled;
    $("setOcrAr").checked = !!s.ocr_arabic;
    $("setSpeed").value = String(S.speed);
    $("setSpeedOut").textContent = `${S.speed}×`;
    mtRows(); voiceRows(); ocrNote();
  }

  function bind() {
    $("settingsBtn").onclick = async () => {
      refresh();
      $("settingsPanel").hidden = false;                 // open at once, then refresh from the server
      try { A.applyConfig(await A.api("/api/config")); refresh(); } catch (e) { /* use what we have */ }
    };
    $("closeSettings").onclick = () => { $("settingsPanel").hidden = true; };
    $("aboutBtn").onclick = openAbout;
    $("closeAbout").onclick = () => { $("aboutPanel").hidden = true; };

    $("setLang").onchange = (e) => A.setUiLang(e.target.value);
    $("setTheme").onchange = (e) => { A.applyTheme(e.target.value); A.saveSettings({ theme: e.target.value }); };
    // saveSettings updates S.settings synchronously and persists in the background,
    // so each control takes effect at once instead of after a network round trip
    $("setScale").onchange = (e) => {
      A.saveSettings({ text_scale: Number(e.target.value) });
      A.applyTextScale();
    };
    $("setShowTr").onchange = (e) => {
      A.saveSettings({ show_translation: e.target.checked });
      A.applyShowTranslation();
    };
    $("setTarget").onchange = (e) => {
      A.saveSettings({ translation_target: e.target.value });
      A.syncMt();
      A.applyTargetLabels();
      A.relabelAllHints();
      A.resetTranslations();
      refresh();
    };
    $("setAutoHints").onchange = (e) => A.saveSettings({ arabic_hints: e.target.checked });
    $("setOcr").onchange = (e) => A.saveSettings({ ocr_enabled: e.target.checked });
    $("setOcrAr").onchange = (e) => A.saveSettings({ ocr_arabic: e.target.checked });
    $("setVoice").onchange = (e) => {
      const v = A.readingVoices().find((x) => x.key === e.target.value);
      if (v) A.setVoice(v);
    };
    $("setSpeed").oninput = (e) => {
      const v = Number(e.target.value);
      $("setSpeedOut").textContent = `${v}×`;
    };
    $("setSpeed").onchange = (e) => {
      const v = Number(e.target.value);
      S.speed = v;
      $("speed").value = String(v);
      A.saveSettings({ tts_speed: v });
      A.resetAudio();
    };

    const clear = async (what, confirmKey, doneKey) => {
      if (!window.confirm(t(confirmKey))) return;
      const r = await A.post("/api/cache/clear", { what });
      A.sayKey(doneKey, { n: r.removed != null ? r.removed : r.docs });
      if (what === "translations") A.resetTranslations();
    };
    $("clearTr").onclick = () => clear("translations", "settings.confirm_clear_tr", "settings.cleared_tr");
    $("clearDocs").onclick = () => clear("documents", "settings.confirm_clear_docs", "settings.cleared_docs");
  }

  /* ------------------------------------------------------------ about */
  async function openAbout() {
    $("aboutPanel").hidden = false;
    try {
      const d = await A.api("/api/about");
      $("aboutVer").textContent = d.version;
      $("aboutRepo").href = d.upstream.repo;
      $("aboutPaper").href = d.upstream.paper;
      const body = $("aboutModels");
      body.innerHTML = "";
      d.models.forEach((m) => {
        const tr = document.createElement("tr");
        const a = document.createElement("a");
        a.href = m.url; a.target = "_blank"; a.rel = "noopener"; a.textContent = m.name;
        const name = document.createElement("td"); name.appendChild(a);
        const role = document.createElement("td"); role.textContent = t(`about.role_${m.role}`);
        const lic = document.createElement("td");
        lic.textContent = m.license === "per-model-card" ? t("about.per_card")
          : m.license === "per-voice-card" ? t("about.per_card") : m.license;
        tr.append(name, role, lic);
        body.appendChild(tr);
      });
    } catch (e) {
      $("aboutVer").textContent = "?";
    }
  }

  /* ------------------------------------------------------------ onboarding */
  const ONBOARDED = "lumen.onboarded";

  function onboarding() {
    if (A.mem.get(ONBOARDED, "") === "1") return;
    const box = $("onboard");
    box.hidden = false;
    const segs = box.querySelectorAll(".seg button");
    const mark = () => segs.forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.lang === window.LumenI18n.pref)));
    segs.forEach((b) => { b.onclick = async () => { await A.setUiLang(b.dataset.lang); mark(); }; });
    window.addEventListener("lumen:langchange", mark);
    mark();
    $("onTr").checked = !!S.settings.show_translation;
    $("onGo").onclick = async () => {
      A.saveSettings({ show_translation: $("onTr").checked });
      A.applyShowTranslation();
      A.mem.set(ONBOARDED, "1");
      box.hidden = true;
    };
    $("onGo").focus();
  }

  window.addEventListener("lumen:langchange", () => {
    if (!$("settingsPanel").hidden) refresh();
    if (!$("aboutPanel").hidden) openAbout();
  });

  window.LumenSettings = { refresh, openAbout };
  bind();
  document.addEventListener("lumen:ready", onboarding, { once: true });
})();
