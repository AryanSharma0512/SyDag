"""
Mirror a Google Drive folder to local disk through the Drive API (v3).

The challenge data is shared as a Drive folder. This walks it recursively, writes every
file under the same relative path, and records Drive's own id, size and MD5 for each one
in `drive_listing.json`, so the local copy can be checked against the source and a rerun
only fetches what is missing or changed.

    GDRIVE_TOKEN=<OAuth access token, drive.readonly> \\
    uv run --project ../backend --group ml python -m soilsignal_ml.ingest.gdrive \\
        <folder id or URL> data/raw/sydag26

The token is read from the environment and never written to disk.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx2 as httpx

API = "https://www.googleapis.com/drive/v3/files"
FOLDER = "application/vnd.google-apps.folder"
SHORTCUT = "application/vnd.google-apps.shortcut"
EXPORTS = {
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
}
FIELDS = "nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime,shortcutDetails)"
LISTING = "drive_listing.json"


def folder_id(value: str) -> str:
    match = re.search(r"/folders/([\w-]+)", value) or re.search(r"[?&]id=([\w-]+)", value)
    return match[1] if match else value


class Drive:
    def __init__(self, token: str) -> None:
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"}, timeout=120, follow_redirects=True
        )

    def _get(self, url: str, **params) -> httpx.Response:
        for attempt in range(5):
            response = self.client.get(url, params=params)
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(2**attempt)
                continue
            if response.status_code == 401:
                raise SystemExit("Drive rejected the token (expired or wrong scope)")
            response.raise_for_status()
            return response
        response.raise_for_status()
        return response

    def children(self, parent: str) -> list[dict]:
        out, page = [], None
        while True:
            params = {
                "q": f"'{parent}' in parents and trashed = false",
                "fields": FIELDS,
                "pageSize": 1000,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page:
                params["pageToken"] = page
            body = self._get(API, **params).json()
            out.extend(body.get("files", []))
            page = body.get("nextPageToken")
            if not page:
                return out

    def walk(self, root: str, prefix: str = "") -> list[dict]:
        files = []
        for item in sorted(self.children(root), key=lambda f: f["name"]):
            if item["mimeType"] == SHORTCUT:
                details = item.get("shortcutDetails", {})
                item = {
                    **item,
                    "id": details.get("targetId"),
                    "mimeType": details.get("targetMimeType", ""),
                }
            path = f"{prefix}{item['name']}"
            if item["mimeType"] == FOLDER:
                files.extend(self.walk(item["id"], path + "/"))
            else:
                files.append({**item, "path": path})
        return files

    def download(self, item: dict, target: Path) -> None:
        if item["mimeType"] in EXPORTS:
            mime, _ = EXPORTS[item["mimeType"]]
            url, params = f"{API}/{item['id']}/export", {"mimeType": mime}
        else:
            url, params = f"{API}/{item['id']}", {"alt": "media", "supportsAllDrives": "true"}
        data = self._get(url, **params).content
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)


def local_path(out: Path, item: dict) -> Path:
    suffix = EXPORTS.get(item["mimeType"], (None, ""))[1]
    return out / (item["path"] + suffix)


def is_current(path: Path, item: dict) -> bool:
    if not path.exists():
        return False
    if item.get("md5Checksum"):
        return hashlib.md5(path.read_bytes()).hexdigest() == item["md5Checksum"]
    return item["mimeType"] in EXPORTS


def mirror(folder: str, out: Path, workers: int = 8) -> dict:
    token = os.environ.get("GDRIVE_TOKEN")
    if not token:
        raise SystemExit("set GDRIVE_TOKEN to an OAuth access token with drive.readonly")
    drive = Drive(token)
    root = folder_id(folder)
    files = drive.walk(root)
    out.mkdir(parents=True, exist_ok=True)
    listing = {
        "folder_id": root,
        "retrieved": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": files,
    }
    (out / LISTING).write_text(json.dumps(listing, indent=1) + "\n")
    todo = [f for f in files if not is_current(local_path(out, f), f)]
    print(
        f"{len(files)} files listed, {len(files) - len(todo)} already local, fetching {len(todo)}",
        flush=True,
    )
    failed = []
    with ThreadPoolExecutor(workers) as pool:
        jobs = {pool.submit(drive.download, f, local_path(out, f)): f for f in todo}
        for i, job in enumerate(as_completed(jobs), 1):
            try:
                job.result()
            except Exception as error:
                failed.append({"path": jobs[job]["path"], "error": str(error)})
            if i % 250 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}", flush=True)
    bad = [f["path"] for f in files if not is_current(local_path(out, f), f)]
    print(f"done: {len(files) - len(bad)}/{len(files)} verified", flush=True)
    return {"listed": len(files), "failed": failed, "unverified": bad}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", help="Drive folder id or URL")
    parser.add_argument("out", type=Path)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    result = mirror(args.folder, args.out, args.workers)
    for f in result["failed"]:
        print(f"failed: {f['path']}: {f['error']}")
    return 1 if result["unverified"] else 0


if __name__ == "__main__":
    sys.exit(main())
