"""Display-only market reference data: quotes, fundamentals, shareholding.

Everything in this package is for **showing the user context about a company**. None
of it reaches the gate, the evidence bundle, or the attribution agent -- and that
boundary is deliberate.

The engine's guarantee is that every explanation traces to cited, tiered evidence
admitted by ``build_bundle``. Fundamentals scraped from a third party carry no tier,
no dissemination timestamp, and no provenance the verifier could check. Letting them
into the reasoning path would quietly break Constraint 6 (CLAUDE.md), so they stay on
this side of the wall: rendered next to the explanation, never an input to it.

Two consequences worth stating plainly:

* **Quotes here are delayed**, scraped from public exchange endpoints. They are not a
  licensed real-time feed and must always be labelled as such in the UI.
* **These sources fail.** Upstream shapes change without notice and endpoints rate-limit.
  Every fetcher returns ``None`` rather than raising on a bad payload, and callers
  render "not available" -- an absent number is honest, a wrong one is not.
"""

from app.marketdata.cache import cached, invalidate, read_cache, write_cache
from app.marketdata.fundamentals import get_financials, get_key_stats, get_profile
from app.marketdata.market import get_indices, get_movers
from app.marketdata.quotes import get_quote
from app.marketdata.shareholding import get_shareholding
from app.marketdata.windows import return_windows

__all__ = [
    "cached", "invalidate", "read_cache", "write_cache",
    "get_key_stats", "get_financials", "get_profile",
    "get_indices", "get_movers",
    "get_quote", "get_shareholding", "return_windows",
]
