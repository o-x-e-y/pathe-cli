"""Disk cache: TTL, atomicity, and tolerance of a corrupt entry."""

import os
import time

from pathe.cache import CATALOGUE_TTL, SHOWTIMES_TTL, Cache


def test_roundtrip(tmp_path):
    cache = Cache(tmp_path)
    cache.set("http://x/1", {"a": 1})
    assert cache.get("http://x/1", 60) == {"a": 1}


def test_miss_is_none(tmp_path):
    assert Cache(tmp_path).get("http://x/absent", 60) is None


def test_expiry(tmp_path):
    cache = Cache(tmp_path)
    cache.set("http://x/2", {"a": 1})
    path = cache._path("http://x/2")
    old = time.time() - 120
    os.utime(path, (old, old))
    assert cache.get("http://x/2", 60) is None      # older than the TTL
    assert cache.get("http://x/2", 300) == {"a": 1}  # still inside a longer one


def test_catalogue_outlives_showtimes(tmp_path):
    """The two tiers exist because the data ages differently; if the constants
    ever converge the design intent is gone."""
    assert CATALOGUE_TTL > SHOWTIMES_TTL


def test_corrupt_entry_reads_as_miss(tmp_path):
    cache = Cache(tmp_path)
    cache.set("http://x/3", {"a": 1})
    cache._path("http://x/3").write_text("{not json")
    assert cache.get("http://x/3", 60) is None


def test_distinct_urls_do_not_collide(tmp_path):
    cache = Cache(tmp_path)
    cache.set("http://x/a", {"v": "a"})
    cache.set("http://x/b", {"v": "b"})
    assert cache.get("http://x/a", 60) == {"v": "a"}
    assert cache.get("http://x/b", 60) == {"v": "b"}


def test_disabled_cache_stores_nothing(tmp_path):
    cache = Cache(tmp_path, enabled=False)
    cache.set("http://x/4", {"a": 1})
    assert cache.get("http://x/4", 60) is None


def test_empty_list_is_cached_not_treated_as_miss(tmp_path):
    """A film not playing that day returns []. That must cache, or a wide date
    sweep re-asks for every empty day on every run."""
    cache = Cache(tmp_path)
    cache.set("http://x/5", [])
    assert cache.get("http://x/5", 60) == []


def test_clear_removes_entries(tmp_path):
    cache = Cache(tmp_path)
    cache.set("http://x/6", {"a": 1})
    cache.set("http://x/7", {"a": 2})
    assert cache.clear() == 2
    assert cache.get("http://x/6", 60) is None


def test_set_leaves_no_temp_files(tmp_path):
    cache = Cache(tmp_path)
    cache.set("http://x/8", {"a": 1})
    assert list(tmp_path.glob("*.tmp")) == []


def test_unwritable_home_disables_caching_instead_of_crashing(tmp_path, monkeypatch):
    """A build sandbox sets HOME to an unwritable path. Caching is an
    optimisation, so the tool must still run -- it just stops caching."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "nope" / "deeper"))
    (tmp_path / "nope").mkdir()
    (tmp_path / "nope").chmod(0o500)
    try:
        cache = Cache()
        assert cache.enabled is False
        cache.set("http://x/9", {"a": 1})           # must not raise
        assert cache.get("http://x/9", 60) is None
        assert cache.clear() == 0                    # must not raise either
    finally:
        (tmp_path / "nope").chmod(0o700)
