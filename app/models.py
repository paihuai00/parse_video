"""Internal immutable records and public Pydantic schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


@dataclass(frozen=True)
class InternalImage:
    url: str
    source_width: int | None
    source_height: int | None
    index: int


@dataclass(frozen=True)
class InternalCover:
    url: str
    source_width: int | None
    source_height: int | None


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


class ImageMedia(StrictModel):
    url: HttpUrl
    source_width: int | None = Field(default=None, ge=1)
    source_height: int | None = Field(default=None, ge=1)
    url_expires_at: datetime | None = None
    verification: Literal["not_checked"] = "not_checked"
    index: int = Field(ge=1)


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


class ParseError(StrictModel):
    success: Literal[False] = False
    data: None = None
    error: ErrorDetails
    meta: ResponseMeta


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"


def to_public_note(note: InternalNote) -> ImageNote | VideoNote:
    if note.kind == "image":
        return ImageNote(
            note_id=note.note_id,
            title=note.title,
            type="image",
            images=[
                ImageMedia(
                    url=item.url,
                    source_width=item.source_width,
                    source_height=item.source_height,
                    index=item.index,
                )
                for item in note.images
            ],
            videos=[],
            cover=None,
        )
    cover = None
    if note.cover:
        cover = CoverMedia(
            url=note.cover.url,
            source_width=note.cover.source_width,
            source_height=note.cover.source_height,
        )
    return VideoNote(
        note_id=note.note_id,
        title=note.title,
        type="video",
        images=[],
        videos=[
            VideoMedia(
                url=item.url,
                source_width=item.source_width,
                source_height=item.source_height,
                codec=item.codec,
                quality=item.quality,
                duration_seconds=item.duration_seconds,
                size_bytes=item.size_bytes,
            )
            for item in note.videos
        ],
        cover=cover,
    )
