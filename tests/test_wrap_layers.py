"""Tests for the separated text-wrapping layers.

The rendering pipeline is decomposed in to four layers, each independently
testable:

1. Measurement (:class:`rich.measure.Measurement` and
   :func:`rich.measure.measure_renderables`) answers "how much width is
   needed" and does not care how the text will be folded.
2. Tokenization and wrapping (:func:`rich._wrap.words` and
   :func:`rich._wrap.divide_line`) depend only on the text and the available
   cell width, and may be called without a console.
3. Cell widths and chopping (:func:`rich.cells.cell_len`,
   :func:`rich.cells.set_cell_size` and :func:`rich.cells.chop_cells`) own
   the boundaries of CJK wide characters and combining characters.
4. :class:`rich.segment.Segment` only delivers already-decided text splits
   to the terminal.

The equivalence tests at the bottom compare full renders against a golden
file generated from the pre-refactor code, guaranteeing that the refactor
preserves rendering output character for character.
"""

import json

from rich._wrap import divide_line, words
from rich.cells import cell_len, chop_cells, set_cell_size
from rich.console import Console
from rich.containers import Lines
from rich.measure import Measurement
from rich.segment import Segment
from rich.text import Text

from ._wrap_equivalence import (
    JUSTIFIES,
    NO_WRAPS,
    OVERFLOWS,
    PLAIN_TEXTS,
    WIDTHS,
    iter_cases,
    iter_measure_cases,
    load_golden,
)


# Layer 2: tokenization and wrapping are pure functions of text and width.


def test_words_tokenizer():
    assert list(words("Hello, World!")) == [
        (0, 7, "Hello, "),
        (7, 13, "World!"),
    ]
    assert list(words("foo bar  baz")) == [
        (0, 4, "foo "),
        (4, 9, "bar  "),
        (9, 12, "baz"),
    ]
    assert list(words("")) == []
    # Trailing whitespace is attached to the preceding word.
    assert list(words("word   ")) == [(0, 7, "word   ")]


def test_divide_line_no_console():
    """Break positions may be computed without constructing a console."""
    assert divide_line("Hello, World!", 6) == [7]
    assert divide_line("foo bar baz", 4) == [4, 8]
    # No break required when everything fits.
    assert divide_line("fits", 10) == []
    # Long words are folded when fold=True...
    assert divide_line("abcdefghij", 4, fold=True) == [4, 8]
    # ...and cropped (no break positions) when fold=False.
    assert divide_line("abcdefghij", 4, fold=False) == []


def test_divide_line_wide_characters():
    """CJK characters occupy two cells; breaks fall on character boundaries."""
    # 中 is 2 cells wide, so only two fit in a width of 4.
    assert divide_line("中中中", 4) == [2]
    # A break never splits a double-width character: "ab中c" fills 5 cells,
    # so the single fold break lands after it (string offset 4).
    assert divide_line("ab中cd中ef", 5) == [4]


# Layer 3: cell widths and chopping own wide / combining character boundaries.


def test_cell_len_boundaries():
    assert cell_len("abc") == 3
    assert cell_len("中文") == 4
    assert cell_len("a中b") == 4
    # Combining characters add no width.
    assert cell_len("á") == 1
    assert cell_len("áb̂ç") == 3
    # Zero width joiner sequences measure as a single glyph.
    assert cell_len("👨‍👩‍👧‍👦") == 2


def test_set_cell_size_boundaries():
    # Pad and crop ASCII.
    assert set_cell_size("foo", 5) == "foo  "
    assert set_cell_size("foobar", 3) == "foo"
    # Cropping inside a wide character replaces it with a space.
    assert set_cell_size("中文", 3) == "中 "
    assert set_cell_size("中文", 2) == "中"
    assert set_cell_size("中文", 1) == " "
    # Combining characters stay attached to their base character.
    assert set_cell_size("ábc", 1) == "á"


def test_chop_cells_boundaries():
    assert chop_cells("abcdef", 2) == ["ab", "cd", "ef"]
    # Wide characters are never split across lines.
    assert chop_cells("中中中", 4) == ["中中", "中"]
    assert chop_cells("ab中cd", 3) == ["ab", "中c", "d"]
    # Combining characters remain with their base character.
    assert chop_cells("áb", 1) == ["á", "b"]


# Composition: Text.wrap_line applies the pure break offsets to a Text.


def test_wrap_line_matches_divide_line():
    """Text.wrap_line divides at exactly the offsets divide_line computes."""
    text = Text("The quick brown fox jumps over the lazy dog")
    for width in (1, 3, 7, 10, 20):
        for fold in (True, False):
            lines = text.wrap_line(width, fold=fold)
            offsets = divide_line(text.plain, width, fold=fold)
            expected = text.divide(offsets)
            for line in expected:
                line.rstrip_end(width)
            assert [line.plain for line in lines] == [
                line.plain for line in expected
            ]


def test_wrap_line_preserves_spans():
    """Span-aware splitting survives the trip through the wrap layer."""
    text = Text("foo bar baz")
    text.stylize("bold", 0, 11)
    lines = text.wrap_line(4)
    assert [line.plain for line in lines] == ["foo ", "bar ", "baz"]
    for line in lines:
        assert line._spans, "spans should be distributed to divided lines"


def test_wrap_line_no_console():
    """The break decision for a line does not require a console."""
    lines = Text("中文混排 English").wrap_line(8)
    assert isinstance(lines, Lines)
    assert [line.plain for line in lines] == ["中文混排 ", "English"]


# Layer 1: measurement answers "how wide" and ignores folding concerns.


def test_measurement_ignores_folding_options():
    """Measurement is independent of justify / overflow / no_wrap options."""
    console = Console(width=20)
    text = Text("The quick brown fox jumps over the lazy dog")
    base_options = console.options
    baseline = Measurement.get(console, base_options, text)
    for justify in JUSTIFIES:
        for overflow in OVERFLOWS:
            for no_wrap in NO_WRAPS:
                options = base_options.update(
                    justify=justify, overflow=overflow, no_wrap=no_wrap
                )
                assert Measurement.get(console, options, text) == baseline


def test_measurement_reports_required_width():
    console = Console(width=80)
    measurement = console.measure(Text("中文混排 English"))
    assert measurement.maximum == cell_len("中文混排 English")
    assert measurement.minimum == max(
        cell_len(word) for word in "中文混排 English".split()
    )


# Layer 4: Segment only delivers already-decided splits to the terminal.


def test_segment_delivers_decided_splits():
    """Segments split at a cell position carry the decided text onwards."""
    segment = Segment("中文字", None)
    left, right = segment.split_cells(2)
    assert (left.text, right.text) == ("中", "文字")
    # Splitting inside a wide character pads both sides with spaces.
    left, right = segment.split_cells(3)
    assert (left.text, right.text) == ("中 ", " 字")


# Equivalence: rendering is character-for-character identical to the
# pre-refactor golden output.


def test_render_equivalence():
    golden = load_golden()["render"]
    mismatches = []
    for key, output in iter_cases():
        expected = golden.get(key)
        if output != expected:
            mismatches.append(key)
    assert not mismatches, (
        f"{len(mismatches)} render(s) differ from the golden output, "
        f"first: {mismatches[:3]}"
    )


def test_measure_equivalence():
    golden = load_golden()["measure"]
    for key, measurement in iter_measure_cases():
        assert list(golden[key]) == list(measurement), key
