/* LumenRead · conversation window
 *
 * One file, no dependencies, no build step. It builds its own root inside a
 * shadow tree, so it can be dropped into the reader's page later without a
 * single style colliding:
 *
 *     <script src="/talk/panel.js"></script>
 *     <script>mountTalkPanel({ getContext: () => ({doc_id, para}) })</script>
 *
 * and it is the same window either way — which is the point. A conversation
 * about the paragraph you are reading should sit *over* the paragraph, not
 * replace it with a different screen.
 *
 * The window is split the way the practice is: the tutor speaks on the left
 * with captions that follow the voice, and everything that is *yours* is on
 * the right — what you said above, what was wrong with it below. Corrections
 * never interrupt the conversation; they accumulate beside it.
 */
(function () {
  "use strict";

  /* Direction: the window's own chrome follows the UI language (dir on .win);
     everything the tutor and the learner *say* is English and is marked
     dir="ltr" lang="en" wherever it is rendered. Arabic (or Chinese) appears only
     in opt-in hint boxes, with its own lang/dir. CSS uses logical properties. */
  const CSS = `
:host { all: initial; }
*, *::before, *::after { box-sizing: border-box; }

/* The panes below set display:grid and display:flex, which outrank the
   browser's own [hidden] { display: none }. Without this rule, hiding the
   conversation to show the setup screen silently does nothing and the two
   stack on top of each other. Keep it above every component. */
[hidden] { display: none !important; }

.win {
  --ink:#0F172A; --graphite:#475569; --faint:#64748B;
  --surface:#F8FAFC; --card:#FFFFFF; --rule:#E2E8F0;
  --marker:#F59E0B; --marker-soft:#FDE7B0; --indigo:#1D4ED8; --live:#B91C1C;
  --sans:"Inter","Cairo",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --serif:"Source Serif 4",Georgia,"Times New Roman",serif;
  --naskh:"Noto Naskh Arabic","Cairo","Traditional Arabic",serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --han:"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif;

  position: fixed; z-index: 2147483000;
  display: flex; flex-direction: column;
  width: 780px; height: 580px; min-width: 360px; min-height: 260px;
  background: var(--card); color: var(--ink);
  font-family: var(--sans); font-size: 14px; line-height: 1.5;
  border: 1px solid var(--rule); border-radius: 10px;
  box-shadow: 0 1px 2px rgba(22,32,43,.08), 0 18px 48px rgba(22,32,43,.18);
  overflow: hidden;
}
.win.dark {
  --ink:#E2E8F0; --graphite:#A9B6C9; --faint:#8797AE;
  --surface:#0B1220; --card:#111B2E; --rule:#243248;
  --marker:#F59E0B; --marker-soft:#5B4210; --indigo:#8FB0FF; --live:#FCA5A5;
  box-shadow: 0 1px 2px rgba(0,0,0,.5), 0 18px 48px rgba(0,0,0,.45);
}
.win.flat { position: relative; width: 100%; height: 100%; border: 0; border-radius: 0; box-shadow: none; }
.win.min { height: auto !important; }
.win.min .main, .win.min .strip, .win.min .compose { display: none; }

button, select, input, textarea { font: inherit; color: inherit; }
button {
  background: transparent; border: 1px solid transparent; border-radius: 6px;
  padding: 3px 8px; cursor: pointer; color: var(--graphite);
}
button:hover { background: color-mix(in srgb, var(--ink) 7%, transparent); color: var(--ink); }
button:focus-visible, select:focus-visible, input:focus-visible {
  outline: 2px solid var(--indigo); outline-offset: 1px;
}
button.icon { padding: 3px 6px; font-size: 13px; }
button.primary { background: #1D4ED8; color: #fff; border-color: #1D4ED8; font-weight: 500; }
button.primary:hover { filter: brightness(1.08); background: #1D4ED8; color: #fff; }
.win.dark button.primary { background: #2F5FE0; border-color: #2F5FE0; }
button[disabled] { opacity: .45; cursor: default; }
.spacer { flex: 1; }

/* -------------------------------------------------------------- title bar */
.bar {
  display: flex; align-items: center; gap: 8px; flex: none;
  padding: 8px 10px; cursor: grab; user-select: none;
  background: var(--surface); border-bottom: 1px solid var(--rule);
}
.bar:active { cursor: grabbing; }
.win.flat .bar { cursor: default; }
.grip { width: 10px; height: 14px; flex: none; opacity: .45;
  background-image: radial-gradient(currentColor 1px, transparent 1px); background-size: 4px 4px; }
.title { font-weight: 600; font-size: 13px; white-space: nowrap; flex: none; }
.now { font-size: 12px; color: var(--graphite); font-family: var(--sans);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--faint); flex: none; }
.dot.on { background: #3f9160; }
.dot.off { background: var(--live); }

/* -------------------------------------------------------------- setup */
.setup { padding: 26px 22px; font-family: var(--sans); overflow-y: auto; }
.setup h3 { margin: 0 0 4px; font-size: 16px; font-weight: 600; }
.setup p { margin: 0 0 16px; font-size: 12.5px; color: var(--graphite); line-height: 1.7; }
.modes { display: flex; gap: 7px; margin-bottom: 12px; flex-wrap: wrap; }
.mode {
  padding: 5px 12px; border-radius: 999px; border: 1px solid var(--rule);
  font-size: 13px; color: var(--graphite); cursor: pointer; background: transparent;
}
.mode:hover { border-color: var(--graphite); }
.mode.on { border-color: var(--indigo); color: var(--indigo); font-weight: 500;
  background: color-mix(in srgb, var(--indigo) 8%, transparent); }
.setup .field { margin-bottom: 12px; }
.setup input, .setup select {
  width: 100%; background: var(--card); border: 1px solid var(--rule);
  border-radius: 7px; padding: 7px 9px; font-size: 13px;
}
.setup .why { font-size: 11.5px; color: var(--faint); margin-top: 5px; line-height: 1.6; }
.setup .go { margin-top: 4px; }

/* -------------------------------------------------------------- main split */
.main { flex: 1; min-height: 0; display: grid; grid-template-columns: 1.05fr 1fr; }
.win.narrow .main { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
.pane { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.pane + .pane { border-inline-start: 1px solid var(--rule); }
.win.narrow .pane + .pane { border-inline-start: 0; border-top: 1px solid var(--rule); }

.head {
  flex: none; display: flex; align-items: center; gap: 7px;
  padding: 6px 11px; border-bottom: 1px solid var(--rule);
  font-family: var(--mono); font-size: 10.5px; letter-spacing: .09em;
  text-transform: uppercase; color: var(--faint);
}
.head button { font-family: var(--sans); font-size: 11px; text-transform: none; letter-spacing: 0; }

/* -------------------------------------------------------------- tutor side */
.stage { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 14px 10px; }
.cap {
  font-family: var(--serif); font-size: 19px; line-height: 1.55; margin-bottom: 14px;
}
.cap .s { color: var(--faint); transition: color .15s ease; }
.cap .s.on { color: var(--ink); background: var(--marker-soft); border-radius: 2px; }
.cap .s.done { color: var(--ink); }
.cap.idle .s { color: var(--ink); }
.cap mark { background: var(--marker-soft); color: inherit; border-radius: 2px; padding: 0 1px; }
.past { border-top: 1px dashed var(--rule); padding-top: 10px; }
.past .line {
  font-family: var(--serif); font-size: 13.5px; line-height: 1.6;
  color: var(--graphite); margin-bottom: 9px; cursor: pointer;
}
.past .line:hover { color: var(--ink); }
.thinking { color: var(--faint); font-style: italic; font-family: var(--serif); font-size: 17px; }

/* -------------------------------------------------------------- my side */
.mine { flex: 1; min-height: 0; overflow-y: auto; padding: 12px 13px 8px; }
.said { margin-bottom: 11px; }
.said .txt { font-size: 14px; line-height: 1.6; }
.said .txt mark { background: var(--marker-soft); color: inherit; border-radius: 2px; padding: 0 1px; }
.said.old .txt { color: var(--graphite); font-size: 13px; }
.said .row { display: flex; align-items: center; gap: 6px; margin-top: 4px; flex-wrap: wrap; }
.chip {
  font-family: var(--mono); font-size: 10.5px; padding: 1px 6px; border-radius: 999px;
  border: 1px solid var(--rule); color: var(--graphite); background: var(--card);
}
.chip.good { border-color: #3f9160; color: #3f9160; }
.chip.mid  { border-color: #b08320; color: #b08320; }
.chip.poor { border-color: var(--live); color: var(--live); }
.chip.act { cursor: pointer; }
.chip.act:hover { background: var(--surface); }
.live {
  font-size: 14px; line-height: 1.6; color: var(--faint); font-style: italic;
  border-inline-start: 2px solid var(--live); padding-inline-start: 8px; min-height: 22px;
}
.live.on { color: var(--graphite); }

/* -------------------------------------------------------------- coach */
.fix {
  flex: none; height: 44%; min-height: 96px; border-top: 1px solid var(--rule);
  display: flex; flex-direction: column;
}
.fixbody { flex: 1; min-height: 0; overflow-y: auto; padding: 11px 13px; font-family: var(--sans); }
.fixnone { color: var(--faint); font-size: 12px; line-height: 1.7; }
.card { margin-bottom: 13px; }
.card .orig {
  font-family: var(--sans); font-size: 12.5px; color: var(--faint);
  text-decoration: line-through; text-decoration-color: var(--rule); margin-bottom: 3px;
}
.card .new { font-family: var(--sans); font-size: 14px; line-height: 1.55; }
.card .new mark {
  background: var(--marker-soft); color: inherit; border-radius: 2px;
  padding: 0 2px; font-weight: 500;
}
.card .why {
  font-size: 12px; color: var(--graphite); margin-top: 5px;
  border-inline-start: 2px solid var(--marker); padding-inline-start: 8px; line-height: 1.65;
}
.card .phon { margin-top: 5px; font-family: var(--mono); font-size: 11.5px; letter-spacing: .04em; }
.phon .sub { color: var(--live); }
.phon .miss { color: #b08320; text-decoration: line-through; }
.phon .extra { color: var(--indigo); opacity: .8; }
.card.ok .new { color: var(--graphite); font-size: 13px; }

/* -------------------------------------------------------------- word strip */
.strip {
  flex: none; display: flex; gap: 5px; align-items: center;
  padding: 7px 10px; border-top: 1px solid var(--rule);
  overflow-x: auto; scrollbar-width: none;
}
.strip::-webkit-scrollbar { display: none; }
.strip .lab { font-size: 10.5px; color: var(--faint); font-family: var(--sans); white-space: nowrap; flex: none; }
.word {
  position: relative; z-index: 0; flex: none; font-size: 12px; padding: 2px 8px;
  border-radius: 999px; border: 1px solid var(--rule); color: var(--faint);
  white-space: nowrap; overflow: hidden; transition: color .2s ease, border-color .2s ease;
}
.word::before {
  content: ""; position: absolute; inset: 0; z-index: -1;
  transform-origin: left center; transform: scaleX(0); background: var(--marker-soft);
}
.win[dir="rtl"] .word::before { transform-origin: right center; }
.word.heard { color: var(--graphite); border-color: var(--marker); }
.word.said { color: var(--ink); border-color: var(--marker); font-weight: 500; }
.word.said::before { animation: sweep .45s cubic-bezier(.4,0,.2,1) forwards; }
@keyframes sweep { to { transform: scaleX(1); } }
@media (prefers-reduced-motion: reduce) {
  .word.said::before { animation: none; transform: scaleX(1); }
}

/* -------------------------------------------------------------- composer */
.compose {
  flex: none; display: flex; align-items: center; gap: 9px;
  padding: 9px 10px; border-top: 1px solid var(--rule); background: var(--surface);
}
.mic {
  flex: none; width: 38px; height: 38px; border-radius: 50%; padding: 0;
  border: 1px solid var(--rule); background: var(--card);
  display: grid; place-items: center; cursor: pointer;
}
.mic:hover { background: var(--card); border-color: var(--graphite); }
.mic .core { width: 13px; height: 13px; border-radius: 50%; background: var(--graphite); }
.mic.live { border-color: var(--live); }
.mic.live .core { background: var(--live); border-radius: 3px; animation: pulse 1.1s ease-in-out infinite; }
@keyframes pulse { 50% { transform: scale(.7); } }
.mic[disabled] { opacity: .4; cursor: default; }
.say {
  flex: 1; min-width: 0; background: var(--card); border: 1px solid var(--rule);
  border-radius: 8px; padding: 7px 9px; font-size: 13px; font-family: var(--serif);
}
.hint { font-size: 10.5px; color: var(--faint); font-family: var(--sans); }
.hint b { color: var(--graphite); font-weight: 500; }

/* -------------------------------------------------------------- overlays */
.sheet {
  position: absolute; inset-inline-end: 8px; inset-block-start: 38px; z-index: 5; width: 250px;
  background: var(--card); border: 1px solid var(--rule); border-radius: 9px;
  box-shadow: 0 10px 30px rgba(22,32,43,.18); padding: 10px; font-size: 12px;
  font-family: var(--sans);
}
.sheet h4 { margin: 0 0 7px; font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
  color: var(--faint); font-family: var(--mono); font-weight: 500; }
.sheet .r { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.sheet .r .k { color: var(--graphite); flex: 1; }
.sheet .r .v { font-family: var(--mono); font-size: 11px; text-align: end;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 132px; }
.sheet label { display: flex; align-items: center; gap: 6px; cursor: pointer;
  color: var(--graphite); margin-bottom: 5px; }
.sheet hr { border: 0; border-top: 1px solid var(--rule); margin: 9px 0; }
.sheet .acts { display: flex; gap: 6px; }
.sheet .acts button { border-color: var(--rule); font-size: 11.5px; }

.note {
  position: absolute; inset-inline: 0; margin-inline: auto; width: fit-content; bottom: 64px;
  background: var(--ink); color: var(--card); font-size: 12px; font-family: var(--sans);
  padding: 5px 11px; border-radius: 999px; z-index: 6; pointer-events: none;
  opacity: 0; transition: opacity .18s ease; max-width: 80%; text-align: center;
}
.note.on { opacity: .93; }

.grab { position: absolute; inset-block-end: 0; width: 15px; height: 15px; cursor: nwse-resize; z-index: 4;
  background: linear-gradient(135deg, transparent 55%, var(--faint) 55% 66%, transparent 66% 77%, var(--faint) 77% 88%, transparent 88%); }
.win.flat .grab { display: none; }

/* opt-in hint (Arabic / Chinese): its own language and direction, set in JS */
.hintbtn { margin-block-start: 6px; font-size: 11.5px; border-color: var(--rule); }
.hintbox {
  margin-block-start: 6px; padding: 7px 10px; border-radius: 8px; background: var(--surface);
  border: 1px solid var(--rule); border-inline-start: 3px solid var(--marker);
  font-size: 13px; line-height: 1.8; text-align: start;
}
.hintbox:lang(ar) { font-family: var(--naskh); font-size: 15px; line-height: 2; }
.hintbox.err { color: var(--live); border-inline-start-color: var(--live); font-family: var(--sans); font-size: 12px; }
.cap, .said .txt, .live, .card .orig, .card .new, .past .line { text-align: start; }

::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: var(--rule); border-radius: 4px; }
`;

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function encodeWav(samples, sampleRate) {
    const buf = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buf);
    const w = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
    w(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); w(8, "WAVE");
    w(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
    view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
    view.setUint16(34, 16, true); w(36, "data");
    view.setUint32(40, samples.length * 2, true);
    let off = 44;
    for (let i = 0; i < samples.length; i++, off += 2) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([view], { type: "audio/wav" });
  }

  /* highlight the learner's target words inside a plain string */
  function markWords(text, words) {
    const frag = document.createDocumentFragment();
    if (!words || !words.length) { frag.appendChild(document.createTextNode(text)); return frag; }
    const stems = words.map((w) => (w.endsWith("e") && w.length > 4 ? w.slice(0, -1) : w));
    const re = new RegExp("\\b(" + stems.map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")
      + ")(s|es|ed|d|ing|ly|er|ers|ion|ions|al)?\\b", "gi");
    let last = 0, m;
    while ((m = re.exec(text)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(text.slice(last, m.index)));
      frag.appendChild(el("mark", null, m[0]));
      last = m.index + m[0].length;
    }
    if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
    return frag;
  }

  /* the coach wraps what it changed in *asterisks* */
  function markStars(text) {
    const frag = document.createDocumentFragment();
    const parts = String(text).split(/\*([^*]+)\*/g);
    parts.forEach((p, i) => {
      if (!p) return;
      frag.appendChild(i % 2 ? el("mark", null, p) : document.createTextNode(p));
    });
    return frag;
  }

  /** Tiny stand-in for js/i18n.js when the panel runs on its own page
      (talk.main serves /i18n/*.json too). Same t(key, params) contract. */
  function miniI18n(api) {
    const st = { lang: "en", dict: {}, fb: {} };
    const q = new URLSearchParams(location.search).get("lang");
    const nav = (navigator.languages || [navigator.language || "en"]).map((l) => String(l).slice(0, 2));
    st.lang = q === "ar" || q === "en" ? q : (nav.find((l) => l === "ar" || l === "en") || "en");
    const get = (k, d, lang) => {
      if (d && typeof d.n === "number") {
        let cat = "other";
        try { cat = new Intl.PluralRules(lang).select(d.n); } catch (e) { /* other */ }
        if (st.dict[`${k}_${cat}`] != null) return st.dict[`${k}_${cat}`];
        if (st.dict[`${k}_other`] != null) return st.dict[`${k}_other`];
      }
      return st.dict[k];
    };
    const api_ = {
      get lang() { return st.lang; },
      get dir() { return st.lang === "ar" ? "rtl" : "ltr"; },
      t(k, p) {
        let v = get(k, p, st.lang);
        if (v == null) v = st.fb[k];
        if (v == null) return k;
        return p ? v.replace(/\{(\w+)\}/g, (m, n) => (n in p ? p[n] : m)) : v;
      },
      ready: null,
    };
    const load = async (lang) => (await fetch(`${api}/i18n/${lang}.json`)).json();
    api_.ready = Promise.all([load(st.lang), load("en")]).then(([d, f]) => { st.dict = d; st.fb = f; })
      .catch(() => { /* keys show instead of text; still usable */ });
    return api_;
  }

  window.mountTalkPanel = function mountTalkPanel(opts) {
    opts = opts || {};
    const api = (opts.apiBase || "").replace(/\/$/, "");
    const I = opts.i18n || miniI18n(api);
    const T = (k, p) => I.t(k, p);
    // labels that are plain text or an attribute: re-applied on a language change
    const labels = [];
    const L = (node, key, prop, params) => { labels.push([node, key, prop || "textContent", params]); return node; };
    const relabel = () => labels.forEach(([n, k, prop, p]) => {
      if (prop === "textContent") n.textContent = T(k, p); else n[prop] = T(k, p);
    });
    const hintLang = () => (opts.getTargetLang ? opts.getTargetLang() : (I.lang === "ar" ? "ar" : "zh"));
    const faceOf = (lang) => (lang === "zh" ? { lang: "zh-Hans", dir: "ltr" } : { lang: "ar", dir: "rtl" });
    /** English content: always left-to-right, whatever the UI language. */
    const en = (node) => { node.lang = "en"; node.dir = "ltr"; return node; };
    const flat = !!opts.flat;
    const host = opts.host || document.body;

    const holder = el("div");
    holder.style.cssText = flat ? "position:static;height:100%"
      : "position:fixed;inset:0 auto auto 0;width:0;height:0";
    const shadow = holder.attachShadow({ mode: "open" });
    const style = el("style"); style.textContent = CSS; shadow.appendChild(style);

    const win = el("div", "win" + (flat ? " flat" : ""));
    shadow.appendChild(win);
    host.appendChild(holder);

    if (!flat) {
      win.style.left = Math.max(12, Math.round((window.innerWidth - 780) / 2)) + "px";
      win.style.top = Math.max(12, window.innerHeight - 640) + "px";
    }
    const isDark = () => ["dark", "black"].includes(document.documentElement.getAttribute("data-theme"))
      || (!document.documentElement.getAttribute("data-theme")
        && window.matchMedia("(prefers-color-scheme: dark)").matches);
    win.classList.toggle("dark", isDark());
    const applyDir = () => { win.dir = I.dir; win.lang = I.lang; win.classList.toggle("dark", isDark()); };
    applyDir();

    // ------------------------------------------------------------ chrome
    const bar = el("div", "bar");
    const title = el("span", "title", "");
    const now = el("span", "now", ""); now.dir = "auto";
    const dSt = el("span", "dot"); L(dSt, "talk.dot_stt", "title");
    const dLl = el("span", "dot"); L(dLl, "talk.dot_llm", "title");
    const dTt = el("span", "dot"); L(dTt, "talk.dot_voice", "title");
    const again = L(el("button"), "talk.new_topic");
    const gear = el("button", "icon", "⚙"); L(gear, "talk.settings", "title"); L(gear, "talk.settings", "ariaLabel");
    const mini = el("button", "icon", "–"); L(mini, "talk.minimize", "title"); L(mini, "talk.minimize", "ariaLabel");
    const shut = el("button", "icon", "✕"); L(shut, "common.close", "title"); L(shut, "common.close", "ariaLabel");
    bar.append(el("span", "grip"), title, dSt, dLl, dTt, now, el("span", "spacer"), again, gear, mini);
    if (!flat) bar.appendChild(shut);

    // ------------------------------------------------------------ setup
    const setup = el("div", "setup");
    const modes = el("div", "modes");
    const mFree = L(el("button", "mode on"), "talk.mode_free");
    const mTopic = L(el("button", "mode"), "talk.mode_topic");
    const mDoc = L(el("button", "mode"), "talk.mode_doc");
    modes.append(mFree, mTopic, mDoc);
    const fTopic = el("div", "field"); fTopic.hidden = true;
    const topicIn = el("input");
    en(topicIn); L(topicIn, "talk.topic_placeholder", "placeholder");
    fTopic.append(topicIn);
    const fDoc = el("div", "field"); fDoc.hidden = true;
    const picker = el("select");
    const docWhy = el("div", "why", "");
    fDoc.append(picker, docWhy);
    const goBtn = L(el("button", "primary go"), "talk.start");
    setup.append(L(el("h3"), "talk.setup_title"), L(el("p"), "talk.setup_body"),
      modes, fTopic, fDoc, goBtn);

    // ------------------------------------------------------------ main
    const main = el("div", "main"); main.hidden = true;   // setup owns the window first

    const paneT = el("div", "pane");
    const headT = el("div", "head");
    const replay = el("button");
    headT.append(L(el("span"), "talk.tutor"), el("span", "spacer"), replay);
    const stage = el("div", "stage");
    const cap = en(el("div", "cap"));
    const past = en(el("div", "past"));
    const hintHost = el("div", "hinthost");
    stage.append(cap, hintHost, past);
    paneT.append(headT, stage);

    const paneM = el("div", "pane");
    const headM = el("div", "head");
    headM.append(L(el("span"), "talk.you_said"));
    const mineWrap = el("div", "mine");
    const live = en(el("div", "live"));
    const fix = el("div", "fix");
    const headF = el("div", "head");
    headF.append(L(el("span"), "talk.corrections"));
    const fixBody = el("div", "fixbody");
    fix.append(headF, fixBody);
    paneM.append(headM, mineWrap, fix);

    main.append(paneT, paneM);

    // ------------------------------------------------------------ bottom
    const strip = el("div", "strip");
    const compose = el("div", "compose");
    const mic = el("button", "mic"); mic.innerHTML = '<span class="core"></span>';
    const say = en(el("input", "say")); L(say, "talk.type_placeholder", "placeholder");
    const hint = el("span", "hint");
    compose.append(mic, say, hint);

    const note = el("div", "note");
    const grab = el("div", "grab"); grab.style.right = "0";
    win.append(bar, setup, main, strip, compose, note, grab);

    const audio = new Audio();
    // 44 bytes of silence. Playing it during a real click satisfies the
    // browser's autoplay policy, so the tutor's first reply is audible instead
    // of being silently refused.
    const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAA"
      + "B9AAACABAAZGF0YQAAAAA=";
    let unlocked = false;
    function unlockAudio() {
      if (unlocked) return;
      unlocked = true;
      audio.muted = true;
      audio.src = SILENCE;
      const done = () => { audio.muted = false; };
      audio.play().then(() => { audio.pause(); done(); }).catch(done);
    }
    let sheet = null;
    let engaged = flat;   // does this window currently own the keyboard?

    // ------------------------------------------------------------ state
    const S = {
      session: null, mode: "free", topic: "", doc: null, para: null,
      docs: [], targets: [], heard: {}, said: {}, ever: {},
      autoplay: true, score: true, coach: true, interim: true,
      busy: false, health: null, capMarks: null, capSents: [],
    };

    const url = (p) => api + p;

    // Nothing here should be able to leave the window stuck on a spinner. Every
    // request carries its own deadline, and "new topic" cancels whatever is running.
    let flight = null;
    async function ask(path, init, seconds, label) {
      const ac = new AbortController();
      flight = ac;
      const t = setTimeout(() => ac.abort(), seconds * 1000);
      try {
        const r = await fetch(url(path), Object.assign({ signal: ac.signal }, init));
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          const det = d.detail;
          const msg = det && typeof det === "object"
            ? (T(det.key) !== det.key ? T(det.key) : det.msg) : det;
          throw new Error(msg || T("talk.request_failed", { what: T(label), status: r.status }));
        }
        return d;
      } catch (e) {
        if (e.name === "AbortError") throw new Error(T("talk.timeout", { what: T(label), n: seconds }));
        throw e;
      } finally {
        clearTimeout(t);
        if (flight === ac) flight = null;
      }
    }
    const toast = (m, ms) => {
      note.textContent = m; note.classList.add("on");
      clearTimeout(toast._t);
      toast._t = setTimeout(() => note.classList.remove("on"), ms || 2600);
    };

    // ------------------------------------------------------------ drag / resize
    if (!flat) {
      let dx = 0, dy = 0, moving = false;
      bar.addEventListener("pointerdown", (e) => {
        if (e.target.closest("button")) return;
        moving = true; bar.setPointerCapture(e.pointerId);
        const r = win.getBoundingClientRect();
        dx = e.clientX - r.left; dy = e.clientY - r.top;
      });
      bar.addEventListener("pointermove", (e) => {
        if (!moving) return;
        win.style.left = Math.min(Math.max(0, e.clientX - dx), window.innerWidth - 80) + "px";
        win.style.top = Math.min(Math.max(0, e.clientY - dy), window.innerHeight - 30) + "px";
      });
      bar.addEventListener("pointerup", () => { moving = false; });

      let rz = false, sx = 0, sy = 0, sw = 0, sh = 0;
      grab.addEventListener("pointerdown", (e) => {
        rz = true; grab.setPointerCapture(e.pointerId);
        sx = e.clientX; sy = e.clientY; sw = win.offsetWidth; sh = win.offsetHeight;
        e.preventDefault();
      });
      grab.addEventListener("pointermove", (e) => {
        if (!rz) return;
        win.style.width = Math.max(360, sw + e.clientX - sx) + "px";
        win.style.height = Math.max(260, sh + e.clientY - sy) + "px";
      });
      grab.addEventListener("pointerup", () => { rz = false; });
    }
    // one column when there is no room for two
    try {
      new ResizeObserver(() => {
        win.classList.toggle("narrow", win.clientWidth < 620);
      }).observe(win);
    } catch (e) { /* old browser: stays two-column */ }

    mini.onclick = () => {
      win.classList.toggle("min");
      mini.textContent = win.classList.contains("min") ? "▢" : "–";
    };
    let hidden = false;
    function hide() {
      hidden = true; engaged = false;
      stopRec(true); audio.pause();
      win.style.display = "none";
    }
    function show() {
      hidden = false; engaged = true;
      win.style.display = "";
    }
    // Closing the window keeps the conversation: reopening from the reader's
    // toolbar should drop you back into the same exchange, not a blank one.
    shut.onclick = hide;
    again.onclick = () => {
      audio.pause(); stopRec(true);
      if (flight) { try { flight.abort(); } catch (e) { } }
      S.busy = false;
      S.session = null; main.hidden = true; setup.hidden = false;
      now.textContent = ""; hint.textContent = "";
      goBtn.textContent = T("talk.start");
    };

    // ------------------------------------------------------------ settings
    gear.onclick = () => {
      if (sheet) { sheet.remove(); sheet = null; return; }
      sheet = el("div", "sheet");
      const h = S.health || {};
      const r = (k, v) => {
        const d = el("div", "r"); d.append(el("span", "k", k), el("span", "v", v)); return d;
      };
      sheet.append(el("h4", null, T("talk.s_components")));
      sheet.append(r(T("talk.s_stt"), h.stt && h.stt.available
        ? `${h.stt.backend} · ${h.stt.model}` : (h.stt ? h.stt.reason : "…")));
      sheet.append(r(T("talk.s_llm"), h.llm && h.llm.available ? h.llm.model : T("talk.s_not_running")));
      sheet.append(r(T("talk.s_voice"), h.voice && h.voice.available
        ? `${h.voice.engine} · ${h.voice.via === "reader" ? T("talk.s_shared") : T("talk.s_own")}` : T("talk.s_none")));
      sheet.append(r(T("talk.s_scoring"), h.voice && h.voice.gop ? "wav2vec2" : T("talk.s_unavailable")));
      sheet.append(document.createElement("hr"));
      const box = (label, key) => {
        const l = el("label"); const c = el("input"); c.type = "checkbox"; c.checked = S[key];
        c.onchange = () => { S[key] = c.checked; };
        l.append(c, document.createTextNode(label)); return l;
      };
      sheet.append(box(T("talk.s_autoplay"), "autoplay"),
        box(T("talk.s_score"), "score"),
        box(T("talk.s_coach"), "coach"),
        box(T("talk.s_interim"), "interim"));
      sheet.append(document.createElement("hr"));
      const acts = el("div", "acts");
      const un = el("button", null, T("talk.s_unload"));
      un.onclick = async () => {
        await fetch(url("/api/talk/stt/unload"), { method: "POST" });
        toast(T("talk.s_unloaded")); refreshHealth();
      };
      const rs = el("button", null, T("talk.s_recheck"));
      rs.onclick = () => { refreshHealth(); loadDocs(); toast(T("talk.s_rechecked")); };
      acts.append(un, rs);
      sheet.append(acts);
      win.appendChild(sheet);
    };
    win.addEventListener("pointerdown", (e) => {
      if (sheet && !sheet.contains(e.target) && e.target !== gear) { sheet.remove(); sheet = null; }
    }, true);

    // ------------------------------------------------------------ mode picker
    function setMode(m) {
      S.mode = m;
      [[mFree, "free"], [mTopic, "topic"], [mDoc, "doc"]].forEach(([b, k]) =>
        b.classList.toggle("on", k === m));
      fTopic.hidden = m !== "topic";
      fDoc.hidden = m !== "doc";
      if (m === "topic") topicIn.focus();
    }
    mFree.onclick = () => setMode("free");
    mTopic.onclick = () => setMode("topic");
    mDoc.onclick = () => setMode("doc");
    topicIn.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter") start();
    });

    // ------------------------------------------------------------ tutor side
    let capTimer = null;
    let showTutor = function (t, isNew) {
      // demote whatever was on stage
      if (isNew && cap.textContent.trim()) {
        const old = el("div", "line");
        old.appendChild(markWords(cap.dataset.text || cap.textContent, S.targets));
        if (cap.dataset.audio) {
          const a = cap.dataset.audio, rt = cap.dataset.rate;
          old.title = T("talk.click_replay");
          old.onclick = () => { audio.src = url(a); audio.playbackRate = +rt || 1; audio.play(); };
        }
        past.prepend(old);
      }
      cap.textContent = "";
      cap.className = "cap";
      cap.dataset.text = t.text || "";
      cap.dataset.audio = t.audio || "";
      cap.dataset.rate = t.rate || 1;
      S.capSents = (t.sents && t.sents.length ? t.sents : [t.text || ""]);
      S.capMarks = t.marks || null;
      S.capSents.forEach((s, i) => {
        const sp = el("span", "s");
        sp.appendChild(markWords(s, S.targets));
        cap.appendChild(sp);
        if (i < S.capSents.length - 1) cap.appendChild(document.createTextNode(" "));
      });
      if (!S.capMarks) cap.classList.add("idle");
      stage.scrollTop = 0;
    };

    function showThinking(on) {
      if (!on) return;
      cap.className = "cap idle";
      cap.textContent = "";
      cap.appendChild(el("div", "thinking", T("talk.thinking")));
    }

    function followCaption() {
      cancelAnimationFrame(capTimer);
      if (!S.capMarks || !S.capMarks.length) return;
      const step = () => {
        const d = audio.duration;
        if (!d || audio.paused) { return; }
        const f = audio.currentTime / d;
        const spans = cap.querySelectorAll(".s");
        let cur = -1;
        S.capMarks.forEach((m, i) => { if (f >= m[0] && f < m[1]) cur = i; });
        spans.forEach((sp, i) => {
          sp.classList.toggle("on", i === cur);
          sp.classList.toggle("done", cur >= 0 && i < cur);
        });
        capTimer = requestAnimationFrame(step);
      };
      capTimer = requestAnimationFrame(step);
    }
    audio.addEventListener("play", followCaption);
    audio.addEventListener("pause", () => {
      cancelAnimationFrame(capTimer);
      cap.querySelectorAll(".s.on").forEach((s) => s.classList.remove("on"));
    });
    audio.addEventListener("ended", () => {
      cap.querySelectorAll(".s").forEach((s) => { s.classList.remove("on"); s.classList.add("done"); });
    });
    replay.onclick = () => {
      if (!cap.dataset.audio) { toast(T("talk.no_audio")); return; }
      audio.src = url(cap.dataset.audio);
      audio.playbackRate = +cap.dataset.rate || 1;
      audio.play();
    };

    let voiceWarned = false;
    function playTurn(t) {
      if (t.voice_error && !voiceWarned) {
        voiceWarned = true;
        toast(T("talk.no_audio_why", { msg: t.voice_error }), 6000);
      }
      if (!S.autoplay || !t.audio) return;
      audio.src = url(t.audio);
      audio.playbackRate = t.rate || 1;
      audio.play().catch((err) => {
        toast(err && err.name === "NotAllowedError"
          ? T("talk.autoplay_blocked")
          : T("talk.play_failed", { msg: (err && err.name) || String(err) }), 6000);
      });
    }

    // ------------------------------------------------------------ my side
    function scoreClass(n) { return n >= 80 ? "good" : n >= 60 ? "mid" : "poor"; }

    function showSaid(t) {
      mineWrap.querySelectorAll(".said").forEach((n) => n.classList.add("old"));
      const wrap = en(el("div", "said"));
      const txt = el("div", "txt");
      txt.appendChild(markWords(t.text || "", S.targets));
      wrap.append(txt);
      const row = el("div", "row");
      if (typeof t.score === "number") row.append(el("span", "chip " + scoreClass(t.score), T("talk.chip_pron", { n: t.score })));
      if ((t.used || []).length) row.append(el("span", "chip", T("talk.chip_used", { n: t.used.length })));
      if (row.childNodes.length) wrap.append(row);
      mineWrap.insertBefore(wrap, live);
      live.textContent = ""; live.classList.remove("on");
      mineWrap.scrollTop = mineWrap.scrollHeight;
    }

    function showFix(t) {
      const card = el("div", "card");
      if (t.fixed) {
        card.append(en(el("div", "orig", t.text)));
        const nw = en(el("div", "new"));
        nw.appendChild(markStars(t.fixed));
        card.append(nw);
        if (t.why) card.append(en(el("div", "why", t.why)));    // one English sentence naming the rule
        card.append(hintControl("correction", () => ({ said: t.text, fixed: t.fixed.replace(/\*/g, ""), why: t.why || "" })));
      } else {
        card.classList.add("ok");
        card.append(el("div", "new", T("talk.fix_ok")));
      }
      if (t.problems && t.problems.length) {
        const ph = en(el("div", "phon"));
        ph.append(Object.assign(el("span", null, T("talk.phon_note")), { lang: document.documentElement.lang, dir: I.dir }));
        t.problems.forEach((o) => {
          const s = el("span", o.op === "sub" ? "sub" : o.op === "miss" ? "miss" : "extra");
          s.textContent = o.op === "sub" ? `${o.target}→${o.heard} `
            : o.op === "miss" ? `${o.target} ` : `${o.heard} `;
          ph.append(s);
        });
        card.append(ph);
        card.append(hintControl("pronunciation", () => ({
          word: t.text, ops: t.problems })));
      }
      const none = fixBody.querySelector(".fixnone");
      if (none) none.remove();
      fixBody.prepend(card);
    }

    function resetFix() {
      fixBody.textContent = "";
      fixBody.append(el("div", "fixnone", T("talk.fix_none")));
    }

    // ------------------------------------------------------------ word strip
    function renderStrip() {
      strip.textContent = "";
      if (!S.targets.length) {
        strip.append(el("span", "lab", T("talk.strip_empty")));
        return;
      }
      strip.append(el("span", "lab", T("talk.strip_label")));
      S.targets.forEach((w) => {
        const c = en(el("span", "word", w));
        const ever = S.ever[w] ? " " + T("talk.strip_ever", { n: S.ever[w] }) : "";
        if (S.said[w]) { c.classList.add("said"); c.title = T("talk.strip_said") + ever; }
        else if (S.heard[w]) { c.classList.add("heard"); c.title = T("talk.strip_heard") + ever; }
        else c.title = T("talk.strip_not_yet") + ever;
        strip.append(c);
      });
    }

    function absorb(role, used) {
      (used || []).forEach((w) => {
        if (role === "learner") S.said[w] = (S.said[w] || 0) + 1;
        else S.heard[w] = (S.heard[w] || 0) + 1;
      });
      renderStrip();
    }

    // ------------------------------------------------------------ network
    async function refreshHealth() {
      try { S.health = await (await fetch(url("/api/talk/health"))).json(); }
      catch (e) { S.health = null; }
      const h = S.health || {};
      dSt.className = "dot " + (h.stt && h.stt.available ? "on" : "off");
      dLl.className = "dot " + (h.llm && h.llm.available ? "on" : "off");
      dTt.className = "dot " + (h.voice && h.voice.available ? "on" : "off");
      if (h.score_default === false) S.score = false;
      if (h.coach_default === false) S.coach = false;
      if (h.interim_default === false) S.interim = false;
      title.textContent = h.dev ? T("talk.title") + " · dev" : T("talk.title");
      refreshMic();
    }

    async function loadDocs() {
      try { S.docs = (await (await fetch(url("/api/talk/docs"))).json()).items || []; }
      catch (e) { S.docs = []; }
      picker.textContent = "";
      if (!S.docs.length) {
        picker.append(el("option", null, T("talk.no_docs")));
        picker.disabled = true;
        mDoc.disabled = true;
        docWhy.textContent = T("talk.no_docs_why");
        return;
      }
      picker.disabled = false; mDoc.disabled = false;
      S.docs.forEach((d) => {
        const o = el("option", null, d.title || d.doc_id); o.dir = "auto";
        o.value = d.doc_id;
        picker.append(o);
      });
      syncWhy();
    }
    function syncWhy() {
      const d = S.docs.find((x) => x.doc_id === picker.value);
      docWhy.textContent = d
        ? T("talk.doc_why", { n: ((d.progress && d.progress.para) || 0) + 1 }) : "";
    }
    picker.onchange = syncWhy;

    async function loadWords() {
      try {
        const d = await (await fetch(url("/api/talk/words"))).json();
        S.targets = (d.items || []).slice(0, 12).map((x) => x.word);
        (d.items || []).forEach((x) => { if (x.spoken) S.ever[x.word] = x.spoken; });
        renderStrip();
      } catch (e) { /* strip stays empty */ }
    }

    async function start() {
      const ctx = (S.mode === "doc" && opts.getContext) ? opts.getContext() : null;
      const payload = { mode: S.mode, topic: topicIn.value.trim() };
      if (S.mode === "doc") {
        payload.doc_id = (ctx && ctx.doc_id) || picker.value;
        if (ctx) payload.para = ctx.para;
        if (!payload.doc_id) { toast(T("talk.pick_doc")); return; }
      }
      if (S.mode === "topic" && !payload.topic) { toast(T("talk.type_topic")); topicIn.focus(); return; }

      goBtn.disabled = true; goBtn.textContent = T("talk.starting");
      try {
        const d = await ask("/api/talk/session", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }, 120, "talk.what_open");
        S.session = d.session; S.topic = d.topic;
        S.doc = d.context ? d.context.doc_id : null;
        S.para = d.context ? d.context.para : null;
        S.targets = d.targets || []; S.heard = {}; S.said = {};
        now.textContent = d.context
          ? `${d.context.title} · §${d.context.from + 1}–${d.context.to + 1}`
          : (d.topic || T("talk.mode_free"));
        setup.hidden = true; main.hidden = false;
        past.textContent = ""; mineWrap.textContent = ""; mineWrap.append(live);
        resetFix(); renderStrip();
        showTutor(d.turn, false); absorb("tutor", d.turn.used);
        playTurn(d.turn);
        setHint("talk.hint_ready");
      } catch (e) {
        toast(String(e.message || e), 5000);
      }
      goBtn.disabled = false; goBtn.textContent = T("talk.start");
    }
    goBtn.onclick = () => { unlockAudio(); start(); };

    async function send(blob, typed) {
      if (S.busy || !S.session) return;
      S.busy = true; refreshMic();
      audio.pause();
      if (typed) { live.textContent = typed; live.classList.add("on"); }
      showThinking(true);

      const fd = new FormData();
      fd.append("session", S.session);
      fd.append("score", S.score ? "1" : "0");
      fd.append("coach", S.coach ? "1" : "0");
      if (blob) fd.append("file", blob, "turn.wav");
      if (typed) fd.append("text", typed);

      try {
        const d = await ask("/api/talk/turn", { method: "POST", body: fd }, 180, "talk.what_turn");
        if (d.empty) {
          live.textContent = ""; live.classList.remove("on");
          showTutor({ text: cap.dataset.text, audio: cap.dataset.audio, rate: cap.dataset.rate,
            sents: S.capSents, marks: S.capMarks }, false);
          toast((d.message_key && T(d.message_key) !== d.message_key ? T(d.message_key) : d.message) || T("talk.heard_nothing"), 3500);
          return;
        }
        showSaid(d.learner); absorb("learner", d.learner.used);
        showFix(d.learner);
        showTutor(d.turn, true); absorb("tutor", d.turn.used);
        playTurn(d.turn);
        S.targets = d.targets || S.targets;
        setHint("talk.hint_after", { secs: d.secs.toFixed(1) });
      } catch (e) {
        cap.className = "cap idle";
        cap.textContent = "";
        cap.appendChild(markWords(cap.dataset.text || "", S.targets));
        live.textContent = ""; live.classList.remove("on");
        toast(String(e.message || e), 5000);
      }
      S.busy = false; refreshMic();
    }

    function refreshMic() {
      const h = S.health || {};
      mic.disabled = !(h.stt && h.stt.available) || S.busy || !S.session;
      mic.title = mic.disabled && !(h.stt && h.stt.available)
        ? T("talk.mic_no_stt") : T("talk.mic_title");
    }

    // ------------------------------------------------------------ microphone
    const REC = { on: false, ctx: null, node: null, stream: null, chunks: [],
      sr: 16000, cap: null, tick: null, busy: false };

    function snapshot() {
      const total = REC.chunks.reduce((n, c) => n + c.length, 0);
      const all = new Float32Array(total);
      let off = 0;
      REC.chunks.forEach((c) => { all.set(c, off); off += c.length; });
      return { blob: encodeWav(all, REC.sr), samples: total };
    }

    async function pushInterim() {
      if (!REC.on || REC.busy || S.busy || !S.interim) return;
      const snap = snapshot();
      if (snap.samples < REC.sr * 0.8) return;
      REC.busy = true;
      try {
        const fd = new FormData();
        fd.append("file", snap.blob, "part.wav");
        const d = await (await fetch(url("/api/talk/interim"), { method: "POST", body: fd })).json();
        if (REC.on && d.text) { live.textContent = d.text; live.classList.add("on"); }
      } catch (e) { /* interim is a nicety; silence is fine */ }
      REC.busy = false;
    }

    async function startRec() {
      if (REC.on || S.busy) return;
      if (!S.session) { toast(T("talk.pick_start")); return; }
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        toast(T("err.mic_insecure"), 5000); return;
      }
      try {
        REC.stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      } catch (e) { toast(T("err.mic_denied"), 4000); return; }
      audio.pause();                       // talking over the tutor interrupts it
      if (opts.pauseHost) { try { opts.pauseHost(); } catch (e) { } }
      REC.ctx = new (window.AudioContext || window.webkitAudioContext)();
      REC.sr = REC.ctx.sampleRate;
      REC.chunks = [];
      const src = REC.ctx.createMediaStreamSource(REC.stream);
      REC.node = REC.ctx.createScriptProcessor(4096, 1, 1);
      REC.node.onaudioprocess = (ev) => REC.chunks.push(new Float32Array(ev.inputBuffer.getChannelData(0)));
      src.connect(REC.node);
      REC.node.connect(REC.ctx.destination);
      REC.on = true;
      mic.classList.add("live");
      live.textContent = "…"; live.classList.remove("on");
      setHint("talk.hint_listening");
      REC.tick = setInterval(pushInterim, 1600);
      // Whisper reads 30 s at a time; past that the tail would vanish silently
      REC.cap = setTimeout(() => {
        if (!REC.on) return;
        const b = stopRec();
        toast(T("talk.max_30"), 3000);
        if (b) send(b, "");
      }, 30000);
    }

    function stopRec(discard) {
      if (!REC.on) return null;
      REC.on = false;
      clearTimeout(REC.cap); clearInterval(REC.tick);
      mic.classList.remove("live");
      if (S.session) setHint("talk.hint_ready"); else hint.textContent = "";
      try { REC.node.disconnect(); } catch (e) { }
      try { REC.stream.getTracks().forEach((t) => t.stop()); } catch (e) { }
      const snap = snapshot();
      try { REC.ctx.close(); } catch (e) { }
      if (discard || snap.samples < REC.sr * 0.4) {
        live.textContent = ""; live.classList.remove("on");
        return null;
      }
      return snap.blob;
    }

    mic.onclick = () => {
      if (REC.on) {
        const b = stopRec();
        if (!b) { toast(T("talk.too_short")); return; }
        send(b, "");
      } else startRec();
    };

    say.addEventListener("keydown", (e) => {
      e.stopPropagation();
      if (e.key === "Enter" && say.value.trim()) {
        const v = say.value.trim(); say.value = "";
        send(null, v);
      }
    });

    // ------------------------------------------------------------ keys
    // Space is push-to-talk, Esc cuts the tutor off. Both only while this
    // window has the user's attention: it lives over someone else's page, and
    // stealing the space bar from the reader mid-paragraph is the wrong default.
    let held = false;
    win.addEventListener("pointerdown", () => { engaged = true; unlockAudio(); });
    document.addEventListener("pointerdown", (e) => {
      if (!flat && !holder.contains(e.target)) engaged = false;
    }, true);
    const mine = () => engaged || shadow.activeElement || win.matches(":hover");

    window.addEventListener("keydown", (e) => {
      if (hidden || !mine()) return;
      if (shadow.activeElement === say || shadow.activeElement === topicIn) return;
      if (e.code === "Escape") {
        if (!audio.paused) { audio.pause(); toast(T("talk.interrupted")); }
        else if (REC.on) { stopRec(true); toast(T("talk.cancelled")); }
        e.preventDefault(); e.stopPropagation();
        return;
      }
      if (e.code !== "Space" || e.repeat) return;
      e.preventDefault(); e.stopPropagation();
      unlockAudio();
      held = true;
      startRec();
    }, true);

    window.addEventListener("keyup", (e) => {
      if (hidden || e.code !== "Space" || !held) return;
      held = false;
      e.preventDefault(); e.stopPropagation();
      const b = stopRec();
      if (!b) { toast(T("talk.too_short_hold")); return; }
      send(b, "");
    }, true);

    // follow the reader's position, when hosted inside it
    if (opts.getContext) {
      setInterval(async () => {
        if (!S.session || S.mode !== "doc") return;
        const c = opts.getContext();
        if (!c || c.doc_id !== S.doc || c.para === S.para) return;
        S.para = c.para;
        try {
          const d = await (await fetch(url("/api/talk/anchor"), {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session: S.session, para: c.para }),
          })).json();
          if (d.ok) now.textContent = `${d.context.title} · §${d.context.from + 1}–${d.context.to + 1}`;
        } catch (e) { }
      }, 4000);
    }

    // ------------------------------------------------------------ go
    // ------------------------------------------------------------ hints
    // A "Show Arabic hint" button under a card. Nothing is requested until it is
    // pressed; the server caches the answer. Chinese when that is the target.
    function hintControl(kind, payload) {
      const wrap = el("div", "hintwrap");
      const btn = el("button", "hintbtn");
      const box = el("div", "hintbox"); box.hidden = true;
      let open = false, loaded = "";
      const label = () => { btn.textContent = open ? T("hint.hide") : T("hint.show", { lang: T(`hint.lang_${hintLang()}`) }); };
      label();
      btn.dataset.relabel = "1";
      btn.relabel = label;
      btn.onclick = async () => {
        if (open) { open = false; box.hidden = true; label(); return; }
        const lang = hintLang();
        const f = faceOf(lang);
        box.hidden = false; box.className = "hintbox"; box.lang = f.lang; box.dir = f.dir;
        if (loaded !== lang) {
          box.textContent = T("hint.loading");
          try {
            const d = await (await fetch(url("/api/talk/hint"), {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ kind, lang, ...payload() }),
            })).json();
            if (d.error_key || d.error) {
              box.className = "hintbox err"; box.lang = I.lang; box.dir = I.dir;
              box.textContent = (d.error_key && T(d.error_key) !== d.error_key) ? T(d.error_key) : d.error;
            } else { box.textContent = d.hint; loaded = lang; }
          } catch (e) {
            box.className = "hintbox err"; box.lang = I.lang; box.dir = I.dir;
            box.textContent = T("err.generic");
          }
        }
        open = true; label();
      };
      wrap.append(btn, box);
      if (opts.getSettings && opts.getSettings().arabic_hints) setTimeout(() => btn.click(), 0);
      return wrap;
    }

    function setHint(key, params) {
      // the hint strings carry <b>…</b> around key names; they are our own text
      hint.innerHTML = T(key, params);
      hint.dataset.key = key;
      hint.dataset.params = JSON.stringify(params || {});
    }

    // ------------------------------------------------------------ language
    function relabelAll() {
      applyDir();
      relabel();
      replay.textContent = "▶ " + T("talk.replay");
      mic.title = T("talk.mic_title");
      if (hint.dataset.key) setHint(hint.dataset.key, JSON.parse(hint.dataset.params || "{}"));
      renderStrip();
      refreshHealth();
      loadDocs();
      win.querySelectorAll(".hintbtn").forEach((b) => b.relabel && b.relabel());
      if (!S.session) goBtn.textContent = T("talk.start");
      if (!fixBody.querySelector(".card")) resetFix();
    }
    if (opts.i18n) window.addEventListener("lumen:langchange", relabelAll);

    // the tutor's line gets its own hint button, rebuilt for every new turn
    const origShowTutor = showTutor;
    showTutor = function (tt, isNew) {          // eslint-disable-line no-func-assign
      origShowTutor(tt, isNew);
      hintHost.textContent = "";
      if (tt && tt.text) hintHost.append(hintControl("tutor", () => ({ text: tt.text })));
    };

    (async () => {
      if (I.ready) await I.ready;
      applyDir();
      relabel();
      replay.textContent = "▶ " + T("talk.replay");
      mic.title = T("talk.mic_title");
      resetFix();
      renderStrip();
      refreshHealth();
      loadDocs();
      loadWords();
      if (opts.getContext && opts.getContext()) setMode("doc");
    })();
    setInterval(refreshHealth, 20000);

    return {
      el: holder,
      i18n: I,
      start,
      show, hide,
      toggle: () => (hidden ? show() : hide()),
      visible: () => !hidden,
      destroy: () => { stopRec(true); audio.pause(); holder.remove(); },
    };
  };
})();
