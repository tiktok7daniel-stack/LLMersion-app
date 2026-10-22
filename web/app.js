/* LumenRead — reader client.
   Audio model: one paragraph = one cached clip with sentence marks. Clips are
   decoded up front and scheduled on the Web Audio clock, so playback is gapless
   and the highlighter position is derived from ctx.currentTime rather than from
   timer guesswork.

   Every visible string comes from t() / data-i18n (js/i18n.js); layout direction
   comes from <html dir> (js/layout.js). Nothing here writes English or Arabic
   into the page directly. The text of the *document* is different: it keeps its
   own direction (p.dir) whatever the UI language is. */

const $ = (id) => document.getElementById(id);
const t = (key, params) => window.LumenI18n.t(key, params);

/** A failed API call. `key` is an i18n key when the server sent one. */
class ApiError extends Error {
  constructor(message, key) { super(message); this.key = key || ""; }
}

const api = async (url, opt) => {
  const r = await fetch(url, opt);
  if (!r.ok) {
    let key = "", msg = "";
    try {
      const d = await r.json();
      const det = d && d.detail;
      if (det && typeof det === "object") { key = det.key || ""; msg = det.msg || ""; }
      else msg = det || "";
    } catch (e) { /* not JSON */ }
    throw new ApiError(msg || `HTTP ${r.status}`, key);
  }
  return r.json();
};

/** The localised text for an error: its i18n key if it has one, else its message. */
function errText(e) {
  if (e && e.key) {
    const s = t(e.key);
    if (s !== e.key) return s;
  }
  return (e && e.message) || t("err.generic");
}

/** Text for a { error_key, error } body that came back with HTTP 200. */
function bodyError(d) {
  if (d && d.error_key) {
    const s = t(d.error_key);
    if (s !== d.error_key) return s;
  }
  return (d && d.error) || t("err.generic");
}

const post = (url, body) => api(url, {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
});

const S = {
  doc: null,
  blocks: [],         // [{bi, pi, unit0, sents:[...]}]  one audio file each
  units: [],          // [{bi, si, pi, text}]  flat sentence index, for navigation
  audio: new Map(),   // block index -> {buffer, rate, marks}
  inflight: new Map(),
  engine: "",
  voice: "",
  speed: 0.8,         // learners start slow; the server setting overrides this
  cfg: null,
  settings: { ui_lang: "system", theme: "system", show_translation: true,
    translation_target: "ar", tts_speed: 0.8, tts_voice: "", ocr_enabled: true,
    ocr_arabic: false, arabic_hints: false, mt_choice: {}, text_scale: 100 },
  mt: { backend: "", model: "" },    // for the current translation target
  compare: new Set(),
};

const P = {
  ctx: null, gain: null,
  playing: false,
  idx: 0,             // sentence (unit) currently sounding
  queueBi: 0,         // next block to schedule
  queueSi: 0,         // sentence to enter that block at
  extra: 0,           // seconds past that sentence's start, for resume
  sources: [],
  nextTime: 0,
};

const targetLang = () => (S.settings.translation_target === "zh" ? "zh" : "ar");
const uiDir = () => document.documentElement.getAttribute("dir") || "ltr";
const BACK = () => window.LumenFlash.BACK_FACE[targetLang()];

/* ---------------------------------------------------------------- utils */
let statusTimer;
/** Show an already-localised message. Use sayKey() for a key. */
function say(msg, ms = 2200) {
  const el = $("status");
  el.textContent = msg;
  el.classList.add("on");
  clearTimeout(statusTimer);
  if (ms) statusTimer = setTimeout(() => el.classList.remove("on"), ms);
}
const sayKey = (key, params, ms) => say(t(key, params), ms);

function ctx() {
  if (!P.ctx) {
    P.ctx = new (window.AudioContext || window.webkitAudioContext)();
    P.gain = P.ctx.createGain();
    P.gain.connect(P.ctx.destination);
  }
  return P.ctx;
}

/** Local, dependency-free sentinel so a localStorage failure never breaks the app. */
const mem = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : v; } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
};

/* ---------------------------------------------------------------- audio */
async function fetchClip(text, engine, voice, speed) {
  const data = await api("/api/tts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      texts: [text],
      engine: engine !== undefined ? engine : S.engine,
      voice: voice !== undefined ? voice : S.voice,
      speed: speed !== undefined ? speed : S.speed,
    }),
  });
  const item = data.items[0];
  if (!item || !item.ok) throw new Error(item ? item.error : "tts failed");
  const buf = await (await fetch(item.url)).arrayBuffer();
  // engines that cannot change rate return one render plus a playbackRate
  return { buffer: await ctx().decodeAudioData(buf), rate: item.rate || 1 };
}

async function fetchBlock(b) {
  const data = await api("/api/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      blocks: [{ text: b.text, sents: b.sents.map((x) => x.text) }],
      engine: S.engine, voice: S.voice, speed: S.speed,
    }),
  });
  const item = data.items[0];
  if (!item || !item.ok) throw new Error(item ? item.error : "tts failed");
  const raw = await (await fetch(item.url)).arrayBuffer();
  return {
    buffer: await ctx().decodeAudioData(raw),
    rate: item.rate || 1,
    marks: item.marks || [[0, 1]],
    method: item.method || "",
  };
}

function ensureAudio(bi) {
  if (bi < 0 || bi >= S.blocks.length) return Promise.resolve(null);
  if (S.audio.has(bi)) return Promise.resolve(S.audio.get(bi));
  if (S.inflight.has(bi)) return S.inflight.get(bi);
  const p = fetchBlock(S.blocks[bi])
    .then((rec) => {
      S.audio.set(bi, rec);
      S.inflight.delete(bi);
      return rec;
    })
    .catch((e) => {
      S.inflight.delete(bi);
      say(t("err.tts_failed", { msg: errText(e) }), 4000);
      return null;
    });
  S.inflight.set(bi, p);
  return p;
}

function prefetch(from, n = 3) {
  for (let bi = from; bi < Math.min(from + n, S.blocks.length); bi++) ensureAudio(bi);
}

function stopAll() {
  P.sources.forEach((s) => {
    s.node.onended = null;
    try { s.node.stop(); } catch (e) { /* already stopped */ }
  });
  P.sources = [];
}

let pumping = false;
async function pump() {
  if (pumping) return;
  pumping = true;
  try {
    while (P.playing && P.sources.length < 2 && P.queueBi < S.blocks.length) {
      const bi = P.queueBi;
      const a = await ensureAudio(bi);
      if (!P.playing) break;
      if (!a) { P.queueBi++; P.queueSi = 0; P.extra = 0; continue; }

      const si = Math.min(P.queueSi, a.marks.length - 1);
      const total = a.buffer.duration;
      const offset = Math.min(total - 0.01, a.marks[si][0] * total + P.extra);
      P.queueSi = 0;
      P.extra = 0;

      const when = Math.max(ctx().currentTime + 0.04, P.nextTime);
      const node = ctx().createBufferSource();
      node.buffer = a.buffer;
      node.playbackRate.value = a.rate;
      node.connect(P.gain);
      node.start(when, offset);

      const rec = { bi, node, start: when, offset, total,
                    rate: a.rate, marks: a.marks,
                    dur: (total - offset) / a.rate };
      node.onended = () => {
        P.sources = P.sources.filter((s) => s !== rec);
        if (P.playing) {
          if (P.queueBi >= S.blocks.length && P.sources.length === 0) setPlaying(false);
          else pump();
        }
      };
      P.sources.push(rec);
      P.nextTime = when + rec.dur;
      P.queueBi = bi + 1;
      prefetch(P.queueBi, 3);
    }
  } finally {
    pumping = false;
  }
}

function startAt(unitIdx) {
  if (!S.units.length) return;
  unitIdx = Math.max(0, Math.min(unitIdx, S.units.length - 1));
  const u = S.units[unitIdx];
  stopAll();
  P.idx = unitIdx;
  P.queueBi = u.bi;
  P.queueSi = u.si;
  P.extra = 0;
  P.nextTime = 0;
  P.playing = true;
  ctx().resume();
  setPlaying(true);
  pump();
  scrollToUnit(unitIdx);
}

function resume() {
  if (!S.units.length) return;
  P.nextTime = 0;
  P.playing = true;
  ctx().resume();
  setPlaying(true);
  pump();
}

function setPlaying(on) {
  P.playing = on;
  setPlayIcon(on);
  if (!on) stopAll();
}

const ICON_PLAY = "M8 5v14l11-7z";
const ICON_PAUSE = "M7 5h4v14H7zM13 5h4v14h-4z";
function setPlayIcon(on) {
  $("playIcon").firstElementChild.setAttribute("d", on ? ICON_PAUSE : ICON_PLAY);
  $("play").setAttribute("aria-pressed", String(on));
}

