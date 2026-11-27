"""Synthetic media fixtures only; never fetch real providers/CDNs."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpcore
import pytest
from fastapi.testclient import TestClient

from app.api.media_routes import MediaResponse, MediaService
from app.config import Settings
from app.errors import AppError
from app.main import create_app
from app.models import InternalCover, InternalImage, InternalNote, InternalVideo
from app.services.media_policy import validate_media_url
from app.services.media_tickets import MediaTickets
from app.services.parse_service import ServiceResult

IMAGE = "https://p26-sign.douyinpic.com/image.webp?x=one%2Btwo+z&x=2"
VIDEO = "https://v11-weba.douyinvod.com/motion.mp4?sig=secret"
PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic image bytes"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"synthetic video bytes"


def settings(**changes):
    return replace(
        Settings(
            api_key="test",
            environment="test",
            media_publication_enabled=True,
            media_public_origin="https://media.example",
            media_signing_key="s" * 32,
        ),
        **changes,
    )


def note():
    motion = InternalVideo(VIDEO, None, None, None, None, None, None)
    return InternalNote(
        None, "synthetic", "image", (InternalImage(IMAGE, None, None, 1, motion),), (), None
    )


def resolve(tickets, url):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    return tickets.resolve(parts.path.rsplit("/", 1)[-1], query["exp"][0], query["sig"][0])


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.closed = 0
        self.reads = 0

    @asynccontextmanager
    async def stream(self, method, url, headers=None):
        self.calls.append((method, url, headers))
        status, values, chunks = self.responses.pop(0)

        async def body():
            for chunk in chunks:
                self.reads += 1
                if isinstance(chunk, Exception):
                    raise chunk
                yield chunk

        try:
            yield httpcore.Response(status, headers=values, content=body())
        finally:
            self.closed += 1


def response(body=PNG, content_type=b"image/png", status=200, extra=()):
    return (
        status,
        [(b"content-type", content_type), (b"content-length", str(len(body)).encode()), *extra],
        [body],
    )


def client_with(http, **changes):
    config = settings(**changes)
    app = create_app(config)
    app.state.media_service = MediaService(config, http)
    publication = app.state.media_tickets.publish(note(), "douyin")
    return TestClient(app), app, publication


def test_publication_raw_cache_unchanged_fresh_atomic_and_reusable():
    tickets = MediaTickets(settings())
    original = note()
    first = tickets.publish(original, "douyin")
    second = tickets.publish(original, "douyin")
    assert original.images[0].url == IMAGE
    assert first.note.images[0].url != second.note.images[0].url
    assert resolve(tickets, first.note.images[0].url).url == IMAGE
    assert resolve(tickets, first.note.images[0].url).url == IMAGE
    assert resolve(tickets, first.note.images[0].live_video.url).url == VIDEO
    assert first.expires_at is not None


def test_capacity_never_evicts_live_records_and_batch_is_atomic():
    tickets = MediaTickets(settings(media_ticket_max_entries=3))
    first = tickets.publish(note(), "douyin")
    records = tickets.records.copy()
    size = tickets.bytes
    with pytest.raises(AppError, match="MEDIA_TICKET_CAPACITY"):
        tickets.publish(note(), "douyin")
    assert tickets.records == records and tickets.bytes == size
    assert resolve(tickets, first.note.images[0].url).url == IMAGE
    tickets.revoke(first.resource_ids)
    assert tickets.bytes == 0


def test_byte_capacity_and_invalid_last_slot_leave_no_partial_records():
    tickets = MediaTickets(settings(media_ticket_max_bytes=1))
    with pytest.raises(AppError):
        tickets.publish(note(), "douyin")
    assert not tickets.records and tickets.bytes == 0
    tickets = MediaTickets(settings())
    invalid = replace(
        note(), images=(*note().images, InternalImage("https://evil.test/a", None, None, 2))
    )
    with pytest.raises(AppError):
        tickets.publish(invalid, "douyin")
    assert not tickets.records


def test_expired_records_are_reclaimed_restart_and_bad_signatures():
    clock = [1000.0]
    tickets = MediaTickets(settings(media_ticket_ttl_seconds=1), lambda: clock[0])
    published = tickets.publish(note(), "douyin")
    url = published.note.images[0].url
    parts = urlsplit(url)
    exp = parse_qs(parts.query)["exp"][0]
    rid = parts.path.rsplit("/", 1)[-1]
    for signature in ["坏" * 64, "a" * 63, "g" * 64, "a" * 64]:
        with pytest.raises(AppError) as caught:
            tickets.resolve(rid, exp, signature)
        assert caught.value.status_code == 403
    with pytest.raises(AppError, match="MEDIA_TICKET_GONE"):
        resolve(MediaTickets(settings(), lambda: clock[0]), url)
    clock[0] += 2
    with pytest.raises(AppError, match="MEDIA_TICKET_EXPIRED"):
        resolve(tickets, url)
    tickets.publish(note(), "douyin")
    assert len(tickets.records) == 2


@pytest.mark.parametrize(
    "url,platform,kind",
    [
        ("https://p26-sign.douyinpic.com/a", "douyin", "image"),
        ("https://sns-web-i10.rednotecdn.com/a", "xiaohongshu", "image"),
        ("https://sns-v28.rednotecdn.com/a", "xiaohongshu", "video"),
        ("https://i0.hdslb.com/bfs/archive/a.jpg", "bilibili", "image"),
        ("https://upos-sz-mirrorcos.bilivideo.com/a", "bilibili", "video"),
    ],
)
def test_separate_media_namespaces(url, platform, kind):
    validate_media_url(url, platform, kind)


@pytest.mark.parametrize(
    "url",
    [
        "https://p26-sign.douyinpic.com.evil.test/a",
        "https://127.0.0.1/a",
        "https://user@p26-sign.douyinpic.com/a",
        "https://p26-sign.douyinpic.com:444/a",
        "https://p26-sign.douyinpic.com/a#fragment",
        "https://p26-sign.douyinpic.com./a",
    ],
)
def test_media_rejects_unsafe_urls(url):
    with pytest.raises(AppError):
        validate_media_url(url, "douyin", "image")


def test_complete_get_ignores_range_and_head_has_no_body_or_made_up_length():
    http = FakeHTTP([response(), (200, [(b"content-type", b"image/png")], [])])
    client, app, publication = client_with(http)
    url = publication.note.images[0].url
    result = client.get(url, headers={"Range": "bytes=0-2"})
    assert result.status_code == 200 and result.content == PNG
    assert result.headers["content-type"] == "image/png"
    assert result.headers["content-length"] == str(len(PNG))
    assert not any(key.lower() == b"range" for key, value in http.calls[0][2])
    result = client.head(url)
    assert result.status_code == 200 and not result.content
    assert "content-length" not in result.headers
    assert http.closed == 2 and app.state.media_service.admission.active == 0


@pytest.mark.parametrize(
    "upstream,code,status",
    [
        (
            response(body=b"<html>challenge</html>", content_type=b"text/html"),
            "MEDIA_UPSTREAM_BAD_RESPONSE",
            502,
        ),
        (
            response(body=b"<html>challenge</html>", content_type=b"image/png"),
            "MEDIA_UPSTREAM_BAD_RESPONSE",
            502,
        ),
        (response(status=206), "MEDIA_UPSTREAM_BAD_RESPONSE", 502),
        (response(status=403), "MEDIA_UPSTREAM_REJECTED", 502),
        (response(status=429), "MEDIA_RATE_LIMITED", 429),
        (response(extra=[(b"content-encoding", b"gzip")]), "MEDIA_UPSTREAM_BAD_RESPONSE", 502),
    ],
)
def test_preflight_errors_have_machine_readable_headers(upstream, code, status):
    http = FakeHTTP([upstream])
    client, app, publication = client_with(http)
    result = client.get(publication.note.images[0].url)
    assert result.status_code == status
    assert result.headers["x-media-error-code"] == code
    assert result.headers["x-request-id"]
    assert result.json()["error"]["code"] == code
    assert http.closed == 1 and app.state.media_service.admission.active == 0


def test_redirect_stays_server_side_and_every_target_is_validated():
    http = FakeHTTP([(302, [(b"location", IMAGE.replace("p26-", "p27-"))], []), response()])
    client, _, publication = client_with(http)
    result = client.get(publication.note.images[0].url)
    assert result.status_code == 200 and result.content == PNG
    assert len(http.calls) == 2 and "location" not in result.headers
    bad = FakeHTTP([(302, [(b"location", b"https://127.0.0.1/private")], [])])
    client, _, publication = client_with(bad)
    assert client.get(publication.note.images[0].url).status_code == 400
    assert len(bad.calls) == 1


def test_media_logs_do_not_include_capability_path_query_or_source(caplog):
    caplog.set_level(logging.INFO, logger="parser_video")
    client, _, publication = client_with(FakeHTTP([response()]))
    url = publication.note.images[0].url
    client.get(url)
    output = "\n".join(r.getMessage() for r in caplog.records if r.name == "parser_video")
    assert urlsplit(url).path.rsplit("/", 1)[-1] not in output
    assert "sig=" not in output and "one%2Btwo" not in output
    assert "media_complete" in output


def test_media_rate_limit_and_expired_ticket_headers():
    client, app, publication = client_with(FakeHTTP([response()]), media_rate_limit_per_minute=1)
    url = publication.note.images[0].url
    assert client.get(url).status_code == 200
    result = client.get(url)
    assert (
        result.status_code == 429 and result.headers["x-media-error-code"] == "MEDIA_RATE_LIMITED"
    )
    client, app, publication = client_with(FakeHTTP([]))
    app.state.media_tickets.clock = lambda: 10**12
    result = client.get(publication.note.images[0].url)
    assert (
        result.status_code == 410 and result.headers["x-media-error-code"] == "MEDIA_TICKET_EXPIRED"
    )


class StaticService:
    def __init__(self):
        self.note = note()
        self.calls = 0

    async def parse(self, raw_url, refresh, key, platform="douyin"):
        self.calls += 1
        now = datetime.now(UTC)
        return ServiceResult(self.note, now, now + timedelta(seconds=120), self.calls > 1)


def test_parse_response_publishes_cache_hits_without_raw_nested_urls():
    service = StaticService()
    app = create_app(settings(), service)
    client = TestClient(app)
    body = {"url": "https://v.douyin.com/example/"}
    first = client.post("/api/v1/parse", json=body, headers={"X-API-Key": "test"}).json()
    second = client.post("/api/v1/parse", json=body, headers={"X-API-Key": "test"}).json()
    assert first["success"] and second["meta"]["cache"]["hit"]
    assert first["data"]["platform"] == "douyin" and first["data"]["note_id"] is None
    assert first["data"]["images"][0]["url"] != second["data"]["images"][0]["url"]
    assert "douyinpic.com" not in str(first) and "douyinvod.com" not in str(first)
    assert service.note.images[0].url == IMAGE


def test_publication_failure_does_not_repeat_parse_and_rolls_back():
    service = StaticService()
    app = create_app(settings(media_ticket_max_entries=1), service)
    result = TestClient(app).post(
        "/api/v1/parse",
        json={"url": "https://v.douyin.com/example/"},
        headers={"X-API-Key": "test"},
    )
    assert result.status_code == 503 and result.json()["error"]["code"] == "MEDIA_TICKET_CAPACITY"
    assert service.calls == 1 and not app.state.media_tickets.records


def test_bilibili_video_cover_is_also_published():
    video = InternalVideo(
        "https://upos-sz-mirrorcos.bilivideo.com/a.mp4", None, None, None, None, None, None
    )
    original = InternalNote(
        "BVsynthetic",
        "video",
        "video",
        (),
        (video,),
        InternalCover("https://i0.hdslb.com/a.jpg", None, None),
    )
    publication = MediaTickets(settings()).publish(original, "bilibili")
    assert publication.note.videos[0].url.startswith("https://media.example/")
    assert publication.note.cover.url.startswith("https://media.example/")


async def test_asgi_cancellation_releases_source_and_admission():
    from starlette.requests import Request

    config = settings()
    app = create_app(config)
    http = FakeHTTP([response()])
    app.state.media_service = MediaService(config, http)
    record = resolve(
        app.state.media_tickets,
        app.state.media_tickets.publish(note(), "douyin").note.images[0].url,
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/media/redacted",
        "headers": [],
        "app": app,
        "asgi": {"spec_version": "2.4"},
    }
    request = Request(scope)
    request.state.request_id = "synthetic"
    entered = asyncio.Event()
    gate = asyncio.Event()

    async def send(message):
        if message["type"] == "http.response.body":
            entered.set()
            await gate.wait()

    async def receive():
        await gate.wait()

    task = asyncio.create_task(MediaResponse(request, record)(scope, receive, send))
    await entered.wait()
    assert app.state.media_service.admission.active == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert http.closed == 1 and app.state.media_service.admission.active == 0


def test_header_timeout_and_size_limit_close_source():
    from contextlib import asynccontextmanager

    class Stalled(FakeHTTP):
        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            try:
                await asyncio.Event().wait()
                yield
            finally:
                self.closed += 1

    http = Stalled([])
    client, app, publication = client_with(http, media_timeout_seconds=0.01)
    result = client.get(publication.note.images[0].url)
    assert result.status_code == 504
    assert result.headers["x-media-error-code"] == "MEDIA_UPSTREAM_TIMEOUT"
    assert http.closed == 1 and app.state.media_service.admission.active == 0
    http = FakeHTTP([response()])
    client, app, publication = client_with(http, media_max_bytes=1)
    assert client.get(publication.note.images[0].url).status_code == 502
    assert http.closed == 1


@pytest.mark.parametrize("failure", ["truncated", "oversized", "network"])
async def test_after_start_errors_interrupt_without_appending_json(failure, caplog):
    from starlette.requests import Request

    caplog.set_level(logging.INFO, logger="parser_video")
    config = settings(media_max_bytes=64)
    initial = PNG + b"padding-32"
    headers = [(b"content-type", b"image/png")]
    if failure == "truncated":
        headers += [(b"content-length", b"60")]
        chunks = [initial]
    elif failure == "oversized":
        chunks = [initial, b"x" * 80]
    else:
        chunks = [initial, httpcore.ReadError("synthetic failure")]
    http = FakeHTTP([(200, headers, chunks)])
    app = create_app(config)
    app.state.media_service = MediaService(config, http)
    url = app.state.media_tickets.publish(note(), "douyin").note.images[0].url
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/media/redacted",
        "headers": [],
        "app": app,
        "asgi": {"spec_version": "2.0"},
    }
    request = Request(scope)
    request.state.request_id = "synthetic"
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        await asyncio.Event().wait()

    with pytest.raises((AppError, httpcore.ReadError)):
        await MediaResponse(request, resolve(app.state.media_tickets, url))(scope, receive, send)
    assert sum(message["type"] == "http.response.start" for message in sent) == 1
    assert not any(b'"success"' in message.get("body", b"") for message in sent)
    assert http.closed == 1 and app.state.media_service.admission.active == 0
    assert "MEDIA_UPSTREAM_BAD_RESPONSE" in caplog.text


async def test_media_queue_is_independent_bounded_and_releases():
    config = settings(media_concurrency=1, media_queue_capacity=1, media_queue_wait_seconds=0.01)
    service = MediaService(config)
    from app.parser.client import Deadline

    async with service.admission.slot(Deadline(1)):
        async with service.admission.waiter():
            with pytest.raises(AppError, match="BUSY"):
                async with service.admission.slot(Deadline(1)):
                    pytest.fail("queue must refuse")
        with pytest.raises(AppError, match="BUSY"):
            async with service.admission.slot(Deadline(1)):
                pytest.fail("queue must expire")
    assert service.admission.active == service.admission.waiting == 0


@pytest.mark.parametrize(
    "origin",
    [
        "http://media.example",
        "https://user@media.example",
        "https://media.example/prefix",
        "https://media.example?query=x",
    ],
)
def test_public_origin_is_configuration_not_caller_input(origin):
    with pytest.raises(RuntimeError):
        settings(media_public_origin=origin)


def test_failed_public_model_construction_revokes_unpublished_records():
    service = StaticService()
    service.note = InternalNote(
        None,
        "synthetic",
        "image",
        (InternalImage("https://sns-web-i10.rednotecdn.com/synthetic.jpg", None, None, 1),),
        (),
        None,
    )
    app = create_app(settings(), service)
    # Legacy XHS demands a real 24-hex identity; use an invalid synthetic internal note.
    client = TestClient(app, raise_server_exceptions=False)
    result = client.post(
        "/api/v1/xiaohongshu/parse",
        json={"url": "https://xhslink.com/synthetic"},
        headers={"X-API-Key": "test"},
    )
    assert result.status_code == 500
    assert not app.state.media_tickets.records


@pytest.mark.parametrize("brand", [b"avif", b"avis", b"heic", b"mif1", b"zzzz"])
def test_image_or_unknown_ftyp_brands_are_not_mp4(brand):
    from app.services.media_source import sniff_type

    with pytest.raises(AppError):
        sniff_type(b"\x00\x00\x00\x18ftyp" + brand + b"\x00" * 12, "video")


@pytest.mark.parametrize(
    "location,expected",
    [
        ("?", "https://p26-sign.douyinpic.com/a?"),
        ("/other?", "https://p26-sign.douyinpic.com/other?"),
        ("?new=a%2Bb+z&x=1&x=2", "https://p26-sign.douyinpic.com/a?new=a%2Bb+z&x=1&x=2"),
    ],
)
def test_redirect_query_is_not_silently_reused(location, expected):
    from app.services.media_source import media_redirect

    assert media_redirect("https://p26-sign.douyinpic.com/a?old=signature", location) == expected


@pytest.mark.parametrize(
    "dns_code,status,media_code",
    [
        ("UPSTREAM_BAD_RESPONSE", 502, "MEDIA_UPSTREAM_BAD_RESPONSE"),
        ("UPSTREAM_TIMEOUT", 504, "MEDIA_UPSTREAM_TIMEOUT"),
        ("INVALID_URL", 403, "MEDIA_SOURCE_FORBIDDEN"),
    ],
)
def test_dns_failure_classification(dns_code, status, media_code):
    class Failed(FakeHTTP):
        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            raise AppError(dns_code, status)
            yield  # pragma: no cover

    client, _, publication = client_with(Failed([]))
    result = client.get(publication.note.images[0].url)
    assert result.status_code == status and result.headers["x-media-error-code"] == media_code


@pytest.mark.parametrize("stage", ["queue", "connect", "prefix"])
async def test_disconnect_before_response_cancels_and_awaits_cleanup(stage):
    from starlette.requests import Request

    from app.parser.client import Deadline

    config = settings(media_concurrency=1)
    entered = asyncio.Event()
    closed = asyncio.Event()

    class Stalled(FakeHTTP):
        @asynccontextmanager
        async def stream(self, *args, **kwargs):
            try:
                if stage == "connect":
                    entered.set()
                    await asyncio.Event().wait()

                async def body():
                    entered.set()
                    await asyncio.Event().wait()
                    yield b""

                yield httpcore.Response(
                    200, headers=[(b"content-type", b"image/png")], content=body()
                )
            finally:
                closed.set()

    app = create_app(config)
    app.state.media_service = MediaService(config, Stalled([]))
    record = resolve(
        app.state.media_tickets,
        app.state.media_tickets.publish(note(), "douyin").note.images[0].url,
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/media/redacted",
        "headers": [],
        "app": app,
    }
    request = Request(scope)
    request.state.request_id = "synthetic"
    received = []

    async def receive():
        await entered.wait()
        received.append("disconnect")
        return {"type": "http.disconnect"}

    async def send(message):
        pytest.fail("disconnected before response headers")

    if stage == "queue":
        async with app.state.media_service.admission.slot(Deadline(1)):
            entered.set()
            await asyncio.wait_for(MediaResponse(request, record)(scope, receive, send), 0.2)
            assert app.state.media_service.admission.waiting == 0
    else:
        await asyncio.wait_for(MediaResponse(request, record)(scope, receive, send), 0.2)
        assert closed.is_set()
    assert received == ["disconnect"] and app.state.media_service.admission.active == 0
