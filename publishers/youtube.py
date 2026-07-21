"""YouTube Data API v3 upload adapter with OAuth 2.0."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from core.config import PROJECT_ROOT
from core.env import get_env
from publishers.base import BasePublisher, PublishResult, PublisherError

SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)

YOUTUBE_CATEGORY_IDS: dict[str, str] = {
    "film & animation": "1",
    "autos & vehicles": "2",
    "music": "10",
    "pets & animals": "15",
    "sports": "17",
    "short movies": "18",
    "travel & events": "19",
    "gaming": "20",
    "videoblogging": "21",
    "people & blogs": "22",
    "comedy": "23",
    "entertainment": "24",
    "news & politics": "25",
    "howto & style": "26",
    "education": "27",
    "science & technology": "28",
    "nonprofits & activism": "29",
}


def _resolve_path(path: Path | str) -> Path:
    candidate = Path(path)
    if candidate.is_file():
        return candidate.resolve()
    rooted = (PROJECT_ROOT / candidate).resolve()
    if rooted.is_file():
        return rooted
    raise PublisherError(f"File not found: {path}")


def _resolve_category_id(category: str | None) -> str:
    if not category:
        return YOUTUBE_CATEGORY_IDS["education"]
    cleaned = category.strip()
    if cleaned.isdigit():
        return cleaned
    mapped = YOUTUBE_CATEGORY_IDS.get(cleaned.lower())
    if mapped:
        return mapped
    raise PublisherError(
        f"Unknown YouTube category '{category}'. "
        f"Use a numeric ID or one of: {', '.join(sorted(YOUTUBE_CATEGORY_IDS))}"
    )


def _normalize_tags(tags: list[str] | None, *, max_count: int = 30) -> list[str]:
    if not tags:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = raw.strip().lstrip("#")
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(tag[:100])
        if len(cleaned) >= max_count:
            break
    return cleaned


def _append_shorts_hashtags(description: str, hashtags: list[str]) -> str:
    body = description.rstrip()
    extras: list[str] = []
    lower_body = body.lower()
    if "#shorts" not in lower_body:
        extras.append("#Shorts")
    for tag in hashtags:
        normalized = tag if tag.startswith("#") else f"#{tag.lstrip('#')}"
        if normalized.lower() not in lower_body:
            extras.append(normalized)
    if not extras:
        return body
    suffix = " ".join(extras)
    return f"{body}\n\n{suffix}" if body else suffix


class YouTubePublisher(BasePublisher):
    """Upload Shorts/longform videos via YouTube Data API v3."""

    def __init__(
        self,
        *,
        client_secrets_file: Path | str | None = None,
        token_file: Path | str | None = None,
        privacy_status: str = "unlisted",
    ) -> None:
        secrets_raw = client_secrets_file or get_env(
            "YOUTUBE_CLIENT_SECRETS_FILE",
            "credentials/client_secret.json",
        )
        token_raw = token_file or get_env(
            "YOUTUBE_TOKEN_FILE",
            "credentials/token.json",
        )
        self.client_secrets_file = (PROJECT_ROOT / secrets_raw).resolve()
        self.token_file = (PROJECT_ROOT / token_raw).resolve()
        self.default_privacy_status = privacy_status.strip().lower()
        self._service: Any | None = None

    def authenticate(self, *, interactive: bool = True) -> None:
        if not self.client_secrets_file.is_file():
            raise PublisherError(
                f"YouTube client secrets not found: {self.client_secrets_file}\n"
                "Download OAuth Desktop credentials from Google Cloud Console "
                "and save as credentials/client_secret.json"
            )

        credentials = self._load_credentials(interactive=interactive)
        self._service = build("youtube", "v3", credentials=credentials, cache_discovery=False)

    def publish(
        self,
        *,
        video_path: Path,
        title: str,
        description: str,
        tags: list[str] | None = None,
        thumbnail_path: Path | None = None,
        category: str | None = None,
        privacy_status: str | None = None,
    ) -> PublishResult:
        if self._service is None:
            self.authenticate()

        resolved_video = _resolve_path(video_path)
        resolved_thumbnail = _resolve_path(thumbnail_path) if thumbnail_path else None

        cleaned_title = title.strip()
        if not cleaned_title:
            raise PublisherError("Video title is required")
        if len(cleaned_title) > 100:
            cleaned_title = cleaned_title[:100].rstrip()

        privacy = (privacy_status or self.default_privacy_status).lower()
        if privacy not in {"public", "unlisted", "private"}:
            raise PublisherError("privacy_status must be public, unlisted, or private")

        category_id = _resolve_category_id(category)
        normalized_tags = _normalize_tags(tags)

        body: dict[str, Any] = {
            "snippet": {
                "title": cleaned_title,
                "description": description.strip(),
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }
        if normalized_tags:
            body["snippet"]["tags"] = normalized_tags

        media = MediaFileUpload(
            str(resolved_video),
            mimetype="video/mp4",
            chunksize=8 * 1024 * 1024,
            resumable=True,
        )

        try:
            request = self._service.videos().insert(  # type: ignore[union-attr]
                part="snippet,status",
                body=body,
                media_body=media,
            )
            response = self._execute_resumable_upload(request)
            video_id = str(response["id"])
        except HttpError as exc:
            raise PublisherError(f"YouTube upload failed: {exc}") from exc

        thumbnail_applied = True
        thumbnail_warning: str | None = None
        if resolved_thumbnail:
            thumbnail_applied, thumbnail_warning = self._apply_thumbnail(
                video_id,
                resolved_thumbnail,
            )
            if thumbnail_warning:
                print(f"THUMBNAIL WARNING: {thumbnail_warning}")

        return PublishResult(
            platform="youtube",
            remote_id=video_id,
            url=f"https://www.youtube.com/watch?v={video_id}",
            title=cleaned_title,
            privacy_status=privacy,
            thumbnail_applied=thumbnail_applied,
            thumbnail_warning=thumbnail_warning,
        )

    def publish_package(
        self,
        package,
        *,
        video_path: Path | None = None,
        thumbnail_path: Path | None = None,
        privacy_status: str | None = None,
    ) -> PublishResult:
        overrides = package.platform_overrides.youtube
        description = str(
            overrides.get("description") or package.content_plan.seo.description
        )
        enriched_description = _append_shorts_hashtags(
            description,
            package.content_plan.seo.hashtags,
        )

        resolved_video = video_path
        if resolved_video is None:
            if not package.assets.video_path:
                raise PublisherError("ContentPackage has no assets.video_path")
            resolved_video = Path(package.assets.video_path)

        resolved_thumbnail = thumbnail_path
        if resolved_thumbnail is None and package.assets.thumbnail_path:
            resolved_thumbnail = Path(package.assets.thumbnail_path)

        title = str(overrides.get("title") or package.content_plan.seo.title)
        tags_raw = overrides.get("tags") or package.content_plan.seo.tags
        tags = [str(tag) for tag in tags_raw] if tags_raw else None
        category = overrides.get("category") or package.content_plan.seo.category

        return self.publish(
            video_path=resolved_video,
            title=title,
            description=enriched_description,
            tags=tags,
            thumbnail_path=resolved_thumbnail,
            category=str(category) if category else None,
            privacy_status=privacy_status,
        )

    def _load_credentials(self, *, interactive: bool) -> Credentials:
        credentials: Credentials | None = None
        if self.token_file.is_file():
            credentials = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if credentials and credentials.valid:
            return credentials

        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            self._save_credentials(credentials)
            return credentials

        if not interactive:
            raise PublisherError(
                "YouTube OAuth token missing or expired. "
                "Run: python scripts/upload_youtube.py --auth-only"
            )

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise PublisherError(
                "Missing google-auth-oauthlib. Run: pip install -r requirements.txt"
            ) from exc

        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.client_secrets_file),
            SCOPES,
        )
        credentials = flow.run_local_server(port=0, open_browser=True)
        self._save_credentials(credentials)
        return credentials

    def _save_credentials(self, credentials: Credentials) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(credentials.to_json(), encoding="utf-8")

    def _execute_resumable_upload(self, request: Any) -> dict[str, Any]:
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                progress = int(status.progress() * 100)
                print(f"Upload progress: {progress}%")
        if not isinstance(response, dict) or "id" not in response:
            raise PublisherError("YouTube upload finished without a video id")
        return response

    def _apply_thumbnail(
        self,
        video_id: str,
        thumbnail_path: Path,
    ) -> tuple[bool, str | None]:
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg", resumable=False)
        try:
            self._service.thumbnails().set(  # type: ignore[union-attr]
                videoId=video_id,
                media_body=media,
            ).execute()
            return True, None
        except HttpError as exc:
            if exc.resp.status == 403:
                return False, (
                    "Custom thumbnails are not enabled for this channel yet. "
                    "Verify at https://www.youtube.com/verify or upload the thumbnail "
                    "manually in YouTube Studio."
                )
            return False, f"Thumbnail upload failed: {exc}"