function pause() {
  const rec = activeSource();
  if (rec) {
    const at = bufferTime(rec);
    const si = sentenceAt(rec, at / rec.total);
    P.queueBi = rec.bi;
    P.queueSi = si;
    P.extra = Math.max(0, at - rec.marks[si][0] * rec.total);
    P.idx = S.blocks[rec.bi].unit0 + si;
  }
  setPlaying(false);
  saveProgress(true);
}

function toggle() {
  if (P.playing) pause();
  else resume();
}

function activeSource() {
  const now = ctx().currentTime;
  return P.sources.find((s) => now >= s.start && now < s.start + s.dur) || null;
}

/** Position inside the decoded buffer, in buffer seconds. */
function bufferTime(rec) {
  return rec.offset + (ctx().currentTime - rec.start) * rec.rate;
}

function sentenceAt(rec, frac) {
  for (let i = 0; i < rec.marks.length; i++) {
    if (frac < rec.marks[i][1]) return i;
  }
  return rec.marks.length - 1;
}

function duck(on) {
  if (!P.gain) return;
  P.gain.gain.setTargetAtTime(on ? 0.14 : 1.0, ctx().currentTime, 0.06);
}


/* ---------------------------------------------------------------- render */
function unitEl(i) { return document.querySelector(`.sent[data-i="${i}"]`); }

function scrollToUnit(i) {
  const el = unitEl(i);
  if (!el) return;
  const r = el.getBoundingClientRect();
  if (r.top < 90 || r.bottom > window.innerHeight - 140) {
    el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
}

/** Language of a paragraph's own text: what the font, the voice and the
 *  direction should follow — not the UI language. */
const paraLang = (p) => (p.kind === "ar" ? "ar" : p.kind === "cjk" ? "zh" : "en");

function pageBreak(page) {
  const el = document.createElement("div");
  el.className = "pagebreak";
  el.dataset.page = page;
  const label = document.createElement("span");
  label.setAttribute("data-i18n", "reader.page_n");
  label.setAttribute("data-i18n-params", JSON.stringify({ n: page + 1 }));
  el.appendChild(label);
  window.LumenI18n.apply(el);
  return el;
}

function simplifyButton(text, el) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "icon simplify";
  btn.setAttribute("data-i18n-attr", "title:reader.simplify;aria-label:reader.simplify");
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true"><path fill="currentColor" d="M4 6h16v2H4zM4 11h10v2H4zM4 16h16v2H4z"/></svg>';
  btn.onclick = () => simplifyPara(el, text, btn);
  window.LumenI18n.apply(btn);
  return btn;
}

function render(doc) {
  S.doc = doc;
  S.units = [];
  S.blocks = [];
  S.audio.clear();
  S.inflight.clear();
  painted = -1;

  const arabicDoc = (doc.meta && doc.meta.lang) === "ar";
  const root = document.createElement("div");
  root.className = "doc";
  let lastPage = -1;

  doc.paragraphs.forEach((p) => {
    if (p.page !== lastPage) { lastPage = p.page; root.appendChild(pageBreak(p.page)); }
    const el = document.createElement("article");
    el.className = "para " + p.kind;
    el.dataset.pi = p.id;
    el.dataset.page = p.page;
    el.dir = p.dir || "ltr";            // the document's direction, not the UI's

    const en = document.createElement("p");
    en.className = "en";
    en.lang = paraLang(p);
    if (p.kind === "other" || p.kind === "toc" || p.kind === "cjk" || p.kind === "ar") {
      en.textContent = p.text;
    } else {
      const sents = p.sents && p.sents.length
        ? p.sents : [{ start: 0, end: p.text.length, text: p.text }];
      const bi = S.blocks.length;
      S.blocks.push({ bi, pi: p.id, text: p.text, sents, unit0: S.units.length });
      sents.forEach((s, si) => {
        const idx = S.units.length;
        S.units.push({ bi, si, pi: p.id, text: s.text });
        const span = document.createElement("span");
        span.className = "sent";
        span.dataset.i = idx;
        span.textContent = s.text + " ";
        en.appendChild(span);
      });
    }
    el.appendChild(en);

    if (p.kind === "body") el.appendChild(simplifyButton(p.text, el));
    if ((p.kind === "body" || p.kind === "heading") && !arabicDoc) {
      const tr = document.createElement("p");
      tr.className = "tr pending";
      tr.dataset.pi = p.id;
      tr.textContent = "…";
      applyTrFace(tr);
      el.appendChild(tr);
    }
    root.appendChild(el);
  });

  const reader = $("reader");
  reader.innerHTML = "";
  reader.appendChild(root);
  const title = $("docTitle");
  title.textContent = doc.title;
  title.hidden = false;
  document.title = `${doc.title} · LumenRead`;
  $("transport").hidden = false;
  updateCounter();
  const pj = $("pageJump");
  pj.max = String(doc.pages || 1);
  $("pageTotal").textContent = String(doc.pages || 1);

  observeParas();

  const pr = doc.progress || { para: 0, sent: 0 };
  const start = S.units.findIndex((u) => u.pi === pr.para && u.si === pr.sent);
  P.idx = start > 0 ? start : 0;
  P.queueBi = S.units[P.idx] ? S.units[P.idx].bi : 0;
  P.queueSi = S.units[P.idx] ? S.units[P.idx].si : 0;
  P.extra = 0;
  if (P.idx > 0) { scrollToUnit(P.idx); sayKey("reader.resumed"); }
  prefetch(P.queueBi, 2);
}

function updateCounter() {
  $("counter").textContent = `${S.units.length ? P.idx + 1 : 0} / ${S.units.length}`;
}

/** Current page (1-based) of the sentence being read. */
function currentPage() {
  const u = S.units[P.idx];
  const p = u && S.doc ? S.doc.paragraphs[u.pi] : null;
  return p ? p.page + 1 : 1;
}

/** Jump to the first sentence on or after page `n` (1-based). Keeps playing if it was. */
function jumpToPage(n) {
  if (!S.doc || !S.units.length) return;
  const last = S.doc.pages || 1;
  n = Math.max(1, Math.min(last, Math.round(Number(n) || 1)));
  let idx = S.units.findIndex((u) => S.doc.paragraphs[u.pi].page + 1 >= n);
  if (idx < 0) idx = S.units.length - 1;
  if (P.playing) startAt(idx);
  else {
    const u = S.units[idx];
    P.idx = idx; P.queueBi = u.bi; P.queueSi = u.si; P.extra = 0;
    scrollToUnit(idx);
    paint(idx, -1);
    scheduleTr(0);
    saveProgress(true);
  }
  $("pageJump").value = String(n);
}

/* ---------------------------------------------------------------- translation
   Translation is the slowest thing in the app, so what gets translated matters
   more than how fast one call is. Priority, best first:

     1. the paragraph being read aloud, and the next few after it
     2. paragraphs currently on screen, nearest the reading position first

   A paragraph that scrolls away before its turn simply loses its place in the
   queue instead of holding one; scroll past forty paragraphs and none of them
   are translated, which is the point.

   The translation is a learning aid and is independent of the UI language: an
   Arabic translation appears under English paragraphs in the English UI too. */

const TR = {
  state: new Map(),     // pi -> "busy" | "done"
  visible: new Set(),
  active: 0,
  timer: null,
  io: null,
  warned: false,
  epoch: 0,             // bumped when the target/model changes; stale replies are dropped
};

const TR_AHEAD = 4;     // paragraphs to translate ahead of the voice
const TR_BATCH = 3;
const TR_CONCURRENT = 2;

/** Language and direction of the translation text under a paragraph. */
function applyTrFace(el) {
  el.lang = BACK().lang;
  el.dir = BACK().dir;
}

function trWanted(pi) {
  const p = S.doc && S.doc.paragraphs[pi];
  if (!p) return false;
  if (p.kind !== "body" && p.kind !== "heading") return false;   // contents, formulas, Arabic/CJK
  return !TR.state.has(pi);
}

function trTargets() {
  const here = S.units[P.idx] ? S.units[P.idx].pi : -1;
  const scored = new Map();
  if (here >= 0) {
    for (let k = 0; k <= TR_AHEAD; k++) {
      if (trWanted(here + k)) scored.set(here + k, k);
    }
  }
  TR.visible.forEach((pi) => {
    if (!trWanted(pi)) return;
    const d = here >= 0 ? Math.abs(pi - here) : pi;
    const score = 100 + d;                       // always after the reading head
    if (!scored.has(pi) || scored.get(pi) > score) scored.set(pi, score);
  });
  return [...scored.entries()].sort((a, b) => a[1] - b[1]).map((e) => e[0]);
}

