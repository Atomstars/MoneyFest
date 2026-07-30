"""Server-rendered UI routes (Phase 4).

FastAPI + Jinja2 + htmx, mounted under /ui. The UI renders what the engine produced --
it computes no financial quantity and never rewrites the explanation text. Every /ui page
and every UI mutation requires the shared token; reads work without JavaScript.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import DISCLAIMER, HISTORY_DAYS
from app.db import fresh_db
from app.web import auth
from app.web import data as webdata
from app.exposure.profiles import effective_profile

_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_DIR / "templates"))
templates.env.globals["DISCLAIMER"] = DISCLAIMER


def _pct(x):
    return "n/a" if x is None else f"{x * 100:+.2f}%"


def _movesign(x):
    if x is None or x == 0:
        return "flat"
    return "up" if x > 0 else "down"


templates.env.filters["pct"] = _pct
templates.env.filters["movesign"] = _movesign

router = APIRouter(prefix="/ui")


def _conn():
    return fresh_db()


def _ctx(request: Request, **kw) -> dict:
    base = {"request": request, "authed": auth.is_authenticated(request)}
    base.update(kw)
    return base


def _guard(request: Request):
    """Return a redirect to login if not authenticated, else None."""
    if not auth.is_authenticated(request):
        return RedirectResponse("/ui/login", status_code=303)
    return None


# --- auth pages ------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str | None = None):
    if auth.is_authenticated(request):
        return RedirectResponse("/ui", status_code=303)
    return templates.TemplateResponse(request, "login.html", _ctx(request, error=error))


@router.post("/login")
def login_submit(request: Request, token: str = Form("")):
    if not auth.check_password(token):
        return templates.TemplateResponse(
            request, "login.html", _ctx(request, error="Invalid token."), status_code=401)
    resp = RedirectResponse("/ui", status_code=303)
    auth.set_login_cookie(resp)
    return resp


@router.get("/logout")
def logout():
    resp = RedirectResponse("/ui/login", status_code=303)
    auth.clear_login_cookie(resp)
    return resp


# --- dashboard -------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, date: str | None = None, msg: str | None = None):
    if (r := _guard(request)):
        return r
    conn = _conn()
    date = date or webdata.latest_run_date(conn) or ""
    rows = webdata.dashboard(conn, date) if date else []
    return templates.TemplateResponse(
        request, "dashboard.html", _ctx(request, rows=rows, date=date, msg=msg))


@router.post("/add")
def add_stock_ui(request: Request, ticker: str = Form(...)):
    if (r := _guard(request)):
        return r
    from app.onboard import add_stock
    from app.users import register_user
    conn = _conn()
    uid = register_user(conn, "web-ui", "Web UI")  # UI-added stocks live under a web user
    try:
        res = add_stock(conn, uid, ticker)
        msg = f"Added {res.ticker_nse}." + (f" {res.warning}" if res.warning else "")
    except Exception as exc:
        msg = f"Could not add {ticker}: {exc}"
    return RedirectResponse(f"/ui?msg={msg}", status_code=303)


# --- stock detail ----------------------------------------------------------

@router.get("/stock/{stock_id}", response_class=HTMLResponse)
def stock_detail(request: Request, stock_id: int, date: str | None = None):
    if (r := _guard(request)):
        return r
    conn = _conn()
    date = date or webdata.latest_run_date(conn) or ""
    header = webdata.stock_header(conn, stock_id, date)
    if header is None:
        return HTMLResponse("Unknown stock", status_code=404)
    detail = webdata.attribution_detail(conn, stock_id, date)
    hist = webdata.history(conn, stock_id, HISTORY_DAYS)
    return templates.TemplateResponse(
        request, "stock.html", _ctx(request, header=header, detail=detail, history=hist, date=date))


@router.get("/stock/{stock_id}/profile", response_class=HTMLResponse)
def stock_profile(request: Request, stock_id: int):
    if (r := _guard(request)):
        return r
    conn = _conn()
    header = webdata.stock_header(conn, stock_id, webdata.latest_run_date(conn) or "")
    if header is None:
        return HTMLResponse("Unknown stock", status_code=404)
    edges = [e.to_json_dict() for e in effective_profile(conn, stock_id)]
    drafts = webdata.pending_drafts(conn, stock_id)
    return templates.TemplateResponse(
        request, "profile.html", _ctx(request, header=header, edges=edges, drafts=drafts,
                                       stock_id=stock_id))


@router.post("/exposure/{draft_id}/ratify")
def ui_ratify(request: Request, draft_id: int, stock_id: int = Form(...)):
    if (r := _guard(request)):
        return r
    from app.exposure.ratify import approve_draft
    approve_draft(_conn(), draft_id)
    return RedirectResponse(f"/ui/stock/{stock_id}/profile", status_code=303)


@router.post("/exposure/{draft_id}/reject")
def ui_reject(request: Request, draft_id: int, stock_id: int = Form(...)):
    if (r := _guard(request)):
        return r
    from app.exposure.ratify import reject_draft
    reject_draft(_conn(), draft_id)
    return RedirectResponse(f"/ui/stock/{stock_id}/profile", status_code=303)


# --- ops -------------------------------------------------------------------

@router.get("/ops", response_class=HTMLResponse)
def ops(request: Request):
    if (r := _guard(request)):
        return r
    conn = _conn()
    return templates.TemplateResponse(request, "ops.html", _ctx(
        request,
        runs=webdata.run_log(conn),
        strips=webdata.strip_metrics(conn),
        outcomes=webdata.outcomes_distribution(conn),
        alerts=webdata.alert_log(conn),
    ))


@router.post("/ops/run")
def ops_run(request: Request):
    if (r := _guard(request)):
        return r
    from app.jobs.eod import run_eod
    run_eod(_conn(), force=True)
    return RedirectResponse("/ui/ops", status_code=303)


@router.post("/ops/retry")
def ops_retry(request: Request):
    if (r := _guard(request)):
        return r
    from app.alerts.telegram import retry_failed
    retry_failed(_conn())
    return RedirectResponse("/ui/ops", status_code=303)
