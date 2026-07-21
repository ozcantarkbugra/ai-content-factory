"""SQLite persistence for used topics and production logs."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from core.config import PROJECT_ROOT, ChannelConfig, load_channel_config


class DatabaseError(RuntimeError):
    """Raised when a database operation fails."""


DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "factory.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ProductionRunRecord:
    id: int
    niche: str
    topic: str
    status: str
    seo_title: str | None
    package_id: str | None
    video_path: str | None
    thumbnail_path: str | None
    review_overall: float | None
    attempts: int | None
    created_at: str


class ContentFactoryDB:
    """Track topics and production runs per channel niche."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS used_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    niche TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    angle TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(niche, topic)
                );

                CREATE TABLE IF NOT EXISTS production_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    niche TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    status TEXT NOT NULL,
                    seo_title TEXT,
                    package_id TEXT,
                    video_path TEXT,
                    thumbnail_path TEXT,
                    review_overall REAL,
                    attempts INTEGER,
                    created_at TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_used_topics_niche
                    ON used_topics(niche, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_production_runs_niche
                    ON production_runs(niche, created_at DESC);
                """
            )

    def get_used_topics(self, niche: str, *, limit: int = 100) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT topic FROM used_topics
                WHERE niche = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (niche, limit),
            ).fetchall()
        return [str(row["topic"]) for row in rows]

    def record_topic(self, niche: str, topic: str, *, angle: str | None = None) -> None:
        cleaned = topic.strip()
        if not cleaned:
            raise DatabaseError("Cannot record an empty topic")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO used_topics (niche, topic, angle, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(niche, topic) DO UPDATE SET
                    angle = excluded.angle,
                    created_at = excluded.created_at
                """,
                (niche, cleaned, angle, _utc_now()),
            )

    def log_production_run(
        self,
        *,
        niche: str,
        topic: str,
        status: str,
        seo_title: str | None = None,
        package_id: str | None = None,
        video_path: str | None = None,
        thumbnail_path: str | None = None,
        review_overall: float | None = None,
        attempts: int | None = None,
        metadata: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> str:
        run_identifier = run_id or str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO production_runs (
                    run_id, niche, topic, status, seo_title, package_id,
                    video_path, thumbnail_path, review_overall, attempts,
                    created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_identifier,
                    niche,
                    topic.strip(),
                    status,
                    seo_title,
                    package_id,
                    video_path,
                    thumbnail_path,
                    review_overall,
                    attempts,
                    _utc_now(),
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
        return run_identifier

    def list_production_runs(
        self,
        niche: str | None = None,
        *,
        limit: int = 20,
    ) -> list[ProductionRunRecord]:
        query = """
            SELECT id, niche, topic, status, seo_title, package_id, video_path,
                   thumbnail_path, review_overall, attempts, created_at
            FROM production_runs
        """
        params: list[Any]
        if niche:
            query += " WHERE niche = ?"
            params = [niche, limit]
            query += " ORDER BY created_at DESC LIMIT ?"
        else:
            params = [limit]
            query += " ORDER BY created_at DESC LIMIT ?"

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [
            ProductionRunRecord(
                id=int(row["id"]),
                niche=str(row["niche"]),
                topic=str(row["topic"]),
                status=str(row["status"]),
                seo_title=row["seo_title"],
                package_id=row["package_id"],
                video_path=row["video_path"],
                thumbnail_path=row["thumbnail_path"],
                review_overall=row["review_overall"],
                attempts=row["attempts"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def record_pipeline_result(
        self,
        config: ChannelConfig,
        result: Any,
        *,
        status: str = "approved",
        video_path: str | None = None,
        thumbnail_path: str | None = None,
        package_id: str | None = None,
    ) -> str:
        niche = config.channel.niche
        self.record_topic(niche, result.topic.topic, angle=result.topic.angle)
        return self.log_production_run(
            niche=niche,
            topic=result.topic.topic,
            status=status,
            seo_title=result.content_plan.seo.title,
            package_id=package_id,
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            review_overall=result.review.overall,
            attempts=result.attempts,
            metadata={
                "angle": result.topic.angle,
                "review_summary": result.review.summary,
                "scene_count": len(result.content_plan.scenes),
            },
        )
