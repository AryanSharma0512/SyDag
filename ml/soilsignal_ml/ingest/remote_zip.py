"""
Read members of a large remote zip without downloading it.

Zenodo serves byte ranges, so the zip's index and only the needed members are
fetched into memory. Nothing is written to disk.
"""

import io
import zipfile
from collections.abc import Iterator

import httpx2 as httpx

BLOCK = 8 * 1024 * 1024  # one range request per 8 MB block


class RangeFile(io.RawIOBase):
    """A seekable read-only file over HTTP range requests, with a one-block cache."""

    def __init__(self, url: str, client: httpx.Client) -> None:
        self.url = url
        self.client = client
        head = client.head(url)
        head.raise_for_status()
        self.size = int(head.headers["Content-Length"])
        self.pos = 0
        self.bytes_fetched = 0
        self._block_start = -1
        self._block = b""

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def _fetch(self, start: int, end: int) -> bytes:
        response = self.client.get(self.url, headers={"Range": f"bytes={start}-{end - 1}"})
        if response.status_code != 206:
            raise OSError(f"range request returned HTTP {response.status_code}")
        self.bytes_fetched += len(response.content)
        return response.content

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        end = self.pos + n
        if not (self._block_start <= self.pos and end <= self._block_start + len(self._block)):
            if n >= BLOCK:
                data = self._fetch(self.pos, end)
                self.pos = end
                return data
            self._block_start = self.pos
            self._block = self._fetch(self.pos, min(self.size, self.pos + BLOCK))
        offset = self.pos - self._block_start
        data = self._block[offset : offset + n]
        self.pos += len(data)
        return data

    def readinto(self, buffer) -> int:  # type: ignore[override]
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


class RemoteZip:
    def __init__(self, url: str, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(follow_redirects=True, timeout=120)
        self._file = RangeFile(url, self._client)
        self.zip = zipfile.ZipFile(self._file)

    @property
    def bytes_fetched(self) -> int:
        return self._file.bytes_fetched

    def names(self) -> list[str]:
        return self.zip.namelist()

    def read(self, name: str) -> bytes:
        return self.zip.read(name)

    def iter_members(self, names: list[str]) -> Iterator[tuple[str, bytes]]:
        """Yield (name, bytes) in archive order, so reads stream through the zip once."""
        infos = sorted((self.zip.getinfo(n) for n in names), key=lambda i: i.header_offset)
        for info in infos:
            yield info.filename, self.zip.read(info)
