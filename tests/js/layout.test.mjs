// RTL layout switching, language resolution, i18n plurals and flashcard directionality.
// Run: node --test tests/js     (pytest runs it too, see tests/test_js.py)
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const Layout = require("../../web/js/layout.js");
const I18n = require("../../web/js/i18n.js");
const Flash = require("../../web/js/flashcards.js");

/** Just enough of a document for the layout controller. */
function fakeDoc() {
  const attrs = {};
  return {
    attrs,
    documentElement: {
      setAttribute: (k, v) => { attrs[k] = v; },
      getAttribute: (k) => attrs[k] ?? null,
    },
  };
}
const fakeWin = (langs, stored = {}, dark = false) => ({
  navigator: { languages: langs, language: langs[0] },
  matchMedia: () => ({ matches: dark }),
  localStorage: { getItem: (k) => stored[k] ?? null, setItem: (k, v) => { stored[k] = v; } },
});

test("Arabic sets <html dir=rtl lang=ar>; English sets ltr/en", () => {
  const doc = fakeDoc();
  assert.deepEqual(Layout.applyLanguage("ar", doc), { lang: "ar", dir: "rtl" });
  assert.equal(doc.attrs.dir, "rtl");
  assert.equal(doc.attrs.lang, "ar");
  Layout.applyLanguage("en", doc);
  assert.equal(doc.attrs.dir, "ltr");
  assert.equal(doc.attrs.lang, "en");
});

test("switching back and forth leaves no stale direction", () => {
  const doc = fakeDoc();
  for (const l of ["ar", "en", "ar", "ar", "en"]) {
    const { dir } = Layout.applyLanguage(l, doc);
    assert.equal(doc.attrs.dir, dir);
    assert.equal(dir, l === "ar" ? "rtl" : "ltr");
  }
});

test("system locale: ar and en are honoured, anything else falls back to English", () => {
  assert.equal(Layout.resolveLang("system", ["ar-EG", "en-US"]), "ar");
  assert.equal(Layout.resolveLang("system", ["en-GB"]), "en");
  assert.equal(Layout.resolveLang("system", ["fr-FR", "de"]), "en");
  assert.equal(Layout.resolveLang("system", ["fr-FR", "ar"]), "ar");
  assert.equal(Layout.resolveLang("system", []), "en");
  assert.equal(Layout.resolveLang("ar", ["en"]), "ar");
  assert.equal(Layout.resolveLang("en", ["ar"]), "en");
});

test("first paint uses the saved language, else the system locale", () => {
  let doc = fakeDoc();
  Layout.applyEarly(doc, fakeWin(["en-US"], { "lumen.lang": "ar" }));
  assert.equal(doc.attrs.dir, "rtl");
  doc = fakeDoc();
  Layout.applyEarly(doc, fakeWin(["ar"]));
  assert.equal(doc.attrs.dir, "rtl");
  doc = fakeDoc();
  Layout.applyEarly(doc, fakeWin(["ja"]));
  assert.equal(doc.attrs.dir, "ltr");
  assert.equal(doc.attrs.lang, "en");
});

test("theme follows the preference, or the OS when set to system", () => {
  const doc = fakeDoc();
  assert.equal(Layout.applyTheme("dark", doc, fakeWin(["en"])), "dark");
  assert.equal(Layout.applyTheme("light", doc, fakeWin(["en"], {}, true)), "light");
  assert.equal(Layout.applyTheme("system", doc, fakeWin(["en"], {}, true)), "dark");
  assert.equal(doc.attrs["data-theme"], "dark");
  assert.equal(Layout.applyTheme("black", doc, fakeWin(["en"])), "black");
  assert.equal(doc.attrs["data-theme"], "black");
});

test("arrow keys and track position mirror with the UI direction", () => {
  assert.equal(Layout.nextKey("ltr"), "ArrowRight");
  assert.equal(Layout.nextKey("rtl"), "ArrowLeft");
  assert.equal(Layout.prevKey("rtl"), "ArrowRight");
  const rect = { left: 100, width: 200 };
  assert.equal(Layout.trackFraction(125, rect, "ltr"), 0.125);
  assert.equal(Layout.trackFraction(125, rect, "rtl"), 0.875);
  assert.equal(Layout.trackFraction(0, rect, "ltr"), 0);
  assert.equal(Layout.trackFraction(999, rect, "ltr"), 1);
});

test("English and numbers keep their direction inside Arabic text", () => {
  assert.equal(Layout.ltr("Chapter 3"), '<bdi dir="ltr">Chapter 3</bdi>');
  assert.equal(Layout.ltr("<b>"), '<bdi dir="ltr">&lt;b&gt;</bdi>');
  assert.equal(Layout.contentDir("en"), "ltr");
  assert.equal(Layout.contentDir("ar"), "rtl");
});

test("i18n: parameters, fallback to English, and Arabic plural categories", () => {
  I18n._load("ar", {
    "a_one": "كلمة", "a_two": "كلمتان", "a_few": "{n} كلمات", "a_many": "{n} كلمة", "a_other": "{n} كلمة",
    "greet": "مرحبًا {name}",
  }, { "greet": "Hello {name}", "only_en": "English only" });
  assert.equal(I18n.t("greet", { name: "Sara" }), "مرحبًا Sara");
  assert.equal(I18n.t("only_en"), "English only");
  assert.equal(I18n.t("nope.key"), "nope.key");
  assert.equal(I18n.t("a", { n: 1 }), "كلمة");
  assert.equal(I18n.t("a", { n: 2 }), "كلمتان");
  assert.equal(I18n.t("a", { n: 5 }), "5 كلمات");
  assert.equal(I18n.t("a", { n: 11 }), "11 كلمة");
  assert.equal(I18n.t("a", { n: 100 }), "100 كلمة");
});

test("flashcard: English front is always LTR, Arabic back is RTL, whatever the UI", () => {
  const item = { word: "luminous", phonetic: "ˈluːmɪnəs", ar: "مضيء", zh: "发光的", context: "A luminous sky." };
  for (const uiDir of ["ltr", "rtl"]) {
    const m = Flash.cardModel(item, { target: "ar", uiDir, showBack: true });
    assert.deepEqual([m.front.dir, m.front.lang], ["ltr", "en"]);
    assert.deepEqual([m.back.dir, m.back.lang, m.back.text], ["rtl", "ar", "مضيء"]);
    assert.deepEqual([m.context.dir, m.context.lang], ["ltr", "en"]);
    assert.equal(m.front.ipa, "/ˈluːmɪnəs/");
  }
});

test("flashcard: Chinese back is LTR; the toggle controls visibility; keys follow the UI", () => {
  const item = { word: "light", ar: "ضوء", zh: "光" };
  const zh = Flash.cardModel(item, { target: "zh", uiDir: "rtl", showBack: false });
  assert.deepEqual([zh.back.dir, zh.back.lang, zh.back.text, zh.back.visible], ["ltr", "zh-Hans", "光", false]);
  assert.equal(zh.keys.next, "ArrowLeft");
  assert.equal(Flash.cardModel(item, { target: "ar", uiDir: "ltr" }).keys.next, "ArrowRight");
});

test("flashcards come due-first", () => {
  const out = Flash.sortDue([{ word: "b", due: 500 }, { word: "a", due: 0 }, { word: "c", due: 100 }], 300);
  assert.deepEqual(out.map((x) => x.word), ["a", "c", "b"]);
  assert.deepEqual(out.map((x) => x._due), [true, true, false]);
});
