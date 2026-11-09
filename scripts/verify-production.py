"""Verify the deployed API through the frontend origin. Uses one synthetic test account."""
import http.cookiejar
import json
import secrets
import time
import urllib.error
import urllib.request

BASE = "https://moneyfest-beta.vercel.app"

def request(client, path, method="GET", body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    hdr = {"Accept": "application/json", **(headers or {})}
    if data is not None:
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + "/api/v1" + path, data=data, headers=hdr, method=method)
    try:
        res = client.open(req, timeout=30)
    except urllib.error.HTTPError as err:
        res = err
    with res:
        raw = res.read()
        content_type = res.headers.get("Content-Type", "")
        result = json.loads(raw) if "application/json" in content_type else None
        return res.status, result

def client():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

browser = client()
deadline = time.monotonic() + 900
print("Waiting for production API readiness through Vercel...", flush=True)
while True:
    try:
        code, health = request(browser, "/health")
        if code == 200 and health and health.get("status") == "ok" and health.get("backend") == "java":
            break
    except (urllib.error.URLError, TimeoutError):
        pass
    if time.monotonic() > deadline:
        raise RuntimeError("Production API did not become healthy through Vercel within 15 minutes")
    time.sleep(10)
print("PASS: Java API and database health through Vercel", flush=True)
assert request(browser, "/auth/me")[0] == 401
profile = {"email": "deployment-check-" + secrets.token_hex(8) + "@example.invalid",
           "password": secrets.token_urlsafe(24), "displayName": "Deployment check"}
assert request(browser, "/auth/register", "POST", profile)[0] == 403
print("PASS: unauthenticated access and CSRF enforcement", flush=True)

def mutate(path, method, body=None):
    code, csrf = request(browser, "/auth/csrf")
    assert code == 200 and csrf.get("token") and csrf.get("headerName")
    return request(browser, path, method, body, {csrf["headerName"]: csrf["token"]})

code, user = mutate("/auth/register", "POST", profile)
assert code == 201 and user.get("id"), "Registration failed"
identity = user["id"]
assert request(browser, "/auth/me")[1]["id"] == identity
code, portfolio = request(browser, "/me/portfolio?currency=INR")
assert code == 200 and portfolio["positions"] == []
prefs = {"alert_level": "HIGH_ONLY", "quiet_market": True, "daily_digest": False}
assert mutate("/me/preferences", "PUT", prefs)[0] == 200
assert request(browser, "/me/preferences")[1]["alert_level"] == "HIGH_ONLY"
print("PASS: registration, secure session, portfolio read and persisted preferences", flush=True)
assert mutate("/auth/logout", "POST")[0] == 200
assert request(browser, "/auth/me")[0] == 401
assert mutate("/auth/login", "POST", {"email": profile["email"], "password": profile["password"]})[0] == 200
assert request(browser, "/auth/me")[1]["id"] == identity
assert request(browser, "/me/preferences")[1]["alert_level"] == "HIGH_ONLY"
assert request(client(), "/auth/me")[0] == 401
assert mutate("/auth/logout", "POST")[0] == 200
print("PASS: logout, login, persisted data and independent-session isolation", flush=True)
print("Production smoke checks passed. One synthetic Deployment check account was retained; no personal data was used.", flush=True)
