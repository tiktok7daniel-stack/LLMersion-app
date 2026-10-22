"""Settings, hints, prompts, spaced repetition, dictionary glosses, speed and voices."""
from __future__ import annotations

import pytest

from server import cache, config, dictionary, hints, llm, prompts, settings, srs


# ---------------------------------------------------------------- settings
def test_settings_defaults(client):
    s = client.get("/api/settings").json()
    assert s["ui_lang"] == "system" and s["translation_target"] == "ar"
    assert s["show_translation"] is True and s["ocr_enabled"] is True and s["ocr_arabic"] is False
    assert s["tts_speed"] == 0.8, "learners start at 0.8x"
    assert s["curator"] is False, "the optional curator is off by default"


def test_settings_persist_and_validate(client):
    out = client.post("/api/settings", json={"ui_lang": "ar", "translation_target": "zh",
                                             "show_translation": False, "tts_speed": 9,
                                             "text_scale": 500, "bogus": 1}).json()
    assert out["ui_lang"] == "ar" and out["translation_target"] == "zh"
    assert out["show_translation"] is False
    assert out["tts_speed"] == 1.5, "speed is clamped to 0.5-1.5"
    assert out["text_scale"] == 150 and "bogus" not in out
    again = client.get("/api/settings").json()
    assert again == out, "settings must survive a reload"
    bad = client.post("/api/settings", json={"ui_lang": "fr", "translation_target": "de",
                                             "show_translation": "yes"}).json()
    assert bad["ui_lang"] == "ar" and bad["translation_target"] == "zh" and bad["show_translation"] is False
    assert client.post("/api/settings", json={"tts_speed": 0.1}).json()["tts_speed"] == 0.5


def test_black_theme_is_a_valid_setting(client):
    assert client.post("/api/settings", json={"theme": "black"}).json()["theme"] == "black"


def test_settings_survive_a_corrupt_file(isolated):
    config.SETTINGS_PATH.write_text("{not json", encoding="utf-8")
    assert settings.load()["ui_lang"] == "system"


def test_clear_caches_endpoints(client):
    cache.put_trans("k", "v")
    assert client.post("/api/cache/clear", json={"what": "translations"}).json()["removed"] == 1
    assert cache.get_trans("k") is None
    cache.put_doc("d", "t", 1, {}, [])
    assert client.post("/api/cache/clear", json={"what": "documents"}).json()["docs"] == 1
    assert client.post("/api/cache/clear", json={"what": "everything"}).status_code == 400


def test_config_endpoint_exposes_branding_settings_and_ocr(client):
    d = client.get("/api/config").json()
    assert d["app"]["name"] == "LumenRead"
    assert d["speed_range"] == [0.5, 1.5] and d["speed"] == 0.8
    assert "settings" in d and "ocr" in d and d["mt"]["targets"] == ["ar", "zh"]
    assert set(d["mt"]["defaults"]) == {"ar", "zh"}


def test_about_lists_upstream_and_model_licenses(client):
    d = client.get("/api/about").json()
    assert d["name"] == "LumenRead" and d["code_license"] == "MIT"
    assert d["upstream"]["repo"] == "https://github.com/QM378/LLMersion"
    lic = {m["id"]: m["license"] for m in d["models"]}
    assert lic["opus-mt-en-ar"] == "CC-BY-4.0" and lic["kokoro"] == "Apache-2.0" and lic["whisper"] == "MIT"


# ---------------------------------------------------------------- prompts
KINDS = ["tutor", "correction", "pronunciation", "writing"]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("lang", ["ar", "zh"])
def test_every_hint_prompt_variant_exists_and_fills(kind, lang):
    ctx = {"text": "How was your day?", "said": "I goed", "fixed": "I went", "why": "Irregular verb.",
           "word": "think", "ops": [{"op": "sub", "target": "θ", "heard": "s"}], "feedback": "**Notes** x"}
    text = hints._prompt(kind, lang, ctx)
    assert "{" not in text.replace("{}", ""), f"unfilled placeholder in {kind}.{lang}: {text}"
    assert len(text) > 80


def test_arabic_hint_prompts_ask_for_arabic_and_keep_english_default():
    assert "IN ARABIC" in prompts.load("tutor.hint_ar", text="x")
    assert "IN SIMPLIFIED CHINESE" in prompts.load("tutor.hint_zh", text="x")
    assert "English only" in prompts.load("tutor.en", level="B1", vocab="x")
    assert "English sentence" in prompts.load("correction.en", said="x")
    assert "Write only in English" in prompts.load("writing.en", vocab="a", text="b")


def test_prompt_braces_in_user_text_survive():
    assert '{"a": 1}' in prompts.load("simplify.en", text='{"a": 1}')


