"""Public APK release metadata, with a last-known-good cache."""
import json
import re
import time
from functools import cmp_to_key
from threading import Lock
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/app", tags=["app"])
RELEASES_API = "https://api.github.com/repos/Karry1123/DingLongMahjong/releases?per_page=10"
CACHE_SECONDS = 600
_cached = None
_cached_at = 0
_lock = Lock()


def _version(text):
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", str(text or "").strip())
    return (*map(int, match.group(1, 2, 3)), match.group(4) or "") if match else None


def _compare(a, b):
    x, y = _version(a["version"]), _version(b["version"])
    if x[:3] != y[:3]:
        return (x[:3] > y[:3]) - (x[:3] < y[:3])
    if x[3] == y[3]:
        return 0
    if not x[3] or not y[3]:
        return 1 if not x[3] else -1
    left, right = x[3].split("."), y[3].split(".")
    for lpart, rpart in zip(left, right):
        if lpart == rpart:
            continue
        ln, rn = lpart.isdigit(), rpart.isdigit()
        if ln and rn:
            return (int(lpart) > int(rpart)) - (int(lpart) < int(rpart))
        if ln != rn:
            return -1 if ln else 1
        return 1 if lpart > rpart else -1
    return (len(left) > len(right)) - (len(left) < len(right))


def select_latest(releases):
    if not isinstance(releases, list):
        raise ValueError("Invalid GitHub release list")
    candidates = []
    for release in releases:
        if release.get("draft"):
            continue
        version = release.get("tag_name") or release.get("name") or ""
        asset = next((a for a in release.get("assets", [])
                      if a.get("name", "").lower().endswith(".apk") and a.get("browser_download_url")), None)
        if _version(version) and asset:
            candidates.append(dict(version=version, url=asset["browser_download_url"],
                                   size=asset.get("size") or 0, notes=release.get("body") or "",
                                   page=release.get("html_url") or ""))
    if not candidates:
        raise ValueError("No installable APK release")
    return max(candidates, key=cmp_to_key(_compare))


def fetch_releases():
    request = Request(RELEASES_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "DingLongMahjong"})
    with urlopen(request, timeout=8) as response:
        return json.load(response)


@router.get("/latest")
def latest():
    global _cached, _cached_at
    with _lock:
        if _cached is not None and time.monotonic() - _cached_at < CACHE_SECONDS:
            return _cached
        try:
            info = select_latest(fetch_releases())
        except Exception as error:
            if _cached is not None:
                return _cached
            raise HTTPException(status_code=503, detail="更新服务暂不可用，请稍后重试") from error
        _cached, _cached_at = info, time.monotonic()
        return info