function scheduleTr(delay = 60) {
  clearTimeout(TR.timer);
  TR.timer = setTimeout(runTr, delay);
}

async function runTr() {
  if (!S.doc || TR.active >= TR_CONCURRENT || !S.settings.show_translation) return;
  if (!S.mt.model) {
    if (!TR.warned) { TR.warned = true; sayKey("tr.no_backend", null, 7000); }
    return;
  }
  const batch = trTargets().slice(0, TR_BATCH);
  if (!batch.length) return;
  const epoch = TR.epoch;
  batch.forEach((pi) => TR.state.set(pi, "busy"));
  TR.active++;
  if (TR.active < TR_CONCURRENT) scheduleTr(20);   // keep the pipe full

  const texts = batch.map((pi) => S.doc.paragraphs[pi].text);
  try {
    const res = await post("/api/translate", {
      texts, backend: S.mt.backend, model: S.mt.model, target: targetLang(),
    });
    if (epoch !== TR.epoch) { TR.active--; return; }
    if (res.error && !TR.warned) { TR.warned = true; say(bodyError(res), 6000); }
    batch.forEach((pi, k) => {
      const tr = res.items[k] || "";
      TR.state.set(pi, "done");
      const el = document.querySelector(`.tr[data-pi="${pi}"]`);
      if (!el) return;
      applyTrFace(el);
      el.textContent = tr;
      el.classList.remove("pending");
    });
  } catch (e) {
    if (epoch === TR.epoch) {
      batch.forEach((pi) => {
        TR.state.delete(pi);                        // let it be retried later
        const el = document.querySelector(`.tr[data-pi="${pi}"]`);
        if (el) el.classList.add("pending");
      });
    }
  }
  TR.active--;
  if (epoch === TR.epoch) scheduleTr(40);
}

/** Throw away every rendered translation and start again (target or model changed). */
function resetTranslations() {
  TR.epoch++;
  TR.active = 0;
  TR.warned = false;
  TR.state.clear();
  document.querySelectorAll(".tr").forEach((el) => {
    applyTrFace(el);
    el.textContent = "…";
    el.classList.add("pending");
  });
  scheduleTr(0);
}

function observeParas() {
  if (TR.io) TR.io.disconnect();
  TR.state.clear();
  TR.visible.clear();
  TR.io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      const pi = Number(e.target.dataset.pi);
      if (e.isIntersecting) TR.visible.add(pi);
      else TR.visible.delete(pi);
    });
    scheduleTr(120);
  }, { rootMargin: "300px 0px" });
  document.querySelectorAll(".para").forEach((el) => TR.io.observe(el));
  scheduleTr(120);
}

/** Pick the (backend, model) for the current translation target. */
function syncMt() {
  const target = targetLang();
  const chosen = (S.settings.mt_choice || {})[target];
  const defs = (S.cfg && S.cfg.mt && S.cfg.mt.defaults) || {};
  const d = defs[target] || {};
  S.mt = chosen && chosen.model ? { backend: chosen.backend, model: chosen.model }
    : { backend: d.backend || "", model: d.model || "" };
  if (S.mt.backend === "none") S.mt = { backend: "", model: "" };
}

function applyShowTranslation() {
  const on = !!S.settings.show_translation;
  document.body.classList.toggle("hide-tr", !on);
  $("zhToggle").setAttribute("aria-pressed", String(on));
  if (on) scheduleTr(0);
}

function applyTargetLabels() {
  const key = `header.translation_${targetLang()}`;
  $("trLabel").setAttribute("data-i18n", key);
  $("trLabel").textContent = t(key);
}

/* ---------------------------------------------------------------- lookup */
let popWord = "";

function hidePop() { $("pop").hidden = true; }

