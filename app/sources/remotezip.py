"""Read one member of a large remote zip using HTTP Range requests.

The national GTFS archive is hundreds of MB, but we only need stops.txt.
zipfile reads the central directory at the end of the archive and then the
member's own bytes, so wrapping HTTP ranges in a seekable file object means we
download a few MB instead of the whole thing.
"""
from __future__ import annotations

import io
import zipfile

import httpx


class RangeNotSupported(RuntimeError):
    pass


class HTTPRangeFile(io.RawIOBase):
    def __init__(self, client: httpx.Client, url: str):
        self.client = client
        self.url = url
        head = client.head(url, follow_redirects=True)
        head.raise_for_status()
        self.url = str(head.url)
        if head.headers.get("accept-ranges", "").lower() != "bytes":
            # Some servers support ranges without advertising it; probe one byte.
            probe = client.get(self.url, headers={"Range": "bytes=0-0"})
            if probe.status_code != 206:
                raise RangeNotSupported(f"{url} does not support HTTP Range requests")
        self.size = int(head.headers["content-length"])
        self.pos = 0
        self.requests = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        elif whence == io.SEEK_END:
            self.pos = self.size + offset
        self.pos = max(0, min(self.pos, self.size))
        return self.pos

    def readinto(self, b) -> int:
        if self.pos >= self.size or not len(b):
            return 0
        end = min(self.pos + len(b), self.size) - 1
        r = self.client.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        self.requests += 1
        if r.status_code != 206:
            raise RangeNotSupported(f"expected 206 Partial Content, got {r.status_code}")
        data = r.content
        n = len(data)
        b[:n] = data
        self.pos += n
        return n


def read_member(url: str, member: str, *, headers: dict | None = None, timeout: float = 60,
                transport: httpx.BaseTransport | None = None) -> bytes:
    """Return the uncompressed bytes of `member` from the zip at `url`."""
    with httpx.Client(headers=headers or {}, timeout=timeout, follow_redirects=True,
                      transport=transport) as client:
        raw = HTTPRangeFile(client, url)
        # A large buffer keeps the number of round trips low.
        buffered = io.BufferedReader(raw, buffer_size=4 * 1024 * 1024)
        with zipfile.ZipFile(buffered) as zf:
            name = next((n for n in zf.namelist() if n.rsplit("/", 1)[-1] == member), None)
            if not name:
                raise FileNotFoundError(f"{member} not found in {url}")
            return zf.read(name)
