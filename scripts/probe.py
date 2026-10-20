#!/usr/bin/env python3
"""Opt-in deployed API probe; never prints submitted or returned media URLs."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from curl_cffi import CurlOpt, requests

from app.parser.douyin.media import normalize_douyin_media_url
from app.parser.media import normalize_media_url
from app.parser.url_rules import is_public_address


def api_parse(api_url: str, api_key: str, share_url: str, legacy_xiaohongshu: bool = False) -> dict:
    path = "/api/v1/xiaohongshu/parse" if legacy_xiaohongshu else "/api/v1/parse"
    request = urllib.request.Request(
        api_url.rstrip("/") + path,
        data=json.dumps({"url": share_url, "refresh": True}).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return json.load(exc)
        except ValueError:
            return {"success": False, "error": {"code": "NON_JSON_RESPONSE"}}


def check_media(url: str, full_download: bool) -> dict:
    normalized_url = normalize_media_url(url) or normalize_douyin_media_url(url)
    if normalized_url is None:
        raise ValueError("API returned an unsupported media URL")
    host = urlsplit(normalized_url).hostname or ""
    infos = socket.getaddrinfo(
        host,
        443,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    addresses = tuple(dict.fromkeys(info[4][0] for info in infos))
    if not addresses or any(not is_public_address(address) for address in addresses):
        raise ValueError("media host did not resolve exclusively to public addresses")
    headers = {"Referer": "https://www.xiaohongshu.com/"} if host.endswith("xhscdn.com") else {}
    if not full_download:
        headers["Range"] = "bytes=0-1023"
    with requests.Session(
        impersonate="chrome136",
        trust_env=False,
        curl_options={CurlOpt.RESOLVE: [f"{host}:443:{','.join(addresses)}"]},
    ) as session:
        response = session.get(
            normalized_url,
            headers=headers,
            timeout=30,
            allow_redirects=False,
            stream=True,
        )
        downloaded = 0
        for chunk in response.iter_content(chunk_size=64 * 1024 if full_download else 1024):
            downloaded += len(chunk)
            if not full_download:
                break
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        response.close()
        return {
            "status": response.status_code,
            "content_type": content_type,
            "bytes_read": downloaded,
            "host": urlsplit(normalized_url).hostname,
        }


def representative_media(data: dict) -> list[tuple[str, str]]:
    images = data.get("images", [])
    videos = data.get("videos", [])
    candidates: list[tuple[str, str]] = []
    motions: list[tuple[str, str]] = []
    if isinstance(images, list):
        for item in images:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("url"), str):
                candidates.append(("image", item["url"]))
            live_video = item.get("live_video")
            if isinstance(live_video, dict) and isinstance(live_video.get("url"), str):
                motions.append(("live_video", live_video["url"]))
    if isinstance(videos, list):
        for item in videos:
            if isinstance(item, dict) and isinstance(item.get("url"), str):
                candidates.append(("video", item["url"]))
    cover = data.get("cover")
    if isinstance(cover, dict) and isinstance(cover.get("url"), str):
        candidates.append(("cover", cover["url"]))
    if motions:
        return candidates[:1] + motions[:1]
    return candidates[:2]


def redacted_summary(payload: dict, check_headers: bool, full_download: bool) -> dict:
    if not payload.get("success"):
        error = payload.get("error") or {}
        return {
            "success": False,
            "error_code": error.get("code"),
            "request_id": (payload.get("meta") or {}).get("request_id"),
        }
    data = payload["data"]
    images = data.get("images", [])
    live_photo_count = sum(
        1 for item in images if isinstance(item, dict) and isinstance(item.get("live_video"), dict)
    )
    result = {
        "success": True,
        "note_id": data.get("note_id"),
        "type": data.get("type"),
        "image_count": len(images),
        "live_photo_count": live_photo_count,
        "video_count": len(data.get("videos", [])),
        "has_cover": data.get("cover") is not None,
        "request_id": payload.get("meta", {}).get("request_id"),
    }
    if check_headers or full_download:
        result["media_checks"] = [
            {"kind": kind, **check_media(url, full_download)}
            for kind, url in representative_media(data)
        ]
        result["media_check_mode"] = "full_download" if full_download else "file_header"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe one or two authorized Xiaohongshu or Douyin URLs through the API"
    )
    parser.add_argument("url", nargs="+", help="one or two full share URLs")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--check-media-headers", action="store_true")
    parser.add_argument(
        "--legacy-xiaohongshu",
        action="store_true",
        help="send requests to the retained Xiaohongshu-only route",
    )
    parser.add_argument(
        "--full-download",
        action="store_true",
        help="download up to two returned media files completely",
    )
    args = parser.parse_args()
    if not 1 <= len(args.url) <= 2:
        parser.error("provide one or two URLs")
    api_key = os.getenv("XHS_API_KEY", "")
    if not api_key:
        parser.error("XHS_API_KEY must be set in the environment")
    summaries = []
    for share_url in args.url:
        try:
            payload = api_parse(
                args.api_url, api_key, share_url, legacy_xiaohongshu=args.legacy_xiaohongshu
            )
            summaries.append(
                redacted_summary(payload, args.check_media_headers, args.full_download)
            )
        except Exception as exc:
            summaries.append({"success": False, "error_code": type(exc).__name__})
    print(json.dumps({"results": summaries}, ensure_ascii=False, indent=2))
    return 0 if all(item.get("success") for item in summaries) else 1


if __name__ == "__main__":
    sys.exit(main())