const WORD_CHAR = /[A-Za-z0-9'’\-]/;
const LETTER = /[A-Za-z]/;

/** Grow a partial selection out to whole words, so dragging over "un" in "run"
 *  looks up "run". Only grows when an end actually sits *inside* a word — a
 *  selection that already stopped at a space keeps its boundary instead of
 *  swallowing the next word. Punctuation is trimmed off both ends afterwards,
 *  so "steps." and "(CAT)" arrive as "steps" and "CAT". */
function snapToWords(sel) {
  if (!sel.rangeCount) return;
  const r = sel.getRangeAt(0);
  const sn = r.startContainer, en = r.endContainer;
  if (sn.nodeType !== Node.TEXT_NODE || en.nodeType !== Node.TEXT_NODE) return;
  let so = r.startOffset, eo = r.endOffset;
  const st = sn.textContent, et = en.textContent;

  if (so < st.length && WORD_CHAR.test(st[so])) {
    while (so > 0 && WORD_CHAR.test(st[so - 1])) so--;
  }
  if (eo > 0 && WORD_CHAR.test(et[eo - 1])) {
    while (eo < et.length && WORD_CHAR.test(et[eo])) eo++;
  }
  while (so < st.length && !LETTER.test(st[so])) so++;
  while (eo > 0 && !LETTER.test(et[eo - 1])) eo--;
  if (sn === en && eo <= so) return;

  try {
    const grown = document.createRange();
    grown.setStart(sn, so);
    grown.setEnd(en, eo);
    sel.removeAllRanges();
    sel.addRange(grown);
  } catch (e) { /* the selection moved under us; keep what we had */ }
}

function setPopGloss(text) {
  const el = $("popGloss");
  el.lang = BACK().lang;
  el.dir = BACK().dir;
  el.textContent = text;
}

function setPopSave(state) {
  const btn = $("popSave");
  btn.dataset.state = state;
  btn.setAttribute("data-i18n", state === "removed" ? "pop.removed" : "pop.saved_remove");
  btn.textContent = t(btn.getAttribute("data-i18n"));
}

async function lookupSelection() {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount || !sel.toString().trim()) return;
  if (!sel.anchorNode || !$("reader").contains(sel.anchorNode)) return;
  snapToWords(sel);
  const raw = sel.toString().trim();
  if (!raw || raw.length > 60 || !/^[A-Za-z][A-Za-z'’\-\s]*$/.test(raw)) return;
  const words = raw.split(/\s+/);
  if (words.length > 4) return;

  const rect = sel.getRangeAt(0).getBoundingClientRect();
  const pop = $("pop");
  pop.hidden = false;
  const w = pop.offsetWidth || 350;
  const left = Math.max(8, Math.min(window.scrollX + rect.left, window.scrollX + window.innerWidth - w - 8));
  pop.style.left = left + "px";
  pop.style.top = window.scrollY + rect.bottom + 8 + "px";
  $("popWord").textContent = raw;
  $("popPhon").textContent = "";
  setPopGloss(t("pop.looking_up"));
  $("popDef").textContent = "";
  $("popSrc").textContent = "";
  popWord = raw;

  speakWord(raw);
  const target = targetLang();
  try {
    const d = await api(`/api/lookup?q=${encodeURIComponent(raw)}&target=${target}`);
    if (popWord !== raw) return;
    $("popWord").textContent = d.word + (d.lemma_of ? ` ← ${raw}` : "");
    $("popPhon").textContent = d.phonetic ? `/${d.phonetic}/` : "";
    setPopGloss(d.gloss || t("pop.not_found"));
    $("popDef").textContent = d.definition || "";
    $("popSrc").textContent = d.source;
    popWord = d.word;                     // remember the base form, not the inflection
    setPopSave("saved");
    // every lookup lands in the list, dated; repeats just bump the counter
    await post("/api/vocab", {
      word: d.word,
      zh: d.zh || (target === "zh" ? d.gloss : "") || "",
      ar: target === "ar" ? d.gloss || "" : "",
      phonetic: d.phonetic || "",
      context: S.units[P.idx] ? S.units[P.idx].text : "",
      doc_id: S.doc ? S.doc.doc_id : "",
    });
    loadVocab();
  } catch (e) {
    setPopGloss(t("pop.failed"));
  }
}

let wordAudio = null;
async function speakWord(text) {
  try {
    duck(true);
    const { buffer, rate } = await fetchClip(text);
    const node = ctx().createBufferSource();
    node.buffer = buffer;
    node.playbackRate.value = rate;
    node.connect(ctx().destination);
    node.onended = () => duck(false);
    if (wordAudio) { try { wordAudio.stop(); } catch (e) {} }
    wordAudio = node;
    node.start();
  } catch (e) {
    duck(false);
  }
}

/* ---------------------------------------------------------------- voices & settings */
const SPEED_STEPS = [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.2, 1.3, 1.4, 1.5];
const nearestSpeed = (v) => SPEED_STEPS.reduce((a, b) => (Math.abs(b - v) < Math.abs(a - v) ? b : a));

function readingVoices() {
  return ((S.cfg && S.cfg.tts.voices) || []).filter((v) => (v.lang || "en") === "en");
}

function applyConfig(cfg) {
  S.cfg = cfg;
  if (cfg.settings) S.settings = { ...S.settings, ...cfg.settings };
  const wantVoice = S.settings.tts_voice;
  if (!S.engine) {
    const hit = wantVoice && readingVoices().find((v) => v.key === wantVoice);
    const d = hit ? { engine: hit.engine, id: hit.id } : cfg.tts.default;
    if (d) { S.engine = d.engine; S.voice = d.id; }
  }
  S.speed = nearestSpeed(Number(S.settings.tts_speed) || 0.8);
  $("speed").value = String(S.speed);
  if (cfg.unit) $("unit").value = cfg.unit;
  syncMt();
  updateVoicePill();
}

function updateVoicePill() {
  const cur = readingVoices().find((v) => v.engine === S.engine && v.id === S.voice);
  $("voiceNow").textContent = cur ? cur.label : t("voice.none");
}

/* A reply to an older save must not undo a newer local change, so each key
   remembers the last save that touched it and only that save's reply may update it. */
const settingsRev = {};
let settingsSeq = 0;

/** Persist settings (merge) and return them. S.settings changes synchronously. */
async function saveSettings(patch) {
  const seq = ++settingsSeq;
  Object.keys(patch).forEach((k) => { settingsRev[k] = seq; });
  S.settings = { ...S.settings, ...patch };
  try {
    const stored = await post("/api/settings", patch);
    // take the server's normalised value (clamped speed, …) for keys no newer save has touched
    Object.keys(patch).forEach((k) => {
      if (settingsRev[k] === seq && k in stored) S.settings[k] = stored[k];
    });
  } catch (e) { /* keep the local copy; the next save retries */ }
  return S.settings;
}

function setVoice(v) {
  S.engine = v.engine;
  S.voice = v.id;
  updateVoicePill();
  resetAudio();
  saveSettings({ tts_voice: v.key });
}

function engineTags(e) {
  const tags = [];
  if (e.cloning) tags.push(`<span class="eng-tag clone">${t("voice.tag_clone")}</span>`);
  tags.push(`<span class="eng-tag">${t(e.network ? "voice.tag_online" : "voice.tag_local")}</span>`);
  if (!e.speed) tags.push(`<span class="eng-tag">${t("voice.tag_client_speed")}</span>`);
  if (e.loaded) tags.push(`<span class="eng-tag">${t("voice.tag_loaded")}</span>`);
  return tags.join("");
}

function renderVoicePanel() {
  const cfg = S.cfg;
  if (!cfg) return;
  const list = $("engineList");
  list.innerHTML = "";
  const usable = cfg.tts.engines.filter((e) => e.available).length;
  $("voiceStat").textContent = t("voice.stat", { n: usable, total: cfg.tts.engines.length });

  cfg.tts.engines.forEach((e) => {
    const box = document.createElement("div");
    box.className = "eng" + (e.available ? "" : " off");
    const head = document.createElement("div");
    head.className = "eng-head";
    const name = document.createElement("span");
    name.className = "eng-name";
    name.textContent = e.label;
    name.dir = "ltr";
    const why = document.createElement("span");
    why.className = "eng-why";
    why.dir = "ltr";
    why.textContent = e.available ? e.id : `${e.reason} — ${e.notes}`;
    head.appendChild(name);
    head.insertAdjacentHTML("beforeend", engineTags(e));
    head.appendChild(why);
    box.appendChild(head);

    if (e.available) {
      const grid = document.createElement("div");
      grid.className = "voice-grid";
      cfg.tts.voices.filter((v) => v.engine === e.id).forEach((v) => {
        const row = document.createElement("label");
        const sel = v.engine === S.engine && v.id === S.voice;
        const reading = (v.lang || "en") === "en";
        row.className = "vopt" + (sel ? " sel" : "");
        row.dir = "ltr";
        row.innerHTML = `
          <input type="checkbox" ${S.compare.has(v.key) ? "checked" : ""} ${reading ? "" : "disabled"}
            title="${t("voice.add_compare")}" aria-label="${t("voice.add_compare")}">
          <span class="vlab"></span>
          <span class="vacc"></span>
          <button class="icon" type="button" ${reading ? "" : "disabled"}
            title="${t("voice.use")}" aria-label="${t("voice.use")}">◉</button>`;
        row.querySelector(".vlab").textContent = v.label;
        row.querySelector(".vacc").textContent = reading ? (v.accent || v.kind) : t("voice.arabic_only");
        row.querySelector("input").onchange = (ev) => {
          if (ev.target.checked) S.compare.add(v.key);
          else S.compare.delete(v.key);
          $("abStat").textContent = t("voice.selected", { n: S.compare.size });
        };
        row.querySelector("button").onclick = (ev) => {
          ev.preventDefault();
          setVoice(v);
          renderVoicePanel();
        };
        grid.appendChild(row);
      });
      box.appendChild(grid);
    }
    list.appendChild(box);
  });
}

function resetAudio() {
  S.audio.clear();
  S.inflight.clear();
  const was = P.playing;
  setPlaying(false);
  P.firstOffset = 0;
  if (was) startAt(P.idx);
}

async function openVoicePanel() {
  $("voicePanel").hidden = false;
  try {
    if (!S.cfg) applyConfig(await api("/api/config"));
    $("abText").value = $("abText").value ||
      (S.units[P.idx] ? S.units[P.idx].text : "The quick brown fox jumps over the lazy dog.");
    renderVoicePanel();
  } catch (err) {
    $("engineList").textContent = t("voice.config_failed", { msg: errText(err) });
    console.error("renderVoicePanel failed", err);
  }
}

async function comparePlay() {
  const keys = [...S.compare];
  if (!keys.length) { sayKey("voice.pick_some"); return; }
  const text = $("abText").value.trim();
  if (!text) return;
  const wasPlaying = P.playing;
  if (wasPlaying) pause();

  for (const key of keys) {
    const [engine, voice] = key.split("|");
    const v = S.cfg.tts.voices.find((x) => x.key === key);
    $("abStat").textContent = t("voice.playing", { name: v ? v.label : key });
    try {
      const { buffer, rate } = await fetchClip(text, engine, voice, S.speed);
      await new Promise((done) => {
        const node = ctx().createBufferSource();
        node.buffer = buffer;
        node.playbackRate.value = rate;
        node.connect(ctx().destination);
        node.onended = () => setTimeout(done, 350);
        node.start();
      });
    } catch (e) {
      $("abStat").textContent = t("voice.play_failed", { name: key, msg: errText(e) });
      await new Promise((r) => setTimeout(r, 1200));
    }
  }
  $("abStat").textContent = t("voice.played", { n: keys.length });
}

/* ---------------------------------------------------------------- hints
   Every card is in English by default. A "Show Arabic hint" button asks the local
   tutor model for a short explanation in Arabic (or Chinese when that is the
   translation target) — only when pressed, and cached by the server. */
const hintLangName = () => t(`hint.lang_${targetLang()}`);

function relabelHintButton(btn) {
  const open = btn.dataset.open === "1";
  btn.textContent = open ? t("hint.hide") : t("hint.show", { lang: hintLangName() });
}

function setupHintButton(btn, box, makePayload) {
  btn.dataset.hint = "1";
  btn.dataset.open = "0";
  btn.dataset.loaded = "";
  relabelHintButton(btn);
  btn.onclick = async () => {
    if (btn.dataset.open === "1") {
      btn.dataset.open = "0"; box.hidden = true; relabelHintButton(btn); return;
    }
    const lang = targetLang();
    box.hidden = false; box.classList.remove("error");
    box.lang = BACK().lang; box.dir = BACK().dir;
    if (btn.dataset.loaded !== lang) {
      box.textContent = t("hint.loading");
      btn.disabled = true;
      try {
        const d = await post("/api/hint", { ...makePayload(), lang });
        if (d.error_key || d.error) {
          box.classList.add("error"); box.lang = document.documentElement.lang; box.dir = uiDir();
          box.textContent = bodyError(d);
        } else { box.textContent = d.hint; btn.dataset.loaded = lang; }
      } catch (e) {
        box.classList.add("error"); box.lang = document.documentElement.lang; box.dir = uiDir();
        box.textContent = errText(e);
      }
      btn.disabled = false;
    }
    btn.dataset.open = "1";
    relabelHintButton(btn);
  };
  return btn;
}

function relabelAllHints() {
  document.querySelectorAll("[data-hint]").forEach(relabelHintButton);
}

/* ---------------------------------------------------------------- vocabulary */
const V = { items: [], flash: null };

async function loadVocab() {
  const r = await api("/api/vocab");
  V.items = r.items || [];
  $("vocabCount").textContent = V.items.length;
  return V.items;
}

function dayKey(ts) {
  const d = new Date((ts || 0) * 1000);
  // Latin digits in both languages: numerals stay consistent with the English text being studied
  const loc = document.documentElement.lang === "ar" ? "ar-u-nu-latn" : "en-GB";
  return d.toLocaleDateString(loc, { year: "numeric", month: "2-digit", day: "2-digit" });
}

const glossOf = (it) => (targetLang() === "ar" ? it.ar : it.zh) || "";

/** Save-time glosses only exist for the language that was active then; fill in
 *  the other one on demand so the list and the flashcards are never blank. */
let glossBusy = false;
async function ensureGlosses(items) {
  if (glossBusy) return;
  glossBusy = true;
  const lang = targetLang();
  try {
    for (const it of items.filter((x) => !glossOf(x)).slice(0, 40)) {
      if (lang !== targetLang()) break;
      const d = await post("/api/vocab/gloss", { word: it.word, lang });
      if (d.gloss) {
        it[lang === "ar" ? "ar" : "zh"] = d.gloss;
        if (!it.phonetic && d.phonetic) it.phonetic = d.phonetic;
        document.querySelectorAll(`.vrow[data-word="${CSS.escape(it.word)}"] .vgloss`).forEach((el) => {
          el.textContent = d.gloss.replace(/\n/g, " / ");
        });
      }
    }
  } catch (e) { /* the list works without glosses */ }
  glossBusy = false;
}

function renderVocab() {
  const list = $("vocabList");
  list.innerHTML = "";
  const known = V.items.filter((x) => x.known).length;
  $("vocabStat").textContent = t("vocab.stat", { n: V.items.length, known });

  const days = new Map();
  V.items.forEach((it) => {
    const k = dayKey(it.ts);
    if (!days.has(k)) days.set(k, []);
    days.get(k).push(it);
  });

  if (!days.size) {
    const p = document.createElement("p");
    p.className = "vocab-empty";
    p.textContent = t("vocab.empty");
    list.appendChild(p);
    return;
  }

  days.forEach((items, date) => {
    const sec = document.createElement("section");
    sec.className = "vocab-day";
    const h = document.createElement("div");
    h.className = "vocab-date";
    h.textContent = `${date} · ${items.length}`;
    sec.appendChild(h);

    items.forEach((it) => {
      const row = document.createElement("div");
      row.className = "vrow" + (it.known ? " known" : "");
      row.dataset.word = it.word;
      row.innerHTML = `
        <div class="vword" dir="ltr" lang="en"><span class="w"></span><span class="ph"></span><span class="hits"></span><span class="best"></span></div>
        <div class="vgloss"></div>
        <div class="vact">
          <button class="icon" type="button" data-act="say" title="${t("vocab.say")}" aria-label="${t("vocab.say")}">▶</button>
          <button class="icon" type="button" data-act="known" title="${t(it.known ? "vocab.unknown" : "vocab.known")}" aria-label="${t(it.known ? "vocab.unknown" : "vocab.known")}">${it.known ? "↺" : "✓"}</button>
          <button class="icon" type="button" data-act="del" title="${t("vocab.delete")}" aria-label="${t("vocab.delete")}">✕</button>
        </div>`;
      const w = row.querySelector(".vword");
      w.querySelector(".w").textContent = it.word;
      if (it.phonetic) w.querySelector(".ph").textContent = `/${it.phonetic}/`;
      if ((it.hits || 1) > 1) w.querySelector(".hits").textContent = `×${it.hits}`;
      if (it.best) w.querySelector(".best").textContent = it.best;
      const g = row.querySelector(".vgloss");
      g.lang = BACK().lang;
      g.dir = BACK().dir;
      g.textContent = glossOf(it).replace(/\n/g, " / ");
      row.querySelector(".vact").onclick = async (e) => {
        const act = e.target.dataset.act;
        if (!act) return;
        if (act === "say") speakWord(it.word);
        if (act === "known") {
          await post("/api/vocab/known", { word: it.word, known: it.known ? 0 : 1 });
          await loadVocab(); renderVocab();
        }
        if (act === "del") {
          await fetch("/api/vocab/" + encodeURIComponent(it.word), { method: "DELETE" });
          await loadVocab(); renderVocab();
        }
      };
      sec.appendChild(row);
    });
    list.appendChild(sec);
  });
  ensureGlosses(V.items);
}

async function openVocab() {
  // show the panel before rendering into it: a render error used to leave the
  // button looking dead, with the exception swallowed by the async call
  $("vocabPanel").hidden = false;
  $("vocabStat").textContent = "";
  $("vocabList").innerHTML = `<p class="vocab-empty">${t("common.loading")}</p>`;
  try {
    await loadVocab();
    renderVocab();
  } catch (err) {
    $("vocabList").textContent = t("vocab.open_failed", { msg: errText(err) });
    console.error("renderVocab failed", err);
  }
}

async function mergeVocab() {
  sayKey("vocab.merging", null, 0);
  const r = await api("/api/vocab/merge", { method: "POST" });
  await loadVocab();
  renderVocab();
  sayKey("vocab.merged", { groups: r.groups, removed: r.removed, total: r.total }, 3500);
}

/* ---------------------------------------------------------------- flashcards
   English on the front (always LTR); the gloss on the back (RTL for Arabic) is
   optional — the learner can switch it off and flip to just the example
   sentence. Cards come due-first; grading a card schedules its next review. */
const SHOW_GLOSS_KEY = "lumen.flashGloss";

function flashPool() {
  const only = $("onlyUnknown").checked;
  return window.LumenFlash.sortDue(V.items.filter((x) => (only ? !x.known : true)));
}

function renderFlashKeys() {
  const L = window.LumenLayout;
  const dir = uiDir();
  const arrow = (k) => (k === "ArrowLeft" ? "←" : "→");
  const keys = [
    ["↑", "flash.k_listen"], ["↓", "flash.k_flip"],
    ["R", REC.on ? "flash.k_stop" : "flash.k_record"],
    [arrow(L.prevKey(dir)), "flash.k_prev"], [arrow(L.nextKey(dir)), "flash.k_next"],
    ["1–4", "flash.k_grade"], ["Enter", "flash.k_known"], ["Space", "flash.k_delete"], ["Esc", "flash.k_exit"],
  ];
  const box = $("flashKeys");
  box.innerHTML = "";
  keys.forEach(([k, label]) => {
    const s = document.createElement("span");
    const kbd = document.createElement("kbd");
    kbd.dir = "ltr";
    kbd.textContent = k;
    s.append(kbd, " ", t(label));
    box.appendChild(s);
  });
}

function ensureGradeButtons() {
  if ($("grades")) return;
  const row = document.createElement("div");
  row.id = "grades";
  row.className = "grades";
  [["flash.again", 0], ["flash.hard", 1], ["flash.good", 2], ["flash.easy", 3]].forEach(([key, g]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ghost";
    b.dataset.grade = g;
    b.setAttribute("data-i18n", key);
    b.textContent = t(key);
    b.onclick = () => flashGrade(g);
    row.appendChild(b);
  });
  $("flashBack").appendChild(row);
}

function openFlash() {
  const pool = flashPool();
  if (!pool.length) { sayKey("flash.empty"); return; }
  ensureGradeButtons();
  V.flash = { list: pool, i: 0, back: false };
  $("flash").hidden = false;
  renderFlashKeys();
  paintFlash();
}

function closeFlash() {
  V.flash = null;
  $("flash").hidden = true;
  loadVocab().then(() => { if (!$("vocabPanel").hidden) renderVocab(); });
}

async function paintFlash() {
  const f = V.flash;
  if (!f) return;
  const it = f.list[f.i];
  const showGloss = mem.get(SHOW_GLOSS_KEY, "1") === "1";
  const m = window.LumenFlash.cardModel(it, { target: targetLang(), uiDir: uiDir(), showBack: f.back });

  const word = $("flashWord");
  word.textContent = m.front.text; word.dir = m.front.dir; word.lang = m.front.lang;
  $("flashPhon").textContent = m.front.ipa;
  const badges = [it.known ? t("flash.known") : "", it.best ? t("flash.best", { n: it.best }) : ""]
    .filter(Boolean).join(" · ");
  $("flashCount").textContent = `${f.i + 1} / ${f.list.length}${badges ? " · " + badges : ""}`;
  $("flashRail").style.width = ((f.i + 1) / f.list.length) * 100 + "%";

  $("flashScore").hidden = true;
  if (REC.on) stopRec();

  $("flashBack").hidden = !f.back;
  if (!f.back) return;
  const g = $("flashGlossEl");
  g.hidden = !showGloss;
  g.lang = m.back.lang; g.dir = m.back.dir;
  g.classList.remove("empty-gloss");
  const ctxEl = $("flashCtx");
  ctxEl.hidden = !m.context.text;
  ctxEl.textContent = m.context.text;
  if (!showGloss) return;
  if (m.back.text) { g.textContent = m.back.text; return; }
  g.textContent = t("pop.looking_up");
  try {
    const d = await post("/api/vocab/gloss", { word: it.word, lang: targetLang() });
    it[targetLang() === "ar" ? "ar" : "zh"] = d.gloss;
    it.phonetic = it.phonetic || d.phonetic;
    if (V.flash && V.flash.list[V.flash.i] === it && V.flash.back) {
      g.textContent = d.gloss || t("pop.not_found");
      if (!d.gloss) g.classList.add("empty-gloss");
      $("flashPhon").textContent = it.phonetic ? `/${it.phonetic}/` : "";
    }
  } catch (e) {
    g.textContent = t("pop.failed");
    g.classList.add("empty-gloss");
  }
}

function flashStep(d) {
  const f = V.flash;
  if (!f) return;                       // closed while a request was in flight
  f.i = (f.i + d + f.list.length) % f.list.length;
  f.back = false;
  paintFlash();
}

function flashFlip() {
  const f = V.flash;
  if (!f) return;
  f.back = !f.back;
  paintFlash();
}

async function flashGrade(grade) {
  const f = V.flash;
  if (!f || !f.back) { sayKey("flash.flip_first"); return; }
  const it = f.list[f.i];
  await post("/api/vocab/review", { word: it.word, grade });
  flashStep(1);
}

async function flashKnown() {
  if (!V.flash) return;
  const it = V.flash.list[V.flash.i];
  it.known = 1;
  await post("/api/vocab/known", { word: it.word, known: 1 });
  flashStep(1);
}

/* ------------------------------------------------------------ recording
   MediaRecorder hands back webm/opus, which the server would need ffmpeg to
   open. Capturing raw samples and writing the WAV header here keeps the server
   dependency-free — soundfile reads it directly. */
const REC = { stream: null, ctx: null, node: null, chunks: [], sr: 48000, on: false };

function encodeWav(samples, sr) {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buf);
  const str = (off, s) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)); };
  str(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); str(8, "WAVE");
  str(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true);
  view.setUint16(22, 1, true); view.setUint32(24, sr, true);
  view.setUint32(28, sr * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  str(36, "data"); view.setUint32(40, samples.length * 2, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return new Blob([buf], { type: "audio/wav" });
}

async function startRec() {
  if (REC.on) return;
  // getUserMedia only exists in a secure context: https, or a localhost origin.
  // Over plain http to a remote box the API is simply absent.
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    sayKey("err.mic_insecure", null, 7000);
    return;
  }
  try {
    REC.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (e) {
    sayKey("err.mic_denied", null, 4000);
    return;
  }
  REC.ctx = new (window.AudioContext || window.webkitAudioContext)();
  REC.sr = REC.ctx.sampleRate;
  REC.chunks = [];
  const src = REC.ctx.createMediaStreamSource(REC.stream);
  REC.node = REC.ctx.createScriptProcessor(4096, 1, 1);
  REC.node.onaudioprocess = (ev) => {
    REC.chunks.push(new Float32Array(ev.inputBuffer.getChannelData(0)));
  };
  src.connect(REC.node);
  REC.node.connect(REC.ctx.destination);
  REC.on = true;
  document.body.classList.add("recording");
  renderFlashKeys();
}

function stopRec() {
  if (!REC.on) return null;
  REC.on = false;
  document.body.classList.remove("recording");
  renderFlashKeys();
  try { REC.node.disconnect(); } catch (e) {}
  REC.stream.getTracks().forEach((tr) => tr.stop());
  const total = REC.chunks.reduce((n, c) => n + c.length, 0);
  const all = new Float32Array(total);
  let off = 0;
  REC.chunks.forEach((c) => { all.set(c, off); off += c.length; });
  const sr = REC.sr;
  REC.ctx.close();
  if (total < sr * 0.15) return null;
  return encodeWav(all, sr);
}

async function scoreRecording() {
  const blob = stopRec();
  const it = V.flash ? V.flash.list[V.flash.i] : null;
  if (!blob || !it) { sayKey("score.too_short", null, 3000); return; }

  const box = $("flashScore");
  box.hidden = false;
  $("scoreNum").textContent = "…";
  $("scoreNum").className = "score-num";
  $("scoreNote").textContent = t("score.scoring");
  $("scorePhon").innerHTML = "";
  $("scoreHintBtn").hidden = true;
  $("scoreHint").hidden = true;

  const fd = new FormData();
  fd.append("file", blob, "rec.wav");
  fd.append("word", it.word);
  fd.append("engine", S.engine);
  fd.append("voice", S.voice);
  try {
    const r = await fetch("/api/pronounce", { method: "POST", body: fd });
    const d = await r.json();
    if (!r.ok || !d.ok) {
      $("scoreNum").textContent = "–";
      const det = d.detail && typeof d.detail === "object" ? d.detail : null;
      $("scoreNote").textContent = det ? errText({ key: det.key, message: det.msg }) : bodyError(d);
      return;
    }
    it.best = Math.max(it.best || 0, d.score);
    $("scoreNum").textContent = d.score;
    $("scoreNum").className = "score-num " + (d.score >= 85 ? "good" : d.score >= 60 ? "mid" : "poor");
    // the summary is English-first: how many sounds, and the sounds themselves
    $("scoreNote").textContent = d.problems.length
      ? t("score.n_off", { n: d.problems.length }) : t("score.all_ok");
    $("scorePhon").innerHTML = d.ops.map((o) => {
      if (o.op === "ok") return `<span class="ph ok">${o.target}</span>`;
      if (o.op === "sub") return `<span class="ph sub">${o.target}<small>→${o.heard}</small></span>`;
      if (o.op === "miss") return `<span class="ph miss">${o.target}</span>`;
      return `<span class="ph extra">${o.heard}</span>`;
    }).join("");
    if (d.problems.length) {
      const btn = $("scoreHintBtn");
      btn.hidden = false;
      setupHintButton(btn, $("scoreHint"), () => ({ kind: "pronunciation", word: it.word, ops: d.problems }));
      if (S.settings.arabic_hints) btn.click();
    }
  } catch (e) {
    $("scoreNum").textContent = "–";
    $("scoreNote").textContent = t("score.failed", { msg: errText(e) });
  }
}

async function flashDelete() {
  const f = V.flash;
  if (!f) return;
  const it = f.list[f.i];
  await fetch("/api/vocab/" + encodeURIComponent(it.word), { method: "DELETE" });
  f.list.splice(f.i, 1);
  V.items = V.items.filter((x) => x.word !== it.word);
  $("vocabCount").textContent = V.items.length;
  sayKey("flash.deleted", { word: it.word }, 1800);
  if (!f.list.length) { closeFlash(); return; }
  if (f.i >= f.list.length) f.i = 0;
  f.back = false;
  paintFlash();
}

function flashKey(e) {
  const f = V.flash;
  if (!f) return false;
  const L = window.LumenLayout;
  const dir = uiDir();
  if (e.key === L.nextKey(dir)) { flashStep(1); e.preventDefault(); return true; }
  if (e.key === L.prevKey(dir)) { flashStep(-1); e.preventDefault(); return true; }
  switch (e.key) {
    case "ArrowUp":
      speakWord(f.list[f.i].word);
      $("flash").classList.remove("spoke");
      void $("flash").offsetWidth;
      $("flash").classList.add("spoke");
      break;
    case "ArrowDown": flashFlip(); break;
    case "1": case "2": case "3": case "4": flashGrade(Number(e.key) - 1); break;
    case " ": flashDelete(); break;
    case "r": case "R":
      if (REC.on) scoreRecording();
      else startRec();
      break;
    case "Enter": flashKnown(); break;
    case "Escape": closeFlash(); break;
    default: return false;
  }
  e.preventDefault();
  return true;
}

/* ---------------------------------------------------------------- loop */
function frame() {
  requestAnimationFrame(frame);
  if (!S.units.length) return;
  const rec = activeSource();
  if (rec) {
    const frac = bufferTime(rec) / rec.total;
    const si = sentenceAt(rec, frac);
    const idx = S.blocks[rec.bi].unit0 + si;
    if (idx !== P.idx) {
      const paraChanged = !S.units[P.idx] || S.units[P.idx].pi !== S.units[idx].pi;
      P.idx = idx;
      scrollToUnit(idx);
      saveProgress();
      if (paraChanged) scheduleTr(0);
    }
    const [m0, m1] = rec.marks[si];
    paint(idx, Math.max(0, Math.min(1, (frac - m0) / Math.max(1e-6, m1 - m0))));
  } else {
    paint(P.idx, P.playing ? 0 : -1);
  }
  const f = S.units.length > 1 ? P.idx / (S.units.length - 1) : 0;
  // inset-inline-start follows the UI direction: the track fills from the right in Arabic
  $("trackFill").style.inlineSize = f * 100 + "%";
  $("trackKnob").style.insetInlineStart = f * 100 + "%";
  updateCounter();
  const pj = $("pageJump");
  if (document.activeElement !== pj) pj.value = String(currentPage());
}

let lastSaved = 0;
function saveProgress(force = false) {
  const u = S.units[P.idx];
  if (!u || !S.doc) return;
  const now = Date.now();
  if (!force && now - lastSaved < 3000) return;
  lastSaved = now;
  const body = JSON.stringify({ doc_id: S.doc.doc_id, para: u.pi, sent: u.si });
  // on the way out fetch() gets cancelled with the page; sendBeacon survives it
  if (force && navigator.sendBeacon) {
    navigator.sendBeacon("/api/progress", new Blob([body], { type: "application/json" }));
    return;
  }
  fetch("/api/progress", { method: "POST", headers: { "Content-Type": "application/json" }, body })
    .catch(() => {});
}

let painted = -1;
function paint(i, tt) {
  if (painted !== i) {
    document.querySelectorAll(".sent.speaking").forEach((el) => {
      el.classList.remove("speaking");
      el.classList.add("done");
    });
    const el = unitEl(i);
    if (el) {
      el.classList.add("speaking");
      el.classList.remove("done");
      document.querySelectorAll(".para.active").forEach((p) => p.classList.remove("active"));
      el.closest(".para").classList.add("active");
    }
    painted = i;
  }
  const el = unitEl(i);
  if (el && tt >= 0) el.style.setProperty("--fill", tt);
}

/* ---------------------------------------------------------------- nav */
function stepSent(d) { startAt(P.idx + d); }

function stepPara(d) {
  const cur = S.units[P.idx];
  if (!cur) return;
  // already partway into a block: "previous" means the top of this one
  const atTop = cur.si === 0;
  const bi = Math.max(0, Math.min(S.blocks.length - 1, cur.bi + (d < 0 && !atTop ? 0 : d)));
  startAt(S.blocks[bi].unit0);
}

/* ---------------------------------------------------------------- opening documents */
/** Windows reports an empty MIME type when no app is registered for .pdf,
 *  so trust the extension too — and never fail silently. */
function acceptFile(file) {
  if (!file) { sayKey("open.no_file", null, 4000); return; }
  const exts = (S.cfg && S.cfg.formats) || [".pdf", ".txt", ".md", ".html", ".epub"];
  const name = file.name || "";
  const ok = exts.some((e) => name.toLowerCase().endsWith(e)) || file.type === "application/pdf";
  if (!ok) {
    sayKey("open.unsupported", { name: name || "?", formats: exts.join(" ") }, 5000);
    return;
  }
  openFile(file);
}

function showOcr(done, total) {
  const box = $("ocrBox");
  box.hidden = false;
  $("ocrText").textContent = total
    ? t("ocr.progress", { done: Math.min(done + 1, total), total }) : t("ocr.starting");
  $("ocrFill").style.inlineSize = total ? Math.round((done / total) * 100) + "%" : "4%";
}

async function pollJob(job) {
  showOcr(job.done, job.total);
  for (;;) {
    await new Promise((r) => setTimeout(r, 700));
    const j = await api(`/api/job/${job.id}`);
    showOcr(j.done, j.total);
    if (j.state === "done") return j;
    if (j.state === "error") {
      throw new ApiError((j.error && j.error.msg) || "", j.error && j.error.key);
    }
  }
}

async function openFile(file) {
  const isPdf = /\.pdf$/i.test(file.name || "");
  say(t(isPdf ? "open.parsing_pdf" : "open.parsing"), 0);
  const fd = new FormData();
  fd.append("file", file);
  try {
    let doc = await api("/api/open", { method: "POST", body: fd });
    if (doc.job) {
      // a scanned PDF: Tesseract reads it page by page in the background
      say(t("ocr.scanned_found"), 0);
      const j = await pollJob(doc.job);
      doc = await api(`/api/doc/${j.result.doc_id}`);
    }
    $("ocrBox").hidden = true;
    render(doc);
    sayKey("open.done", { pages: doc.pages, paras: doc.paragraphs.length, sents: S.units.length });
    const ocr = doc.meta && doc.meta.ocr;
    if (ocr && ocr.used && ocr.note === "ara_missing") sayKey("ocr.ara_missing", null, 8000);
    else if (ocr && ocr.skipped && ocr.skipped.length) sayKey("ocr.skipped_pages", { n: ocr.skipped.length }, 7000);
    else if (doc.meta && doc.meta.lang === "ar") sayKey("reader.arabic_doc", null, 7000);
  } catch (e) {
    $("ocrBox").hidden = true;
    say(t("open.failed", { msg: errText(e) }), 7000);
  }
}

/* ---------------------------------------------------------------- language, theme, scale */
async function setUiLang(pref) {
  await window.LumenI18n.setPreference(pref);
  mem.set("lumen.langpref", pref);
  $("langSwitch").value = pref;
  saveSettings({ ui_lang: pref });
}

function applyTheme(pref) {
  const theme = window.LumenLayout.applyTheme(pref);
  window.LumenLayout.remember(null, pref, window);
  return theme;
}

function applyTextScale() {
  const pct = Math.max(80, Math.min(150, Number(S.settings.text_scale) || 100));
  document.documentElement.style.setProperty("--text-scale", String(pct / 100));
}

/** Everything built from JS (not data-i18n markup) is re-rendered here. */
function onLangChange() {
  const pref = window.LumenI18n.pref;
  $("langSwitch").value = pref;
  applyTargetLabels();
  updateVoicePill();
  setPopSave($("popSave").dataset.state || "saved");
  relabelAllHints();
  if (S.doc) document.title = `${S.doc.title} · LumenRead`;
  if (!$("voicePanel").hidden) renderVoicePanel();
  if (!$("vocabPanel").hidden) renderVocab();
  if (V.flash) { renderFlashKeys(); paintFlash(); }
  document.body.setAttribute("data-drop", t("open.drop"));
}

/* ---------------------------------------------------------------- boot */
async function boot() {
  const L = window.LumenI18n;
  try { await L.setPreference(mem.get("lumen.langpref", "system")); }
  catch (e) { console.error("i18n failed", e); }
  window.addEventListener("lumen:langchange", onLangChange);
  $("langSwitch").value = L.pref;
  $("langSwitch").onchange = (e) => setUiLang(e.target.value);
  document.body.setAttribute("data-drop", t("open.drop"));

  try {
    applyConfig(await api("/api/config"));
    // the server copy of the settings is the source of truth for the language
    if (S.settings.ui_lang && S.settings.ui_lang !== L.pref) {
      await L.setPreference(S.settings.ui_lang);
      mem.set("lumen.langpref", S.settings.ui_lang);
    }
    applyTheme(S.settings.theme || "system");
    applyTextScale();
    applyTargetLabels();
    applyShowTranslation();
    if (!S.cfg.tts.default) sayKey("boot.no_engine", null, 9000);
    else if (!S.mt.model) sayKey("boot.no_translation", null, 6000);
  } catch (e) {
    sayKey("err.backend_down", null, 6000);
  }

  $("fileInput").addEventListener("change", (e) => {
    if (e.target.files[0]) acceptFile(e.target.files[0]);
    e.target.value = "";                  // allow re-opening the same file
  });
  const openPicker = () => $("fileInput").click();
  $("empty").addEventListener("click", openPicker);
  $("empty").addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openPicker(); }
  });

  let dragDepth = 0;
  document.addEventListener("dragenter", (e) => {
    e.preventDefault();
    dragDepth++;
    document.body.classList.add("dragging");
  });
  document.addEventListener("dragover", (e) => e.preventDefault());
  document.addEventListener("dragleave", () => {
    if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("dragging"); }
  });
  document.addEventListener("drop", (e) => {
    e.preventDefault();
    dragDepth = 0;
    document.body.classList.remove("dragging");
    const dt = e.dataTransfer;
    if (!dt || !dt.files || !dt.files.length) { sayKey("open.no_drop", null, 5000); return; }
    acceptFile(dt.files[0]);
  });

  $("play").onclick = toggle;
  $("prevSent").onclick = () => stepSent(-1);
  $("nextSent").onclick = () => stepSent(1);
  $("prevPara").onclick = () => stepPara(-1);
  $("nextPara").onclick = () => stepPara(1);

  const seek = (e) => {
    const f = window.LumenLayout.trackFraction(e.clientX, $("track").getBoundingClientRect(), uiDir());
    startAt(Math.round(f * (S.units.length - 1)));
  };
  $("track").addEventListener("pointerdown", (e) => {
    seek(e);
    const move = (ev) => seek(ev);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });

  const pj = $("pageJump");
  pj.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") { jumpToPage(pj.value); pj.blur(); }
  });
  pj.addEventListener("change", () => jumpToPage(pj.value));

  // a double-click is the natural "look this word up" gesture, but its first
  // click would otherwise start playback — hold the play action briefly and
  // cancel it if a second click arrives
  let clickTimer = null;
  $("reader").addEventListener("click", (e) => {
    const s = e.target.closest(".sent");
    if (!s || window.getSelection().toString().trim() !== "") return;
    clearTimeout(clickTimer);
    const i = Number(s.dataset.i);
    clickTimer = setTimeout(() => startAt(i), 220);
  });
  $("reader").addEventListener("dblclick", () => {
    clearTimeout(clickTimer);
    setTimeout(lookupSelection, 10);
  });
  $("reader").addEventListener("mouseup", (e) => {
    if (e.detail > 1) return;                     // the dblclick handler has it
    setTimeout(lookupSelection, 10);
  });
  document.addEventListener("mousedown", (e) => {
    if (!e.target.closest("#pop")) hidePop();
  });

  $("popPlay").onclick = () => speakWord(popWord);
  $("popSave").onclick = async () => {
    await fetch("/api/vocab/" + encodeURIComponent(popWord), { method: "DELETE" });
    setPopSave("removed");
    loadVocab();
  };

  $("voiceBtn").onclick = openVoicePanel;
  $("closeVoice").onclick = () => { $("voicePanel").hidden = true; };
  $("abPlay").onclick = comparePlay;
  $("rescanBtn").onclick = async () => {
    applyConfig(await post("/api/rescan"));
    renderVoicePanel();
    sayKey("voice.rescanned");
  };
  $("unloadBtn").onclick = async () => {
    await fetch("/api/tts/unload", { method: "POST" });
    applyConfig(await api("/api/config"));
    renderVoicePanel();
    sayKey("voice.unloaded");
  };

  $("vocabBtn").onclick = openVocab;
  $("closeVocab").onclick = () => { $("vocabPanel").hidden = true; };
  $("mergeBtn").onclick = mergeVocab;
  $("flashBtn").onclick = openFlash;
  $("flashClose").onclick = closeFlash;
  $("flashWord").addEventListener("click", flashFlip);
  $("flashGloss").checked = mem.get(SHOW_GLOSS_KEY, "1") === "1";
  $("flashGloss").onchange = (e) => {
    mem.set(SHOW_GLOSS_KEY, e.target.checked ? "1" : "0");
    if (V.flash) paintFlash();
  };
  loadVocab();

  $("zhToggle").onclick = () => {
    saveSettings({ show_translation: !S.settings.show_translation });   // S.settings updates synchronously
    applyShowTranslation();
  };
  $("themeToggle").onclick = async () => {
    const cur = document.documentElement.getAttribute("data-theme");
    const next = cur === "light" ? "dark" : cur === "dark" ? "black" : "light";
    applyTheme(next);
    saveSettings({ theme: next });
    if (window.LumenSettings) window.LumenSettings.refresh();
  };

  $("speed").onchange = (e) => {
    S.speed = parseFloat(e.target.value);
    saveSettings({ tts_speed: S.speed });
    resetAudio();
    if (window.LumenSettings) window.LumenSettings.refresh();
  };
  $("unit").onchange = (e) => {
    post("/api/unit", { unit: e.target.value })
      .then(() => { resetAudio(); sayKey(e.target.value === "paragraph" ? "header.unit_paragraph_note" : "header.unit_sentence_note"); });
  };

  document.addEventListener("keydown", (e) => {
    if (flashKey(e)) return;
    if (!$("writePanel").hidden) {
      // Escape must work even while typing in the textarea
      if (e.key === "Escape") $("writePanel").hidden = true;
      if (e.target.tagName !== "TEXTAREA" || e.key === "Escape") return;
    }
    if (e.target.tagName === "SELECT" || e.target.tagName === "INPUT" ||
        e.target.tagName === "TEXTAREA" || e.target.isContentEditable) return;
    for (const id of ["voicePanel", "settingsPanel", "aboutPanel"]) {
      if (!$(id).hidden) {
        if (e.key === "Escape") $(id).hidden = true;
        return;
      }
    }
    if (!$("vocabPanel").hidden) {
      if (e.key === "Escape") $("vocabPanel").hidden = true;
      if (e.key === "Enter") openFlash();
      return;
    }
    // The reader's arrows follow the *document* (English runs left to right
    // whatever the UI language), so they are not mirrored; the buttons are.
    const k = e.key.toLowerCase();
    if (e.code === "Space") { e.preventDefault(); toggle(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); stepSent(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); stepSent(-1); }
    else if (k === "k") stepPara(-1);
    else if (k === "j") stepPara(1);
    else if (k === "g") { e.preventDefault(); $("pageJump").focus(); $("pageJump").select(); }
    else if (k === "t") $("zhToggle").click();
    else if (e.key === "Escape") hidePop();
  });

  // the reading position is worth more than the 3-second throttle saves
  window.addEventListener("pagehide", () => saveProgress(true));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") saveProgress(true);
  });

  // a swallowed exception used to look like a dead button
  window.addEventListener("error", (e) => {
    say(t("err.unexpected", { msg: e.message || "unknown" }), 6000);
  });
  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    say(t("err.unexpected", { msg: (r && r.message) || String(r || "unknown") }), 6000);
  });

  requestAnimationFrame(frame);
  window.addEventListener("lumen:pause", () => { if (P.playing) pause(); });

  const splash = $("splash");
  splash.classList.add("done");
  setTimeout(() => splash.remove(), 400);
  document.dispatchEvent(new CustomEvent("lumen:ready"));
}

