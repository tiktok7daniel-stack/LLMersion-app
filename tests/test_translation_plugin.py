"""English -> Arabic translation plugin (opus-mt-en-ar) and the target-aware registry."""
from __future__ import annotations

import pytest

from server import config, translate
from server.mt import MANAGER, REGISTRY, discover
from server.mt import opus_ar
from server.mt.base import MTBackend

discover()


class FakeTokenizer:
    def convert_tokens_to_ids(self, tok):
        return {"arb_Arab": 7}.get(tok, 0)


def test_plugin_registered_with_arabic_target_and_zh_untouched():
    assert "opus_ar" in REGISTRY and REGISTRY["opus_ar"].targets == ("ar",)
    hf = REGISTRY["hf"]
    ids = [m["id"] for m in hf.list_models()]
    assert "Helsinki-NLP/opus-mt-en-zh" in ids, "opus-mt-en-zh must stay in the registry"
    assert hf.targets == ("zh",)
    assert set(REGISTRY["ollama"].targets) == {"zh", "ar"}


def test_default_arabic_model_is_opus_mt_en_ar():
    ids = [m["id"] for m in opus_ar.MODELS]
    assert ids[0] == "Helsinki-NLP/opus-mt-en-ar"
    assert "facebook/nllb-200-distilled-600M" in ids      # a better, slower alternative
    assert config.MT_PREFS["ar"]["model"] == "Helsinki-NLP/opus-mt-en-ar"


def test_opus_mt_sources_carry_the_target_language_token():
    assert opus_ar.prepare("Helsinki-NLP/opus-mt-en-ar", ["Hello."]) == [">>ara<< Hello."]
    assert opus_ar.prepare("facebook/nllb-200-1.3B", ["Hello."]) == ["Hello."]
    assert opus_ar.generation_kwargs("facebook/nllb-200-1.3B", FakeTokenizer()) == {"forced_bos_token_id": 7}
    assert opus_ar.generation_kwargs("Helsinki-NLP/opus-mt-en-ar", FakeTokenizer()) == {}


def test_translate_runs_each_sentence_and_joins_with_spaces(monkeypatch):
    seen = []

    def fake_generate(tok, mdl, dev, sources, **kw):
        seen.append(list(sources))
        return [f"ترجمة:{s}" for s in sources]

    monkeypatch.setattr(opus_ar, "generate", fake_generate)
    b = opus_ar.OpusArabicBackend()
    b.load()
    monkeypatch.setattr(b, "_pair", lambda model: (FakeTokenizer(), None, "cpu"))
    out = b.translate(["The sky is blue. The sea is deep."], "Helsinki-NLP/opus-mt-en-ar", "ar")
    assert len(out) == 1
    assert seen and all(s.startswith(">>ara<< ") for s in seen[0])
    assert len(seen[0]) == 2                      # two sentences, translated together
    assert out[0].count("ترجمة:") == 2 and " " in out[0]


def test_manager_routes_by_target(monkeypatch):
    class FakeAr(MTBackend):
        id, label, rank, targets = "fake_ar", "fake", 1, ("ar",)
        @classmethod
        def list_models(cls): return [{"id": "m-ar", "label": "m"}]
        def translate(self, texts, model, target="zh"): return [f"{target}:{t}" for t in texts]

    class FakeZh(FakeAr):
        id, targets = "fake_zh", ("zh",)
        @classmethod
        def list_models(cls): return [{"id": "m-zh", "label": "m"}]

    monkeypatch.setitem(REGISTRY, "fake_ar", FakeAr)
    monkeypatch.setitem(REGISTRY, "fake_zh", FakeZh)
    monkeypatch.setattr(MANAGER, "_checks", {"fake_ar": (True, ""), "fake_zh": (True, "")})
    monkeypatch.setattr(MANAGER, "_live", {})
    assert MANAGER.default("ar") == ("fake_ar", "m-ar")
    assert MANAGER.default("zh") == ("fake_zh", "m-zh")
    assert MANAGER.translate(["hi"], "fake_ar", "m-ar", "ar") == ["ar:hi"]
    with pytest.raises(RuntimeError):
        MANAGER.translate(["hi"], "fake_ar", "m-ar", "zh")


def test_model_is_selectable_in_config(monkeypatch):
    class Fake(MTBackend):
        id, label, rank, targets = "fake_sel", "f", 1, ("ar",)
        @classmethod
        def list_models(cls): return [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]

    monkeypatch.setitem(REGISTRY, "fake_sel", Fake)
    monkeypatch.setattr(MANAGER, "_checks", {"fake_sel": (True, "")})
    monkeypatch.setitem(config.MT_PREFS, "ar", {"backend": "fake_sel", "model": "b"})
    assert MANAGER.default("ar") == ("fake_sel", "b")
    monkeypatch.setitem(config.MT_PREFS, "ar", {"backend": "fake_sel", "model": "missing"})
    assert MANAGER.default("ar") == ("fake_sel", "a")      # unknown model -> first listed


def test_cache_keys_are_per_target_and_zh_keeps_its_old_key():
    from server import cache
    assert translate.cache_key("ar", "b", "m", "hi") != translate.cache_key("zh", "b", "m", "hi")
    assert translate.cache_key("zh", "b", "m", "hi") == cache.sha1("b:m", "hi")


def test_translation_is_cached_per_target(isolated, monkeypatch):
    calls = []

    class Counting(MTBackend):
        id, label, rank, targets = "counting", "c", 1, ("ar", "zh")
        @classmethod
        def list_models(cls): return [{"id": "m", "label": "m"}]
        def translate(self, texts, model, target="zh"):
            calls.append((target, list(texts)))
            return [f"{target}-{t}" for t in texts]

    monkeypatch.setitem(REGISTRY, "counting", Counting)
    monkeypatch.setattr(MANAGER, "_checks", {"counting": (True, "")})
    monkeypatch.setattr(MANAGER, "_live", {})
    assert translate.translate(["a", "b"], "counting", "m", "ar") == ["ar-a", "ar-b"]
    assert translate.translate(["a", "b"], "counting", "m", "ar") == ["ar-a", "ar-b"]
    assert len(calls) == 1, "second call must be served from the cache"
    assert translate.translate(["a"], "counting", "m", "zh") == ["zh-a"]
    assert len(calls) == 2, "another target must not reuse the Arabic row"
    assert translate.translate(["a", "c"], "counting", "m", "ar") == ["ar-a", "ar-c"]
    assert calls[-1] == ("ar", ["c"]), "only the missing sentence is translated"


def test_llm_translation_prompts_exist_for_both_targets():
    from server.mt.base import system_prompt
    assert "Arabic" in system_prompt("ar") and "Chinese" in system_prompt("zh")


def test_missing_backend_returns_empty_strings(isolated, monkeypatch):
    monkeypatch.setattr(MANAGER, "default", lambda target="zh": ("none", ""))
    assert translate.translate(["x"], target="ar") == [""]
