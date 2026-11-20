"""The HTTP client, against a mock transport -- never the network."""

import asyncio

import httpx

from pathe.api import PatheClient
from pathe.cache import Cache


def _client(tmp_path, status, body):
    client = PatheClient(cache=Cache(tmp_path))
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json=body))
    )
    return client


def test_an_unknown_show_slug_is_empty_rather_than_an_error(tmp_path):
    """Recorded live 2026-11-20: `/api/show/<unknown>` is a 404 whose body is a
    JSON string. `pathe info` must get an empty answer, not a traceback."""
    client = _client(tmp_path, 404, "Object Show with slug = zzzz-1 doesn't exist")
    assert asyncio.run(client.show("zzzz-1")) == []