window.LumenApp = {
  S, P, V, t, api, post, say, sayKey, errText, bodyError, saveSettings, setUiLang, applyTheme,
  applyTextScale, applyConfig, applyShowTranslation, applyTargetLabels, syncMt, resetTranslations,
  setVoice, readingVoices, resetAudio, mem, targetLang, setupHintButton, relabelAllHints,
};

boot();


/* ---------- LLM learning features: writing practice & simplify ---------- */
function mdLite(text) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
}

async function simplifyPara(el, text, btn) {
  const old = el.querySelector(".simplified");
  if (old) { old.remove(); btn.classList.remove("on"); return; }
  btn.disabled = true;
  try {
    const d = await post("/api/simplify", { text });
    const box = document.createElement("p");
    box.className = "simplified en";
    box.lang = "en";
    box.textContent = d.error || d.error_key ? "⚠ " + bodyError(d) : d.text;
    el.appendChild(box);
    btn.classList.add("on");
  } catch (e) {
    say(t("simplify.failed", { msg: errText(e) }), 5000);
  } finally { btn.disabled = false; }
}

(function initWriting() {
  const panel = $("writePanel");
  if (!panel) return;
  let lastFeedback = "";
  $("writeBtn").onclick = () => { panel.hidden = !panel.hidden; if (!panel.hidden) $("writeText").focus(); };
  $("writeClose").onclick = () => { panel.hidden = true; };
  $("writeGo").onclick = async () => {
    const text = $("writeText").value.trim();
    const st = $("writeStatus"), out = $("writeOut");
    st.textContent = t("write.checking"); out.hidden = true;
    $("writeHintRow").hidden = true; $("writeHint").hidden = true;
    $("writeGo").disabled = true;
    try {
      const d = await post("/api/writing", { text });
      if (d.error || d.error_key) { st.textContent = "⚠ " + bodyError(d); return; }
      lastFeedback = d.feedback;
      out.innerHTML = mdLite(d.feedback);       // feedback is English, shown left-to-right
      out.hidden = false; st.textContent = "";
      $("writeHintRow").hidden = false;
      const btn = setupHintButton($("writeHintBtn"), $("writeHint"),
        () => ({ kind: "writing", feedback: lastFeedback }));
      if (S.settings.arabic_hints) btn.click();
    } catch (e) { st.textContent = t("write.failed", { msg: errText(e) }); }
    finally { $("writeGo").disabled = false; }
  };
})();
