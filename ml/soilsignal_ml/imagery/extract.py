"""
Batch extraction with a resumable cache.

Each image's statistics are cached under the SHA-1 of its bytes plus the extractor
version, in an append-only JSON-lines file that is flushed after every image:

  - an interrupted run resumes where it stopped (rerun the same command);
  - an image whose bytes change is re-extracted, however it was edited or copied;
  - renaming or moving files costs nothing (paths are matched to hashes on each run);
  - identical files under two paths are one cache entry and a duplicate flag.

Workers decode in separate processes; only the parent writes the cache.
"""

import hashlib
import json
import os
import time
from collections.abc import Callable
from multiprocessing import get_context
from pathlib import Path

import pandas as pd

from soilsignal_ml.imagery.satellite import DEFAULT_BANDS, EXTRACTOR_VERSION, image_stats

Progress = Callable[[str], None]
_CACHED: frozenset[str] = frozenset()
_OPTIONS: dict = {}


def _init(cached: frozenset[str], options: dict) -> None:
    global _CACHED, _OPTIONS
    _CACHED, _OPTIONS = cached, options


def _work(path: str) -> tuple[str, str, dict | None, float]:
    """(path, sha1, stats or None when already cached, seconds spent decoding)."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return path, f"unreadable:{path}", {"error": f"OSError: {exc}"}, 0.0
    sha1 = hashlib.sha1(data).hexdigest()
    if sha1 in _CACHED:
        return path, sha1, None, 0.0
    t0 = time.perf_counter()
    stats = _OPTIONS["fn"](data, **_OPTIONS.get("kwargs", {}))
    return path, sha1, stats, time.perf_counter() - t0


class StatsCache:
    """sha1 -> stats for one extractor version, persisted as JSON lines."""

    def __init__(self, path: Path, version: str) -> None:
        self.path = Path(path)
        self.version = version
        self.entries: dict[str, dict] = {}
        if self.path.exists():
            with self.path.open() as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # a line cut short by an interrupted run
                    if rec.get("version") == version:
                        self.entries[rec["sha1"]] = rec["stats"]

    def add(self, sha1: str, stats: dict, handle) -> None:
        self.entries[sha1] = stats
        handle.write(json.dumps({"sha1": sha1, "version": self.version, "stats": stats}) + "\n")
        handle.flush()


def extract_images(
    images: pd.DataFrame,
    root: Path,
    cache_path: Path,
    *,
    fn: Callable[..., dict] = image_stats,
    version: str = EXTRACTOR_VERSION,
    kwargs: dict | None = None,
    workers: int | None = None,
    retry_errors: bool = False,
    progress: Progress = print,
) -> tuple[pd.DataFrame, dict]:
    """Statistics for every row of `images` (paths relative to root), joined on.

    Returns the image table with a `sha1` column and one column per statistic, and a
    timing summary for the benchmark report."""
    root = Path(root)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = StatsCache(cache_path, version)
    cached = {k for k, v in cache.entries.items() if not (retry_errors and v.get("error"))}
    paths = [str(root / p) for p in images["path"]]
    workers = max(1, workers or os.cpu_count() or 1)
    started = time.perf_counter()
    decode_seconds, n_new, n_cached = 0.0, 0, 0
    by_path: dict[str, str] = {}
    progress(f"{len(paths)} images, {len(cached)} cached results, {workers} worker(s)")
    options = {"fn": fn, "kwargs": kwargs or {}}
    with cache_path.open("a") as handle:
        if workers == 1:
            _init(frozenset(cached), options)
            results = map(_work, paths)
            pool = None
        else:
            pool = get_context().Pool(
                workers, initializer=_init, initargs=(frozenset(cached), options)
            )
            results = pool.imap_unordered(_work, paths, chunksize=8)
        try:
            for i, (path, sha1, stats, seconds) in enumerate(results, 1):
                by_path[path] = sha1
                if stats is None:
                    n_cached += 1
                else:
                    cache.add(sha1, stats, handle)
                    decode_seconds += seconds
                    n_new += 1
                if i % 500 == 0 or i == len(paths):
                    rate = i / max(time.perf_counter() - started, 1e-9)
                    progress(f"  {i}/{len(paths)} ({n_new} extracted, {rate:.0f} images/s)")
        finally:
            if pool is not None:
                pool.close()
                pool.join()
    wall = time.perf_counter() - started

    out = images.copy()
    out["sha1"] = [by_path[p] for p in paths]
    stats = pd.DataFrame([cache.entries.get(s, {"error": "missing"}) for s in out["sha1"]])
    stats.index = out.index
    out = pd.concat([out, stats.drop(columns=[c for c in stats if c in out])], axis=1)
    timing = {
        "images": len(paths),
        "extracted": n_new,
        "from_cache": n_cached,
        "workers": workers,
        "wall_seconds": wall,
        "decode_seconds": decode_seconds,
        "bytes": int(sum(os.path.getsize(p) for p in paths if os.path.exists(p))),
    }
    return out, timing


def satellite_kwargs(band_order: tuple[str, ...] | None, scale: float | None) -> dict:
    return {"band_order": tuple(band_order or DEFAULT_BANDS), "reflectance_scale": scale}
