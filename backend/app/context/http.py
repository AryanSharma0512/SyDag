"""Outbound HTTP for the context services: one shared client and clear failure types."""

from functools import lru_cache
from typing import Any

import httpx2 as httpx

from app.config import get_settings

USER_AGENT = "SoilSignal/0.1 (IoT4Ag hackathon project)"


class UpstreamError(Exception):
    """An external data service failed, timed out or returned something unusable."""

    def __init__(self, service: str, detail: str) -> None:
        super().__init__(f"{service}: {detail}")
        self.service = service


class NotConfigured(Exception):
    """A data source needs configuration, such as an API key, that is not set."""


class NoData(Exception):
    """The source answered but has nothing for this location or date."""


@lru_cache
def get_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=get_settings().context_timeout_seconds,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def request_json(client: httpx.Client, service: str, method: str, url: str, **kwargs: Any) -> Any:
    try:
        response = client.request(method, url, **kwargs)
    except httpx.HTTPError as err:
        raise UpstreamError(service, f"request failed ({type(err).__name__})") from err
    if response.status_code in (401, 403):
        raise UpstreamError(service, "the API key was rejected")
    if response.status_code != 200:
        raise UpstreamError(service, f"HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as err:
        raise UpstreamError(service, "the response was not JSON") from err
