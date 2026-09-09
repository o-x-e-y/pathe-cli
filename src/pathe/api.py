"""Async client for the public www.pathe.nl JSON API.

No key, no signature, no session: every endpoint here is an unauthenticated
GET. Nothing in this module can order a seat or read an account -- the booking
endpoints are deliberately not wrapped.
"""

import asyncio

import httpx

from .cache import CATALOGUE_TTL, SHOWTIMES_TTL, Cache

BASE = "https://www.pathe.nl/api"

# The site is a SPA; the API rejects requests that do not look like a browser.
HEADERS = {
    "Accept": "application/json",
    "Accept-Language": "nl-NL,nl;q=0.9",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}

# Deliberately modest. A day's programme for four cinemas is a few dozen
# requests; there is no published rate limit, so this stays well inside what a
# browser would do on its own.
MAX_CONCURRENCY = 6


class PatheError(RuntimeError):
    pass


class PatheClient:
    def __init__(self, cache=None, concurrency=MAX_CONCURRENCY, timeout=20.0):
        self.cache = cache if cache is not None else Cache()
        self._sem = asyncio.Semaphore(concurrency)
        self._timeout = timeout
        self._client = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers=HEADERS,
            timeout=self._timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=MAX_CONCURRENCY),
        )
        return self

    async def __aexit__(self, *exc):
        await self._client.aclose()
        self._client = None

    async def _get(self, path, ttl, *, missing_ok=False):
        url = f"{BASE}{path}"
        hit = self.cache.get(url, ttl)
        if hit is not None:
            return hit
        async with self._sem:
            for attempt in range(3):
                try:
                    response = await self._client.get(url)
                except httpx.RequestError as exc:
                    if attempt == 2:
                        raise PatheError(f"{url}: {exc}") from exc
                    await asyncio.sleep(0.5 * 2**attempt)
                    continue
                if response.status_code == 404 and missing_ok:
                    # A film simply not playing that day at that cinema. Cached
                    # as empty so a wide date sweep does not re-ask every run.
                    self.cache.set(url, [])
                    return []
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                    await asyncio.sleep(0.5 * 2**attempt)
                    continue
                if response.status_code != 200:
                    raise PatheError(f"{url}: HTTP {response.status_code}")
                payload = response.json()
                self.cache.set(url, payload)
                return payload
        raise PatheError(f"{url}: exhausted retries")

    async def cinemas(self):
        return await self._get("/cinemas", CATALOGUE_TTL)

    async def shows(self):
        """The national catalogue: one object per title, with duration, genre,
        rating and coming-soon ordering. No showtimes."""
        return await self._get("/shows", CATALOGUE_TTL)

    async def show(self, slug):
        return await self._get(f"/show/{slug}", CATALOGUE_TTL)

    async def cinema_matrix(self, cinema):
        """Which titles play at `cinema` on which dates, ~10 months ahead.

        One request covers the entire horizon, and every cell already carries
        tags, versions and the kids flag -- so filtering happens here, and only
        the surviving cells cost a showtimes request.
        """
        return await self._get(f"/cinema/{cinema}/shows", CATALOGUE_TTL)

    async def showtimes(self, show, cinema, date):
        return await self._get(
            f"/show/{show}/showtimes/{cinema}/{date}",
            SHOWTIMES_TTL,
            missing_ok=True,
        )

    async def gather_showtimes(self, triples):
        """Fetch many (show, cinema, date) screenings concurrently.

        Returns a dict keyed by the triple. Failures are dropped rather than
        raised: one dead title should not lose a whole evening's programme.
        """
        async def one(triple):
            try:
                return triple, await self.showtimes(*triple)
            except PatheError:
                return triple, []

        results = await asyncio.gather(*(one(t) for t in triples))
        return dict(results)
