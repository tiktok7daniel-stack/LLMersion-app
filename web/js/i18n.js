/* LumenRead — i18n helper.
 *
 *   t("reader.page_n", { n: 3 })   -> "Page 3" / "صفحة 3"
 *   await LumenI18n.setPreference("ar")
 *   window.addEventListener("lumen:langchange", (e) => rerender(e.detail.lang))
 *
 * Strings live in /i18n/<lang>.json (flat, dotted keys). The UI never contains
 * literal text: static markup carries data-i18n attributes, dynamic code calls
 * t(). `apply(root)` re-labels everything under `root`; a language change
 * re-labels the document and then fires `lumen:langchange` so views that build
 * their own DOM can re-render.
 *
 * Attributes understood by apply():
 *   data-i18n="empty.title"              -> textContent
 *   data-i18n-attr="title:header.speed;aria-label:header.theme;placeholder:write.placeholder"
 *   data-i18n-params='{"n":3}'           -> parameters for the above (optional)
 *
 * Plurals: t("settings.cleared_tr", {n}) looks for settings.cleared_tr_<category>
 * (zero, one, two, few, many, other — whatever Intl.PluralRules gives for the
 * language), then settings.cleared_tr_other, then settings.cleared_tr.
 *
 * If a key is missing in the active language the English string is used, and
 * failing that the key itself, so a gap is visible rather than blank.
 */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else { root.LumenI18n = api; root.t = api.t; }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  const SUPPORTED = ["en", "ar"];
  const PREFS = ["system", "en", "ar"];
  const state = { pref: "system", lang: "en", dict: {}, fallback: {}, loaded: {} };

  const layout = () => root.LumenLayout || (typeof require === "function" ? require("./layout.js") : null);

  /** Replace {name} placeholders. Missing params are left visible. */
  function format(str, params) {
    if (!params) return str;
    return str.replace(/\{(\w+)\}/g, (m, k) => (k in params ? String(params[k]) : m));
  }

  function pluralCategory(lang, n) {
    try { return new Intl.PluralRules(lang).select(Number(n)); } catch (e) { return "other"; }
  }

  function lookup(dict, key, params, lang) {
    if (params && typeof params.n === "number") {
      const cat = pluralCategory(lang, params.n);
      if (dict[`${key}_${cat}`] != null) return dict[`${key}_${cat}`];
      if (dict[`${key}_other`] != null) return dict[`${key}_other`];
    }
    return dict[key];
  }

  function t(key, params) {
    let s = lookup(state.dict, key, params, state.lang);
    if (s == null) s = lookup(state.fallback, key, params, "en");
    if (s == null) return key;
    return format(s, params);
  }

  async function fetchDict(lang) {
    if (state.loaded[lang]) return state.loaded[lang];
    const res = await root.fetch(`/i18n/${lang}.json`, { cache: "no-cache" });
    if (!res.ok) throw new Error(`i18n/${lang}.json: ${res.status}`);
    state.loaded[lang] = await res.json();
    return state.loaded[lang];
  }

  /** Re-label every [data-i18n*] element under `node`. */
  function apply(node) {
    node = node || root.document;
    if (!node || !node.querySelectorAll) return;
    node.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"), params(el));
    });
    node.querySelectorAll("[data-i18n-attr]").forEach((el) => {
      const p = params(el);
      el.getAttribute("data-i18n-attr").split(";").forEach((pair) => {
        const i = pair.indexOf(":");
        if (i < 1) return;
        el.setAttribute(pair.slice(0, i).trim(), t(pair.slice(i + 1).trim(), p));
      });
    });
  }

  function params(el) {
    const raw = el.getAttribute("data-i18n-params");
    if (!raw) return undefined;
    try { return JSON.parse(raw); } catch (e) { return undefined; }
  }

  /** Switch language. `pref` is system | en | ar. */
  async function setPreference(pref, opts) {
    opts = opts || {};
    if (!PREFS.includes(pref)) pref = "system";
    const L = layout();
    const nav = root.navigator ? (root.navigator.languages || [root.navigator.language]) : [];
    const lang = L.resolveLang(pref, nav);
    const [dict, fallback] = await Promise.all([fetchDict(lang), fetchDict("en")]);
    state.pref = pref;
    state.lang = lang;
    state.dict = dict;
    state.fallback = fallback;
    const info = L.applyLanguage(lang, root.document);
    L.remember(lang, null, root);
    apply(root.document);
    if (root.document && root.document.title !== undefined) root.document.title = t("app.title");
    if (root.dispatchEvent && typeof root.CustomEvent === "function") {
      root.dispatchEvent(new root.CustomEvent("lumen:langchange",
        { detail: { lang, dir: info.dir, pref } }));
    }
    return lang;
  }

  /** Test seam: install dictionaries without fetch. */
  function _load(lang, dict, fallback) {
    state.lang = lang; state.dict = dict; state.fallback = fallback || dict;
  }

  return {
    SUPPORTED, PREFS, t, apply, setPreference, format, pluralCategory, _load,
    get lang() { return state.lang; },
    get pref() { return state.pref; },
    get dir() { return layout().dirFor(state.lang); },
  };
});