# ---------------------------------------------------------------- hints
def test_hint_uses_the_llm_and_caches(isolated, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "chat", lambda p, **k: (calls.append(p), "تلميح بالعربية")[1])
    ctx = {"said": "I goed home", "fixed": "I went home", "why": "Use the past of go."}
    a = hints.make("correction", "ar", ctx)
    b = hints.make("correction", "ar", ctx)
    assert a == {"hint": "تلميح بالعربية", "lang": "ar", "source": "llm"}
    assert b["source"] == "cache" and len(calls) == 1
    assert "IN ARABIC" in calls[0]


def test_hint_falls_back_to_machine_translation_without_an_llm(isolated, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    monkeypatch.setattr(hints.translate, "translate", lambda texts, **k: [f"AR:{texts[0]}"])
    out = hints.make("tutor", "ar", {"text": "What is light?"})
    assert out == {"hint": "AR:What is light?", "lang": "ar", "source": "mt"}


def test_hint_without_llm_or_fallback_is_a_localisable_error(isolated, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    with pytest.raises(hints.HintError) as e:
        hints.make("pronunciation", "ar", {"word": "think", "ops": []})
    assert e.value.key == "err.hint_unavailable"
    with pytest.raises(hints.HintError) as e:
        hints.make("nonsense", "ar", {})
    assert e.value.key == "err.hint_kind"


def test_hint_endpoint_and_writing_are_english_first(client, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    seen = []
    monkeypatch.setattr(llm, "chat", lambda p, **k: (seen.append(p), "feedback")[1])
    w = client.post("/api/writing", json={"text": "I goed to school yesterday and learn many thing."}).json()
    assert w == {"feedback": "feedback"} and "Write only in English" in seen[0]
    h = client.post("/api/hint", json={"kind": "writing", "feedback": "**Notes** x", "lang": "ar"}).json()
    assert h["lang"] == "ar" and "IN ARABIC" in seen[-1]
    short = client.post("/api/writing", json={"text": "hi"}).json()
    assert short["error_key"] == "err.write_too_short"


def test_talk_coach_explains_in_english_by_default(monkeypatch):
    from talk import dialogue
    monkeypatch.setattr(dialogue.config, "DEV", False)
    monkeypatch.setattr(dialogue, "_chat", lambda msgs, **k: (
        "FIXED: She *goes* to school.\nWHY: A third-person singular subject needs -s on the verb."))
    out = dialogue.coach("She go to school every day")
    assert out["fixed"] == "She *goes* to school." and out["why"].startswith("A third-person")
    sent = prompts.load("correction.en", said="x")
    assert "one complete English sentence" in sent


def test_tutor_system_prompt_is_english(monkeypatch):
    from talk import dialogue
    s = dialogue._system("free", None, "", ["light"])
    assert "English only" in s and "light" in s


# ---------------------------------------------------------------- SRS
def test_leitner_schedule():
    now = 1000.0
    assert srs.next_state(0, 2, now) == (1, now + srs.DAY)
    assert srs.next_state(3, 0, now) == (0, now + 600)
    box, due = srs.next_state(2, 3, now)
    assert box == 4 and due == now + 8 * srs.DAY
    assert srs.next_state(6, 3, now)[0] == 6, "capped at the top box"
    assert srs.next_state(0, 1, now)[1] >= now + srs.DAY, "hard is never sooner than a day"


def test_review_endpoint_schedules_the_card(client):
    cache.add_vocab("luminous", "", "ˈluːmɪnəs", "A luminous sky.", "", ar="مضيء")
    r = client.post("/api/vocab/review", json={"word": "luminous", "grade": 2}).json()
    assert r["ok"] and r["box"] == 1
    row = [v for v in client.get("/api/vocab").json()["items"] if v["word"] == "luminous"][0]
    assert row["box"] == 1 and row["due"] > 0 and row["ar"] == "مضيء"
    assert client.post("/api/vocab/review", json={"word": "ghost", "grade": 2}).json() == {"ok": False}


def test_vocab_stores_both_glosses_and_exports_them(client):
    cache.add_vocab("light", "光", "laɪt", "ctx", "", ar="ضوء")
    cache.add_vocab("light", "", "", "", "", ar="")        # a repeat keeps what is there
    row = cache.list_vocab()[0]
    assert (row["zh"], row["ar"], row["hits"]) == ("光", "ضوء", 2)
    cache.set_gloss("light", "ar", "نور")
    assert cache.list_vocab()[0]["ar"] == "ضوء", "an existing gloss is never overwritten"
    csv = client.get("/api/vocab/export.csv").content.decode("utf-8-sig")
    assert "arabic" in csv.splitlines()[0] and "ضوء" in csv


# ---------------------------------------------------------------- dictionary: IPA + English definition + gloss
@pytest.fixture()
def tiny_dictionary(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / "ecdict.db"
    c = sqlite3.connect(db)
    c.executescript("""
      CREATE TABLE entry (word TEXT PRIMARY KEY, phonetic TEXT, definition TEXT, translation TEXT,
                          pos TEXT, collins INTEGER, oxford INTEGER, tag TEXT, bnc INTEGER, frq INTEGER, exchange TEXT);
      CREATE TABLE lemma (form TEXT PRIMARY KEY, base TEXT);
      INSERT INTO entry VALUES ('light','laɪt','n. the natural agent that makes things visible','n. 光，光线',
                                '',0,0,'cet4',0,0,'');
      INSERT INTO lemma VALUES ('lights','light');
    """)
    c.commit(); c.close()
    monkeypatch.setattr(config, "DICT_DB", db)
    monkeypatch.setattr(dictionary._local, "dict", None, raising=False)
    return db


def test_word_tap_gives_ipa_english_definition_and_arabic_gloss(tiny_dictionary, isolated, monkeypatch):
    from server import translate
    monkeypatch.setattr(translate, "translate", lambda texts, **k: [f"ar:{texts[0]}"] if k.get("target") == "ar" else ["zh"])
    d = dictionary.lookup("lights", "ar")
    assert d["word"] == "light" and d["lemma_of"] == "light"
    assert d["phonetic"] == "laɪt"
    assert d["definition"].startswith("n. the natural agent")
    assert d["gloss"] == "ar:light" and d["target"] == "ar" and d["translation"] == d["gloss"]
    assert "光" in d["zh"], "the Chinese gloss is still returned"
    zh = dictionary.lookup("light", "zh")
    assert "光" in zh["gloss"] and zh["target"] == "zh"


def test_lookup_without_a_dictionary_still_returns_a_gloss(isolated, monkeypatch):
    from server import translate
    monkeypatch.setattr(config, "DICT_DB", isolated / "none.db")
    monkeypatch.setattr(dictionary._local, "dict", None, raising=False)
    monkeypatch.setattr(translate, "translate", lambda texts, **k: ["غلاف"])
    monkeypatch.setattr(dictionary, "_define", lambda w: "a thin cover")
    d = dictionary.lookup("sheath", "ar")
    assert d["gloss"] == "غلاف" and d["definition"] == "a thin cover" and d["source"] == "mt"


def test_lookup_endpoint_takes_a_target(client, tiny_dictionary, monkeypatch):
    from server import translate
    monkeypatch.setattr(translate, "translate", lambda texts, **k: ["ضوء"])
    d = client.get("/api/lookup", params={"q": "light", "target": "ar"}).json()
    assert d["gloss"] == "ضوء" and d["phonetic"] == "laɪt"


# ---------------------------------------------------------------- reading speed & voices
def test_default_speed_and_range():
    assert config.TTS_SPEED == 0.8
    assert (config.TTS_SPEED_MIN, config.TTS_SPEED_MAX) == (0.5, 1.5)


def test_tts_endpoint_clamps_speed(client, monkeypatch):
    from server import main as m
    assert m._speed(5) == 1.5 and m._speed(0.1) == 0.5 and m._speed("x") == 0.8
    assert m._speed(None) == 0.8


def test_arabic_voices_are_never_the_default_reading_voice(monkeypatch):
    from server.engines import MANAGER, Voice
    ar = Voice(id="kareem", label="k", engine="piper_ar", lang="ar")
    en = Voice(id="am", label="a", engine="kokoro")
    monkeypatch.setattr(MANAGER, "voices", lambda: [ar, en])
    assert MANAGER.default_voice().id == "am"
    monkeypatch.setattr(MANAGER, "voices", lambda: [ar])
    assert MANAGER.default_voice() is None


def test_piper_arabic_is_an_optional_plugin():
    from server.engines import REGISTRY, discover
    discover()
    assert "piper_ar" in REGISTRY
    ok, why = REGISTRY["piper_ar"].check()
    assert ok is False and why, "absent by default, with a reason shown in the UI"


def test_english_voice_never_receives_arabic_or_chinese_text():
    from server.textseg import strip_cjk
    assert strip_cjk("Hello مرحبا world 你好") == "Hello world"


def test_banner_and_title_use_the_new_name(client):
    assert "LumenRead" in client.get("/").text
    assert client.get("/i18n/ar.json").json()["app.tagline"] == "اقرأ. استمع. تحدث. افهم."
    assert client.get("/manifest.webmanifest").json()["name"] == "LumenRead"
    assert client.get("/brand/logo.svg").status_code == 200
    assert client.get("/fonts/fonts.css").status_code == 200
