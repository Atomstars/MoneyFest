"""Follow-up marker for phase-3.5 (see PROMPT_PHASE3.md §0.2).

Tier-2 evidence should carry a numeric signed move so direction checks don't depend on
headline keyword inference. Text inference is lossy: a macro headline that omits an
explicit rose/fell word (or phrases it unusually) yields move_sign 0 and the direction
check silently skips. This xfail documents the gap; remove it when the bundle schema
grows a numeric ``move_sign`` on Tier-2 rows.
"""

from __future__ import annotations

import pytest

from app.attrib.rubric import text_move_sign


@pytest.mark.xfail(reason="phase-3.5: Tier-2 rows need a numeric signed move; "
                          "text inference misses non-standard phrasing",
                   strict=True)
def test_numeric_move_sign_not_yet_available():
    # A real macro observation with a clear sign, phrased without a rose/fell keyword.
    # Today this returns 0 (indeterminate); after phase-3.5 the numeric field makes it -1.
    assert text_move_sign("USDINR settled at 84.9, a 0.8% depreciation session") == -1
