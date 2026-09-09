"""On-disk response cache.

Two tiers, because the two kinds of data age at very different rates. The
catalogue and the cinema matrices are near-static -- Pathé publishes weeks
ahead and edits rarely -- while showtimes for today go stale as screenings sell
out. Caching them under one TTL would either hammer the API or serve bad
availability.
"""

import hashlib
import json
import os
import time
from pathlib import Path

CATALOGUE_TTL = 6 * 3600  # /api/cinemas, /api/shows, /api/cinema/*/shows
SHOWTIMES_TTL = 30 * 60  # /api/show/*/showtimes/*/*


def cache_dir():
    root = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(root) / "pathe"


class Cache:
    def __init__(self, directory=None, enabled=True):
        self.dir = Path(directory) if directory else cache_dir()
        self.enabled = enabled
        if self.enabled:
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                # Read-only or absent HOME -- a build sandbox, a locked-down
                # container. Caching is an optimisation, never a requirement,
                # so run without it rather than refusing to start.
                self.enabled = False

    def _path(self, url):
        return self.dir / (hashlib.sha256(url.encode()).hexdigest()[:32] + ".json")

    def get(self, url, ttl):
        if not self.enabled:
            return None
        path = self._path(url)
        try:
            if time.time() - path.stat().st_mtime > ttl:
                return None
            with path.open() as handle:
                return json.load(handle)
        except (OSError, ValueError):
            # A truncated or unreadable entry is just a miss; the caller refetches.
            return None

    def set(self, url, payload):
        if not self.enabled:
            return
        path = self._path(url)
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w") as handle:
                json.dump(payload, handle)
            # Atomic, so a killed process can never leave a half-written entry
            # that later reads as valid JSON.
            tmp.replace(path)
        except OSError:
            pass

    def clear(self):
        removed = 0
        if self.dir.exists():
            for entry in self.dir.glob("*.json"):
                entry.unlink()
                removed += 1
        return removed
