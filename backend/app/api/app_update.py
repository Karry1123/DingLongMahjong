"""Public APK release metadata, with a last-known-good cache."""
import json
import logging
import os
import re
import time
from functools import cmp_to_key
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/app", tags=["app"])
RELEASES_API = "https://api.github.com/repos/Karry1123/DingLongMahjong/releases?per_page=10"
RELEASES_PAGE = "https://github.com/Karry1123/DingLongMahjong/releases"
CACHE_SECONDS = 600
FAILURE_CACHE_SECONDS = 60
_cached = None
_cached_at = 0
_failed_at = None
_lock = Lock()
logger = logging.getLogger(__name__)


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


def fetch_releases(token=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "DingLongMahjong"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(RELEASES_API, headers=headers)
    with urlopen(request, timeout=8) as response:
        return json.load(response)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _warn_failure(source, error):
    logger.warning("%s failed (HTTP status %s): %s", source, getattr(error, "code", "N/A"), error)


def fetch_latest_redirect():
    request = Request(f"{RELEASES_PAGE}/latest", headers={"User-Agent": "DingLongMahjong"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=8):
            raise ValueError("GitHub latest did not redirect")
    except HTTPError as error:
        try:
            if error.code not in (301, 302, 303, 307, 308):
                raise
            location = error.headers.get("Location", "")
        finally:
            error.close()
    page = urlsplit(urljoin(request.full_url, location))
    prefix = "/Karry1123/DingLongMahjong/releases/tag/"
    tag = unquote(page.path[len(prefix):]) if page.path.startswith(prefix) else ""
    if (page.scheme != "https" or page.netloc != "github.com"
            or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", tag)):
        raise ValueError(f"Invalid GitHub latest Location: {location}")
    tag = quote(tag, safe="")
    url = f"{RELEASES_PAGE}/download/{tag}/DingLongMahjong-{tag}.apk"
    size = 0
    try:
        with urlopen(Request(url, headers={"User-Agent": "DingLongMahjong"}, method="HEAD"), timeout=8) as response:
            size = max(0, int(response.headers.get("Content-Length", 0)))
    except Exception as error:
        _warn_failure("GitHub APK HEAD", error)
    return dict(version=unquote(tag), url=url, size=size, notes="", page=f"{RELEASES_PAGE}/tag/{tag}")


def fetch_latest():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        try:
            return select_latest(fetch_releases(token))
        except Exception as error:
            _warn_failure("GitHub authenticated releases API", error)
    try:
        return fetch_latest_redirect()
    except Exception as error:
        _warn_failure("GitHub latest redirect", error)
    try:
        return select_latest(fetch_releases())
    except Exception as error:
        _warn_failure("GitHub unauthenticated releases API", error)
        raise


@router.get("/latest")
def latest():
    global _cached, _cached_at, _failed_at
    with _lock:
        if _cached is not None and time.monotonic() - _cached_at < CACHE_SECONDS:
            return _cached
        if _failed_at is not None and time.monotonic() - _failed_at < FAILURE_CACHE_SECONDS:
            if _cached is not None:
                return _cached
            raise HTTPException(status_code=503, detail="更新服务暂不可用，请稍后重试")
        try:
            info = fetch_latest()
        except Exception as error:
            _failed_at = time.monotonic()
            if _cached is not None:
                return _cached
            raise HTTPException(status_code=503, detail="更新服务暂不可用，请稍后重试") from error
        _cached, _cached_at = info, time.monotonic()
        _failed_at = None
        return info
