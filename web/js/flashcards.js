/* Flashcard model — pure functions, no DOM, so direction rules are testable.
 *
 * Front of the card: the English word. Always left-to-right, language "en",
 * even in the Arabic UI. Back of the card (optional, toggled by the learner):
 * the gloss in the translation language — Arabic is right-to-left (lang "ar"),
 * Chinese left-to-right (lang "zh-Hans"). The example sentence is English, so
 * it is left-to-right too. The *chrome around* the card (counter, key hints,
 * progress rail) follows the UI direction, and so does which arrow key moves to
 * the next card.
 */
(function (root, factory) {
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LumenFlash = api;
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  const BACK_FACE = {
    ar: { lang: "ar", dir: "rtl" },
    zh: { lang: "zh-Hans", dir: "ltr" },
  };

  const layout = () => root.LumenLayout || require("./layout.js");

  function glossFor(item, target) {
    const g = target === "ar" ? item.ar : item.zh;
    return (g || "").trim();
  }

  /** Everything the renderer needs to lay a card out. */
  function cardModel(item, opts) {
    opts = opts || {};
    const target = opts.target === "zh" ? "zh" : "ar";
    const uiDir = opts.uiDir === "rtl" ? "rtl" : "ltr";
    const L = layout();
    const face = BACK_FACE[target];
    return {
      front: { text: item.word, dir: "ltr", lang: "en", ipa: item.phonetic ? `/${item.phonetic}/` : "" },
      back: { visible: !!opts.showBack, text: glossFor(item, target), dir: face.dir, lang: face.lang },
      context: { text: item.context || "", dir: "ltr", lang: "en" },
      keys: { next: L.nextKey(uiDir), prev: L.prevKey(uiDir) },
    };
  }

  /** Cards that are due first (never-reviewed counts as due), oldest due first. */
  function sortDue(items, now) {
    now = now == null ? Date.now() / 1000 : now;
    return items.slice().sort((a, b) => (a.due || 0) - (b.due || 0)
      || (a.ts || 0) - (b.ts || 0)).map((x) => ({ ...x, _due: (x.due || 0) <= now }));
  }

  return { BACK_FACE, glossFor, cardModel, sortDue };
});
