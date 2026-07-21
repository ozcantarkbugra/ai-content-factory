"""Optional Telegram notifications for pipeline runs."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from core.env import get_env, load_dotenv
from core.pipeline import FactoryRunResult
from publishers.base import PublishResult


class TelegramError(RuntimeError):
    """Raised when a Telegram message cannot be sent."""


class TelegramNotifier:
    """Send run summaries via Telegram Bot API (optional — requires .env)."""

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        load_dotenv()
        self.bot_token = (bot_token or get_env("TELEGRAM_BOT_TOKEN")).strip()
        self.chat_id = (chat_id or get_env("TELEGRAM_CHAT_ID")).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_message(self, text: str, *, disable_preview: bool = True) -> None:
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": disable_preview,
        }
        body = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise TelegramError(f"Telegram HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TelegramError(f"Telegram network error: {exc}") from exc

        if not raw.get("ok"):
            raise TelegramError(f"Telegram API error: {raw}")

    def notify_success(self, result: FactoryRunResult) -> None:
        plan = result.package.content_plan
        lines = [
            "✅ AI Content Factory — tamamlandı",
            f"Kanal: {result.package.channel_name}",
            f"Konu: {result.package.topic.topic}",
            f"Başlık: {plan.seo.title}",
            f"Durum: {result.package.status}",
            f"Paket: {result.package.package_id}",
        ]
        if result.publish_result:
            lines.extend(self._youtube_lines(result.publish_result))
        elif result.package.status == "ready":
            lines.append("YouTube: yüklenmedi (--no-upload)")
        self.send_message("\n".join(lines))

    def notify_failure(self, error: str, *, topic: str | None = None) -> None:
        lines = [
            "❌ AI Content Factory — hata",
            f"Konu: {topic or '(bilinmiyor)'}",
            f"Hata: {error[:500]}",
        ]
        self.send_message("\n".join(lines))

    @staticmethod
    def _youtube_lines(publish: PublishResult) -> list[str]:
        lines = [
            f"YouTube: {publish.url}",
            f"Gizlilik: {publish.privacy_status}",
        ]
        if publish.thumbnail_warning:
            lines.append(f"Thumbnail: {publish.thumbnail_warning[:200]}")
        return lines
