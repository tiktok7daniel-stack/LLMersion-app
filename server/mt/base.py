"""Contract for translation backends.

A backend declares which target languages it can produce (`targets`, default
Chinese only, so a plugin written before Arabic existed keeps working) and
implements `translate`. The reader asks for a target explicitly; the manager
only routes a request to a backend that lists it.
"""
from __future__ import annotations

from .. import prompts

# human-readable names, used inside LLM prompts and status messages
LANG_NAMES = {"ar": "Arabic", "zh": "Simplified Chinese"}


class MTBackend:
    id: str = ""
    label: str = ""
    rank: int = 100
    notes: str = ""
    parallel: int = 1      # >1 means the backend is safe to call concurrently
    targets: tuple[str, ...] = ("zh",)

    @classmethod
    def check(cls) -> tuple[bool, str]:
        return True, ""

    @classmethod
    def list_models(cls) -> list[dict]:
        """[{id, label, targets?}] — populates the model dropdown.

        A model may carry its own `targets` list when it supports fewer
        languages than the backend as a whole.
        """
        return []

    @classmethod
    def models_for(cls, target: str) -> list[dict]:
        return [m for m in cls.list_models()
                if target in m.get("targets", cls.targets)]

    def load(self) -> None:
        pass

    def translate(self, texts: list[str], model: str, target: str = "zh") -> list[str]:
        raise NotImplementedError


def system_prompt(target: str) -> str:
    """The LLM translation prompt for `target` (prompts/mt.<target>.txt)."""
    return prompts.load(f"mt.{target}")


def join_sentences(parts: list[str], target: str) -> str:
    """Chinese runs together; Arabic, like English, takes a space between sentences."""
    return ("" if target == "zh" else " ").join(p.strip() for p in parts if p.strip())
