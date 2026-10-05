"""Edge Impulse Studio REST API client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests

from .config import Settings, require_api_key


class EdgeImpulseError(RuntimeError):
    pass


@dataclass(frozen=True)
class Sample:
    id: int
    filename: str
    label: str
    category: str
    total_length_ms: int


def _retry_get(session: requests.Session, url: str, headers: dict[str, str], attempts: int = 3) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            resp = session.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success", True):
                raise EdgeImpulseError(str(data.get("error", data)))
            return data
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(2**attempt)
    raise EdgeImpulseError(f"GET {url} failed after {attempts} attempts: {last_exc}")


class EdgeImpulseClient:
    def __init__(self, settings: Settings, retries: int = 3) -> None:
        self.settings = settings
        self.retries = retries
        self._session = requests.Session()
        self._headers = {"x-api-key": require_api_key(settings)}

    def info(self) -> dict[str, Any]:
        return _retry_get(self._session, self.settings.base_url, self._headers, self.retries)

    def list_samples(self, category: str) -> list[Sample]:
        data = _retry_get(
            self._session,
            f"{self.settings.base_url}/raw-data?category={category}",
            self._headers,
            self.retries,
        )
        return [
            Sample(
                id=int(s["id"]),
                filename=s.get("filename", "?"),
                label=s.get("label") or "?",
                category=category,
                total_length_ms=int(s.get("totalLengthMs") or 0),
            )
            for s in data.get("samples", [])
        ]

    def iter_all_samples(self) -> Iterator[Sample]:
        for category in ("training", "testing"):
            yield from self.list_samples(category)

    def fetch_sample_values(self, sample_id: int) -> tuple[list[int], int]:
        data = _retry_get(
            self._session,
            f"{self.settings.base_url}/raw-data/{sample_id}",
            self._headers,
            self.retries,
        )
        payload = data.get("payload", {})
        values = payload.get("values", [])
        freq = int(payload.get("frequencyHz") or 16000)
        flat: list[int] = []
        for v in values:
            flat.append(int(v[0]) if isinstance(v, list) else int(v))
        return flat, freq

    def delete_sample(self, sample_id: int) -> None:
        resp = self._session.delete(
            f"{self.settings.base_url}/raw-data/{sample_id}",
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            return
        if not data.get("success", True):
            raise EdgeImpulseError(str(data.get("error", data)))
