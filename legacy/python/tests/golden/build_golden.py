"""Materialise the golden dataset to JSON files for human inspection.

    python -m tests.golden.build_golden

Writes one file per case into tests/golden/cases/ plus a manifest.json listing the
expected answer for each. The Python dataset (dataset.py) remains the source of truth;
these files are a convenience for eyeballing what the pipeline is graded against.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.golden.dataset import ALL_CASES

OUT = Path(__file__).resolve().parent / "cases"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    manifest = []
    for case in ALL_CASES:
        name = case["name"]
        (OUT / f"{name}.json").write_text(
            json.dumps(case["bundle"], indent=2, sort_keys=True), encoding="utf-8")
        manifest.append({"name": name, "stock_name": case["stock_name"],
                         "expect": case["expect"]})
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(ALL_CASES)} golden bundles + manifest to {OUT}")


if __name__ == "__main__":
    main()
