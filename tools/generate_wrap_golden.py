#!/usr/bin/env python3
"""Regenerate tests/_wrap_golden.json (the wrap-equivalence golden file).

Run this against the *pre-refactor* code (or any known-good revision) to
capture the reference rendering output. tests/test_wrap_layers.py then
compares the current code against this golden file, guaranteeing that the
layering refactor is character-for-character behavior preserving.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tests._wrap_equivalence import GOLDEN_PATH, generate_golden


def main() -> None:
    golden = generate_golden()
    with open(GOLDEN_PATH, "w", encoding="utf-8") as golden_file:
        json.dump(golden, golden_file, ensure_ascii=False, indent=0, sort_keys=True)
    total = len(golden["render"]) + len(golden["measure"])
    print(f"wrote {total} cases to {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
