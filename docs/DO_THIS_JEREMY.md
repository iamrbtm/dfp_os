# DO_THIS_JEREMY — Trend Scout Source Fixes

## Status

| Source | Status | Items/Run | Notes |
|--------|--------|-----------|-------|
| MyMiniFactory | ✅ Fixed | 1600 | Uses `/api/search` internal endpoint |
| Printables | ✅ Fixed | 1600 | Uses search page scraping with `article.card` selectors |
| Reddit | ✅ Fixed | ~75 | RSS feeds via curl (bypasses TLS fingerprinting) |
| BGG | 🔄 Pending | 0 | Waiting for BGG app approval + token |
| Etsy | 🔄 Pending | 0 | Needs ETSY_API_KEY from user |
| Makerworld | ❌ Research | 0 | Cloudflare + unknown API |

---

## 1. MyMiniFactory ✅ FIXED

Rewrote to use `https://www.myminifactory.com/api/search` (internal unauthenticated
endpoint) instead of `/api/v2/search` which requires OAuth2.

Response has `objectResults` array with all model data (name, url, thumbnail, likes, price).

---

## 2. Printables ✅ FIXED

Rewrote to scrape `https://www.printables.com/search/models?q=<query>` using
`article.card` CSS selectors matching the Svelte HTML structure.

---

## 3. Reddit ✅ FIXED

Reddit blocks Python `requests` library via TLS fingerprinting (JA3). All Python
HTTP clients return 429 regardless of headers.

**Fix**: Use `curl` via subprocess to fetch RSS feeds:
```
https://www.reddit.com/r/{subreddit}/.rss
```

Subreddits: 3Dprinting, functionalprint, Gridfinity, BambuLab (25 items each).
Reddit has aggressive per-IP rate limits — expect 2-3 subreddits to succeed per run.

---

## 4. Etsy — Needs ETSY_API_KEY

Code already handles missing key gracefully (returns "not_configured" result).

**To enable**:
1. Go to https://developers.etsy.com/
2. Register an app to get an API key
3. Add `ETSY_API_KEY=<your-key>` to `.env`

---

## 5. BGG — Needs BGG_API_TOKEN

Code already handles missing token gracefully. When token is provided, sends
`Authorization: Bearer <token>` header with every request.

**To enable**:
1. Wait for BGG app approval at https://boardgamegeek.com/applications
2. Create a token at https://boardgamegeek.com/applications → Tokens
3. Add `BGG_API_TOKEN=<your-token>` to `.env`

---

## 6. Makerworld — Needs investigation

**Problems**:
- `/api/v1/models` returns 404 (wrong endpoint)
- All pages behind Cloudflare (HTTP 403 "Just a moment...")
- Python `requests` blocked by TLS fingerprinting
- Maybe we can pull modelss via makerworld similar to what we are doing

**To investigate**:
1. Load https://makerworld.com/en/models in a browser
2. Open DevTools → Network tab
3. Look for XHR/fetch requests to API endpoints
4. Common patterns to try: `/api/v2/models`, `/api/graphql`, `/api/models/search`
5. If API found but blocked by Cloudflare → try `cloudscraper` (already in pyproject.toml) or `curl_cffi`
6. If no API found → scrape search page HTML using curl subprocess (like Reddit)

---

## Verification

```bash
uv run flask --app app:create_app shell
```

Then test any source:
```python
from app.services.ai.trend_scout.sources._base import RateLimiter
from app.services.ai.trend_scout.sources.<source> import fetch_<func>
import requests

limiter = RateLimiter()
with requests.Session() as session:
    results = fetch_<func>(session, limiter)
    for r in results:
        print(f"{r.keyword_or_category:30s} items={len(r.items):3d}  errors={r.errors}")
    print(f"Total items: {sum(len(r.items) for r in results)}")
```

Full pipeline:
```python
from app.services.ai.trend_scout import run_full_pipeline
result = run_full_pipeline()
print(f"Snapshots: {result['total_snapshots']}")
print(f"Errors: {len(result.get('failed_sources', []))}")
```
