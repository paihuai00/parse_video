#!/usr/bin/env python3
"""Opt-in deployed API probe; never prints submitted or returned media URLs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from app.parser.media import normalize_media_url


def api_parse(api_url: str, api_key: str, share_url: str) -> dict:
    request = urllib.request.Request(
        api_url.rstrip("/") + "/api/v1/xiaohongshu/parse",
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
    normalized_url = normalize_media_url(url)
    if normalized_url is None:
        raise ValueError("API returned an unsupported media URL")
    headers = {"Referer": "https://www.xiaohongshu.com/"}
    if not full_download:
        headers["Range"] = "bytes=0-1023"
    request = urllib.request.Request(normalized_url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        downloaded = 0
        while True:
            chunk = response.read(64 * 1024 if full_download else 1024)
            if not chunk:
                break
            downloaded += len(chunk)
            if not full_download:
                break
        return {
            "status": response.status,
            "content_type": response.headers.get_content_type(),
            "bytes_read": downloaded,
            "host": urlsplit(normalized_url).hostname,
        }


def redacted_summary(payload: dict, check_headers: bool, full_download: bool) -> dict:
    if not payload.get("success"):
        error = payload.get("error") or {}
        return {
            "success": False,
            "error_code": error.get("code"),
            "request_id": (payload.get("meta") or {}).get("request_id"),
        }
    data = payload["data"]
    media = list(data.get("images", [])) + list(data.get("videos", []))
    if data.get("cover"):
        media.append(data["cover"])
    result = {
        "success": True,
        "note_id": data.get("note_id"),
        "type": data.get("type"),
        "image_count": len(data.get("images", [])),
        "video_count": len(data.get("videos", [])),
        "has_cover": data.get("cover") is not None,
        "request_id": payload.get("meta", {}).get("request_id"),
    }
    if check_headers or full_download:
        result["media_checks"] = [check_media(item["url"], full_download) for item in media[:2]]
        result["media_check_mode"] = "full_download" if full_download else "file_header"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe one or two authorized Xiaohongshu URLs through the deployed API"
    )
    parser.add_argument("url", nargs="+", help="one or two full share URLs")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--check-media-headers", action="store_true")
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
            payload = api_parse(args.api_url, api_key, share_url)
            summaries.append(
                redacted_summary(payload, args.check_media_headers, args.full_download)
            )
        except Exception as exc:
            summaries.append({"success": False, "error_code": type(exc).__name__})
    print(json.dumps({"results": summaries}, ensure_ascii=False, indent=2))
    return 0 if all(item.get("success") for item in summaries) else 1


if __name__ == "__main__":
    sys.exit(main())
