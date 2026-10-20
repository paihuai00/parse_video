"""Internal immutable records and public Pydantic schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SerializerFunctionWrapHandler,
    model_serializer,
)


@dataclass(frozen=True)
class InternalVideo:
    url: str
    source_width: int | None
    source_height: int | None
    codec: str | None
    quality: str | None
    duration_seconds: float | None
    size_bytes: int | None


@dataclass(frozen=True)
class InternalImage:
    url: str
    source_width: int | None
    source_height: int | None
    index: int
    live_video: InternalVideo | None = None


@dataclass(frozen=True)
class InternalCover:
    url: str
    source_width: int | None
    source_height: int | None


@dataclass(frozen=True)
class InternalNote:
    note_id: str
    title: str | None
    kind: Literal["image", "video"]
    images: tuple[InternalImage, ...]
    videos: tuple[InternalVideo, ...]
    cover: InternalCover | None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParseRequest(StrictModel):
    url: HttpUrl = Field(max_length=4096)
    refresh: bool = False


class CoverMedia(StrictModel):
    url: HttpUrl
    source_width: int | None = Field(default=None, ge=1)
    source_height: int | None = Field(default=None, ge=1)
    url_expires_at: datetime | None = None
    verification: Literal["not_checked"] = "not_checked"


class VideoMedia(CoverMedia):
    format: Literal["mp4"] = "mp4"
    codec: str | None = None
    quality: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    size_bytes: int | None = Field(default=None, ge=0)


class ImageMedia(StrictModel):
    url: HttpUrl
    source_width: int | None = Field(default=None, ge=1)
    source_height: int | None = Field(default=None, ge=1)
    url_expires_at: datetime | None = None
    verification: Literal["not_checked"] = "not_checked"
    index: int = Field(ge=1)
    live_video: VideoMedia | None = None

    @model_serializer(mode="wrap")
    def omit_absent_live_video(  # type: ignore[no-untyped-def]
        self, handler: SerializerFunctionWrapHandler
    ):
        # Leaving the return type unannotated is intentional. Pydantic treats a
        # concrete dict return annotation as the model's serialization schema,
        # which would collapse FastAPI's generated ImageMedia schema to a bare
        # object even though the wire output remains structured.
        serialized = handler(self)
        if self.live_video is None:
            serialized.pop("live_video", None)
        return serialized


class ImageNote(StrictModel):
    note_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    title: str | None
    type: Literal["image"]
    images: list[ImageMedia] = Field(min_length=1)
    videos: list[VideoMedia] = Field(max_length=0)
    cover: None


class VideoNote(StrictModel):
    note_id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    title: str | None
    type: Literal["video"]
    images: list[ImageMedia] = Field(max_length=0)
    videos: list[VideoMedia] = Field(min_length=1, max_length=1)
    cover: CoverMedia | None


ParsedNote = Annotated[ImageNote | VideoNote, Field(discriminator="type")]


class UnifiedImageNote(StrictModel):
    note_id: str = Field(pattern=r"^(?:[0-9a-fA-F]{24}|[0-9]{18,20})$")
    title: str | None
    type: Literal["image"]
    images: list[ImageMedia] = Field(min_length=1)
    videos: list[VideoMedia] = Field(max_length=0)
    cover: None


class UnifiedVideoNote(StrictModel):
    note_id: str = Field(pattern=r"^(?:[0-9a-fA-F]{24}|[0-9]{18,20})$")
    title: str | None
    type: Literal["video"]
    images: list[ImageMedia] = Field(max_length=0)
    videos: list[VideoMedia] = Field(min_length=1, max_length=1)
    cover: CoverMedia | None


UnifiedParsedNote = Annotated[UnifiedImageNote | UnifiedVideoNote, Field(discriminator="type")]


class CacheMetadata(StrictModel):
    hit: bool
    expires_at: datetime


class ResponseMeta(StrictModel):
    request_id: str
    parsed_at: datetime | None
    cache: CacheMetadata | None


class ErrorDetails(StrictModel):
    code: str
    message: str
    retryable: bool


class ParseSuccess(StrictModel):
    success: Literal[True] = True
    data: ParsedNote
    error: None = None
    meta: ResponseMeta


class UnifiedParseSuccess(StrictModel):
    success: Literal[True] = True
    data: UnifiedParsedNote
    error: None = None
    meta: ResponseMeta


class ParseError(StrictModel):
    success: Literal[False] = False
    data: None = None
    error: ErrorDetails
    meta: ResponseMeta


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"


def to_public_note(note: InternalNote) -> ImageNote | VideoNote:
    images, videos, cover = _to_public_components(note)
    if note.kind == "image":
        return ImageNote(
            note_id=note.note_id,
            title=note.title,
            type="image",
            images=images,
            videos=[],
            cover=None,
        )
    return VideoNote(
        note_id=note.note_id,
        title=note.title,
        type="video",
        images=[],
        videos=videos,
        cover=cover,
    )


def to_unified_public_note(note: InternalNote) -> UnifiedImageNote | UnifiedVideoNote:
    public = _to_public_components(note)
    if note.kind == "image":
        return UnifiedImageNote(
            note_id=note.note_id,
            title=note.title,
            type="image",
            images=public[0],
            videos=[],
            cover=None,
        )
    return UnifiedVideoNote(
        note_id=note.note_id,
        title=note.title,
        type="video",
        images=[],
        videos=public[1],
        cover=public[2],
    )


def _to_public_components(
    note: InternalNote,
) -> tuple[list[ImageMedia], list[VideoMedia], CoverMedia | None]:
    images = [
        ImageMedia(
            url=item.url,
            source_width=item.source_width,
            source_height=item.source_height,
            url_expires_at=None,
            verification="not_checked",
            index=item.index,
            live_video=(
                VideoMedia(
                    url=item.live_video.url,
                    source_width=item.live_video.source_width,
                    source_height=item.live_video.source_height,
                    url_expires_at=None,
                    verification="not_checked",
                    format="mp4",
                    codec=item.live_video.codec,
                    quality=item.live_video.quality,
                    duration_seconds=item.live_video.duration_seconds,
                    size_bytes=item.live_video.size_bytes,
                )
                if item.live_video
                else None
            ),
        )
        for item in note.images
    ]
    videos = [
        VideoMedia(
            url=item.url,
            source_width=item.source_width,
            source_height=item.source_height,
            url_expires_at=None,
            verification="not_checked",
            format="mp4",
            codec=item.codec,
            quality=item.quality,
            duration_seconds=item.duration_seconds,
            size_bytes=item.size_bytes,
        )
        for item in note.videos
    ]
    cover = None
    if note.cover:
        cover = CoverMedia(
            url=note.cover.url,
            source_width=note.cover.source_width,
            source_height=note.cover.source_height,
            url_expires_at=None,
            verification="not_checked",
        )
    return images, videos, cover
