"""Shared corpus and render harness for the wrap-equivalence tests.

The layering refactor of the text wrapping pipeline (measure -> wrap ->
cells -> segment) must be behavior preserving: the same text, rendered with
the same console width / justify / overflow / no_wrap combination, must
produce a character-identical string before and after the refactor.

This module renders a fixed corpus of tricky texts through
:meth:`rich.console.Console.print` for every combination of parameters and
compares the output against a golden file (``_wrap_golden.json``) that was
generated from the pre-refactor code with ``tools/generate_wrap_golden.py``.
"""

from __future__ import annotations

import io
import json
import os
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from rich.console import Console
from rich.text import Text

# Rendering must not depend on the ambient environment; mirror the
# reset_color_envvars fixture in tests/conftest.py so that golden generation
# and test runs see the same conditions.
os.environ.pop("FORCE_COLOR", None)
os.environ.pop("NO_COLOR", None)

GOLDEN_PATH = Path(__file__).parent / "_wrap_golden.json"

# Corpus of texts chosen to exercise the boundaries between the layers:
# ASCII, long words (fold/crop), CJK wide characters, combining characters,
# ZWJ emoji, variation selectors, tabs, blank lines and whitespace runs.
PLAIN_TEXTS: List[str] = [
    "Hello, World!",
    "The quick brown fox jumps over the lazy dog. " * 3,
    "supercalifragilisticexpialidocious antidisestablishmentarianism",
    "中文混排 English テスト です",
    "TextualはPythonの高速アプリケーション開発フレームワークです",
    "á b̂ç déf",
    "👨‍👩‍👧‍👦 family ✈️ plane 🏳️‍🌈 flag",
    "a\tb\tc\td",
    "  leading and  multiple   spaces  ",
    "line1\nline2\n\nline4\n",
    "ab中cd中ef",
    "",
    "   ",
    "word " * 20,
    "x",
    "😀😀😀😀😀",
]


def _styled_texts() -> List[Text]:
    """Texts with spans, rendered with a terminal-capable console so that
    span redistribution across wrapped lines is observable in the output."""
    styled = Text("styled wrap test " * 3)
    styled.stylize("bold red", 0, 12)
    styled.stylize("underline", 10, 30)
    wide = Text("中文 spans 混排 " * 3)
    wide.stylize("green", 0, 8)
    wide.stylize("reverse", 6, 20)
    return [styled, wide]


WIDTHS = [1, 2, 3, 5, 8, 10, 13, 20, 40]
JUSTIFIES: List[Optional[str]] = [None, "default", "left", "center", "right", "full"]
OVERFLOWS: List[Optional[str]] = [None, "crop", "fold", "ellipsis", "ignore"]
NO_WRAPS: List[Optional[bool]] = [None, True, False]
# A smaller width set for the Text-attribute matrix (justify/overflow/no_wrap
# set on the Text instance rather than passed to print).
ATTR_WIDTHS = [3, 5, 10, 20]


def _render(
    renderable: Any,
    width: int,
    justify: Optional[str] = None,
    overflow: Optional[str] = None,
    no_wrap: Optional[bool] = None,
    force_terminal: bool = False,
) -> str:
    """Render a single case and return the exact output string."""
    console = Console(
        file=io.StringIO(),
        width=width,
        force_terminal=force_terminal,
        legacy_windows=False,
    )
    console.print(renderable, justify=justify, overflow=overflow, no_wrap=no_wrap)
    return console.file.getvalue()


def iter_cases() -> Iterator[Tuple[str, str]]:
    """Yield (case_key, rendered_output) for the whole equivalence matrix."""
    for index, text in enumerate(PLAIN_TEXTS):
        for width, justify, overflow, no_wrap in product(
            WIDTHS, JUSTIFIES, OVERFLOWS, NO_WRAPS
        ):
            key = json.dumps(["print", index, width, justify, overflow, no_wrap])
            yield key, _render(text, width, justify, overflow, no_wrap)
    for offset, text in enumerate(_styled_texts()):
        index = len(PLAIN_TEXTS) + offset
        for width, justify, overflow, no_wrap in product(
            WIDTHS, JUSTIFIES, OVERFLOWS, NO_WRAPS
        ):
            key = json.dumps(["styled", index, width, justify, overflow, no_wrap])
            yield key, _render(
                text, width, justify, overflow, no_wrap, force_terminal=True
            )
    for index, text in enumerate(PLAIN_TEXTS):
        for width, justify, overflow, no_wrap in product(
            ATTR_WIDTHS, JUSTIFIES, OVERFLOWS, NO_WRAPS
        ):
            key = json.dumps(["attrs", index, width, justify, overflow, no_wrap])
            attributed = Text(
                text, justify=justify, overflow=overflow, no_wrap=no_wrap
            )
            yield key, _render(attributed, width)


def iter_measure_cases() -> Iterator[Tuple[str, List[int]]]:
    """Yield (case_key, [minimum, maximum]) measurements for the corpus."""
    for index, text in enumerate(PLAIN_TEXTS):
        for width in WIDTHS:
            console = Console(file=io.StringIO(), width=width, legacy_windows=False)
            measurement = console.measure(Text(text))
            key = json.dumps(["measure", index, width])
            yield key, [measurement.minimum, measurement.maximum]


def generate_golden() -> Dict[str, Any]:
    """Render every case and return the golden mapping."""
    return {
        "render": dict(iter_cases()),
        "measure": dict(iter_measure_cases()),
    }


def load_golden() -> Dict[str, Any]:
    """Load the golden file generated from the pre-refactor code."""
    with open(GOLDEN_PATH, encoding="utf-8") as golden_file:
        return json.load(golden_file)
