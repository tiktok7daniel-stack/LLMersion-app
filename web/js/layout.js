/* LumenRead — layout controller.
 *
 * The one place that decides document direction. It owns:
 *   <html dir lang>      follows the UI language (rtl + ar, or ltr + en)
 *   <html data-theme>    light | dark, from the preference and the OS
 *
 * Everything else is CSS logical properties, so nothing else has to know which
 * way the page runs. Content direction is *not* decided here: a paragraph keeps
 * the direction of its own language (English stays LTR inside the Arabic UI),
 * which `contentDir()` and the `dir` attribute on each paragraph take care of.
 *
 * Loaded synchronously in <head> so the saved language is applied before first
 * paint; there is no flash of a left-to-right page for an Arabic reader.
 * Works in the browser and under Node (the unit tests drive it with a stub
 * document).
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LumenLayout = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const RTL = new Set(["ar", "he", "fa", "ur"]);
  const KEY_LANG = "lumen.lang";        // the *resolved* language, for first paint
  const KEY_THEME = "lumen.theme";      // system | light | dark

  /** "ar-EG" -> "ar" */
  function base(code) { return String(code || "").toLowerCase().split(/[-_]/)[0]; }

  function dirFor(lang) { return RTL.has(base(lang)) ? "rtl" : "ltr"; }

  /** Direction for a piece of *content* by its language; unknown stays LTR. */
  function contentDir(lang) { return dirFor(lang); }

  /** Pick en or ar from a preference and the browser's language list.
   *  `pref` is system | en | ar. Anything that is neither en nor ar -> en. */
  function resolveLang(pref, navigatorLanguages) {
    if (pref === "en" || pref === "ar") return pref;
    const list = Array.isArray(navigatorLanguages) ? navigatorLanguages : [navigatorLanguages];
    for (const l of list) {
      const b = base(l);
      if (b === "ar") return "ar";
      if (b === "en") return "en";
    }
    return "en";
  }

  /** Set <html dir lang>. Returns {lang, dir}. */
  function applyLanguage(lang, doc) {
    doc = doc || document;
    const dir = dirFor(lang);
    const el = doc.documentElement;
    el.setAttribute("lang", lang);
    el.setAttribute("dir", dir);
    el.setAttribute("data-lang", lang);
    return { lang, dir };
  }

  function resolveTheme(pref, prefersDark) {
    if (pref === "light" || pref === "dark" || pref === "black") return pref;
    return prefersDark ? "dark" : "light";
  }

  function applyTheme(pref, doc, win) {
    doc = doc || document;
    win = win || (typeof window !== "undefined" ? window : null);
    const dark = !!(win && win.matchMedia && win.matchMedia("(prefers-color-scheme: dark)").matches);
    const theme = resolveTheme(pref, dark);
    doc.documentElement.setAttribute("data-theme", theme);
    doc.documentElement.setAttribute("data-theme-pref", pref || "system");
    return theme;
  }

  /** Wrap text that must stay left-to-right inside RTL text (numbers, code,
   *  English quotations). Uses <bdi> so it also isolates from the surroundings. */
  function ltr(text) {
    const esc = String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<bdi dir="ltr">${esc}</bdi>`;
  }

  function store(win) {
    try { return (win || window).localStorage; } catch (e) { return null; }
  }

  /** First-paint: apply whatever was saved, before the page renders. */
  function applyEarly(doc, win) {
    doc = doc || document;
    win = win || window;
    const s = store(win);
    let lang = null, theme = "system";
    try { lang = s && s.getItem(KEY_LANG); theme = (s && s.getItem(KEY_THEME)) || "system"; } catch (e) { /* private mode */ }
    if (lang !== "en" && lang !== "ar") {
      lang = resolveLang("system", win.navigator ? (win.navigator.languages || [win.navigator.language]) : []);
    }
    applyLanguage(lang, doc);
    applyTheme(theme, doc, win);
    return lang;
  }

  function remember(lang, theme, win) {
    const s = store(win);
    try {
      if (lang) s && s.setItem(KEY_LANG, lang);
      if (theme) s && s.setItem(KEY_THEME, theme);
    } catch (e) { /* private mode: the server-side setting still holds */ }
  }

  /** Which arrow key means "next" in the current UI direction. */
  function nextKey(dir) { return dir === "rtl" ? "ArrowLeft" : "ArrowRight"; }
  function prevKey(dir) { return dir === "rtl" ? "ArrowRight" : "ArrowLeft"; }

  /** Fraction (0..1) along a track for a pointer at clientX, direction-aware. */
  function trackFraction(clientX, rect, dir) {
    const f = (clientX - rect.left) / Math.max(1, rect.width);
    const v = dir === "rtl" ? 1 - f : f;
    return Math.max(0, Math.min(1, v));
  }

  const api = { RTL, KEY_LANG, KEY_THEME, dirFor, contentDir, resolveLang, applyLanguage,
    resolveTheme, applyTheme, applyEarly, remember, ltr, nextKey, prevKey, trackFraction };

  if (typeof document !== "undefined" && typeof window !== "undefined") {
    try { applyEarly(document, window); } catch (e) { /* never block the page */ }
  }
  return api;
});
