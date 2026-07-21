"""End-to-end production pipeline — agents through optional YouTube upload."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.agent import AgentPipelineError, ContentAgentPipeline, ContentPipelineResult
from core.config import PROJECT_ROOT, ChannelConfig, load_channel_config
from core.db import ContentFactoryDB, DatabaseError
from core.env import get_env, require_env
from core.images import ImageFetchError, SceneAssetFetcher
from core.media_probe import FFmpegNotFoundError
from core.render import RenderError, ShortsRenderer
from core.schemas import ContentPackage
from core.thumbnail import ThumbnailError, ThumbnailGenerator
from core.tts import NarrationSynthesizer, TtsError
from publishers.base import PublishResult, PublisherError
from publishers.youtube import YouTubePublisher


class PipelineError(RuntimeError):
    """Raised when the end-to-end factory run fails."""


@dataclass
class FactoryRunResult:
    package: ContentPackage
    package_dir: Path
    agent_result: ContentPipelineResult
    publish_result: PublishResult | None = None


def _relative_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _default_privacy(config: ChannelConfig) -> str:
    try:
        import yaml

        with config.config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        youtube = raw.get("youtube") or {}
        privacy = str(youtube.get("privacy_status", "")).strip().lower()
        if privacy in {"public", "unlisted", "private"}:
            return privacy
    except Exception:
        pass
    env_privacy = get_env("YOUTUBE_PRIVACY_STATUS", "unlisted").lower()
    return env_privacy if env_privacy in {"public", "unlisted", "private"} else "unlisted"


class ContentFactoryPipeline:
    """Run the full Shorts factory: plan → assets → render → package → upload."""

    def __init__(
        self,
        config: ChannelConfig | None = None,
        db: ContentFactoryDB | None = None,
    ) -> None:
        self.config = config or load_channel_config()
        self.db = db if db is not None else ContentFactoryDB()

    def run(
        self,
        *,
        manual_topic: str | None = None,
        manual_angle: str | None = None,
        upload: bool = True,
        skip_thumbnail_upload: bool = False,
        privacy_status: str | None = None,
        persist: bool = True,
        output_root: Path | str | None = None,
    ) -> FactoryRunResult:
        require_env("GEMINI_API_KEY")
        require_env("PEXELS_API_KEY")

        agent_pipeline = ContentAgentPipeline(
            config=self.config,
            db=self.db if persist else None,
        )

        try:
            agent_result = agent_pipeline.run_content_pipeline(
                manual_topic=manual_topic,
                manual_angle=manual_angle,
                persist=persist,
            )
        except AgentPipelineError as exc:
            raise PipelineError(str(exc)) from exc

        package = ContentPackage.create(
            channel_niche=self.config.channel.niche,
            channel_niche_label=self.config.channel.niche_label,
            channel_name=self.config.channel.name,
            topic=agent_result.topic,
            content_plan=agent_result.content_plan,
            review=agent_result.review,
        )

        root = Path(output_root) if output_root else PROJECT_ROOT / "output"
        package_dir = (root / package.package_id).resolve()
        package_dir.mkdir(parents=True, exist_ok=True)

        scenes_dir = package_dir / "scenes"
        voice_path = package_dir / "voice.mp3"
        video_path = package_dir / "video.mp4"
        thumbnail_path = package_dir / "thumbnail.jpg"

        try:
            fetch_result = SceneAssetFetcher(config=self.config).fetch_scenes(
                agent_result.content_plan,
                work_dir=scenes_dir,
            )
            plan = fetch_result.content_plan

            voice = NarrationSynthesizer(config=self.config).synthesize_content_plan(
                plan,
                output_path=voice_path,
            )

            render_result = ShortsRenderer(config=self.config).render(
                plan,
                voice.voice_path,
                output_path=video_path,
                burn_subtitles=True,
            )

            thumb_result = ThumbnailGenerator(config=self.config).generate(
                plan,
                output_path=thumbnail_path,
                work_dir=package_dir / "thumbnail_work",
            )
        except (ImageFetchError, TtsError, RenderError, FFmpegNotFoundError, ThumbnailError) as exc:
            raise PipelineError(str(exc)) from exc

        scene_paths = [
            _relative_path(path)
            for path in sorted(scenes_dir.glob("scene_*.jpg"))
        ]
        package.assets.video_path = _relative_path(render_result.video_path)
        package.assets.thumbnail_path = _relative_path(thumb_result.thumbnail_path)
        package.assets.voice_path = _relative_path(voice.voice_path)
        package.assets.scene_paths = scene_paths

        package_path = package_dir / "content_package.json"
        package_path.write_text(
            json.dumps(package.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        publish_result: PublishResult | None = None
        if upload:
            privacy = privacy_status or _default_privacy(self.config)
            publisher = YouTubePublisher(privacy_status=privacy)
            try:
                publisher.authenticate()
                publish_result = publisher.publish_package(
                    package,
                    video_path=render_result.video_path,
                    thumbnail_path=None
                    if skip_thumbnail_upload
                    else thumb_result.thumbnail_path,
                    privacy_status=privacy,
                )
                package.status = "published"
            except PublisherError as exc:
                package.status = "failed"
                package_path.write_text(
                    json.dumps(package.to_dict(), ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                if persist:
                    self._log_run(
                        agent_result,
                        package,
                        status="failed",
                        metadata={"error": str(exc)},
                    )
                raise PipelineError(str(exc)) from exc

            package_path.write_text(
                json.dumps(package.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        if persist:
            self._log_run(
                agent_result,
                package,
                status=package.status,
                publish_result=publish_result,
            )

        return FactoryRunResult(
            package=package,
            package_dir=package_dir,
            agent_result=agent_result,
            publish_result=publish_result,
        )

    def _log_run(
        self,
        agent_result: ContentPipelineResult,
        package: ContentPackage,
        *,
        status: str,
        publish_result: PublishResult | None = None,
        metadata: dict | None = None,
    ) -> None:
        payload = metadata or {}
        if publish_result:
            payload.update(
                {
                    "platform": publish_result.platform,
                    "remote_id": publish_result.remote_id,
                    "url": publish_result.url,
                    "privacy_status": publish_result.privacy_status,
                    "thumbnail_applied": publish_result.thumbnail_applied,
                    "thumbnail_warning": publish_result.thumbnail_warning,
                }
            )
        try:
            self.db.log_production_run(
                niche=self.config.channel.niche,
                topic=agent_result.topic.topic,
                status=status,
                seo_title=agent_result.content_plan.seo.title,
                package_id=package.package_id,
                video_path=package.assets.video_path,
                thumbnail_path=package.assets.thumbnail_path,
                review_overall=agent_result.review.overall,
                attempts=agent_result.attempts,
                metadata=payload,
            )
        except DatabaseError:
            pass
