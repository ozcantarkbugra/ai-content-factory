"""Agent pipeline: Topic → Master Content → Reviewer with quality gate."""

from __future__ import annotations

import json
from dataclasses import dataclass

from core.config import ChannelConfig, build_agent_prompt, load_channel_config
from core.gemini_client import GeminiClient
from core.schemas import (
    ContentPlan,
    ReviewDecision,
    ReviewResult,
    SchemaError,
    TopicSelection,
)


class AgentPipelineError(RuntimeError):
    """Raised when the agent pipeline cannot produce approved content."""


@dataclass
class ContentPipelineResult:
    topic: TopicSelection
    content_plan: ContentPlan
    review: ReviewResult
    attempts: int

    @property
    def approved(self) -> bool:
        return self.review.is_approved()


class ContentAgentPipeline:
    def __init__(
        self,
        config: ChannelConfig | None = None,
        client: GeminiClient | None = None,
    ) -> None:
        self.config = config or load_channel_config()
        self._client = client

    @property
    def client(self) -> GeminiClient:
        if self._client is None:
            self._client = GeminiClient()
        return self._client

    def run_topic_agent(
        self,
        used_topics: list[str] | None = None,
        trend_hints: str = "",
    ) -> TopicSelection:
        prompt = build_agent_prompt(
            "topic_agent.txt",
            self.config,
            used_topics=used_topics or [],
            trend_hints=trend_hints,
        )
        data = self.client.generate_json(prompt)
        return TopicSelection.from_dict(data)

    def run_master_agent(
        self,
        topic: TopicSelection,
        fix_instructions: list[str] | None = None,
    ) -> ContentPlan:
        prompt = build_agent_prompt(
            "master_agent.txt",
            self.config,
            topic=topic.topic,
            angle=topic.angle,
        )
        if fix_instructions:
            fixes = "\n".join(f"- {item}" for item in fix_instructions)
            prompt += (
                "\n\n## Önceki deneme reddedildi\n"
                "Aşağıdaki düzeltmeleri uygulayarak JSON çıktısını yeniden üret:\n"
                f"{fixes}\n"
            )
        data = self.client.generate_json(prompt)
        plan = ContentPlan.from_dict(data)
        if plan.topic != topic.topic:
            plan.topic = topic.topic
        return plan

    def run_reviewer_agent(self, content_plan: ContentPlan) -> ReviewResult:
        content_json = json.dumps(content_plan.to_dict(), ensure_ascii=False, indent=2)
        prompt = build_agent_prompt(
            "reviewer_agent.txt",
            self.config,
            content_json=content_json,
        )
        review = ReviewResult.from_dict(self.client.generate_json(prompt))
        return self._enforce_review_rules(review)

    def _enforce_review_rules(self, review: ReviewResult) -> ReviewResult:
        """Apply config thresholds even if the LLM approves too loosely."""
        min_score = self.config.production.reviewer_min_score
        scores = review.scores

        blocking_issues: list[str] = list(review.issues)
        fixes: list[str] = list(review.fix_instructions)

        if review.overall < min_score:
            blocking_issues.append(
                f"overall score {review.overall} below minimum {min_score}"
            )
            fixes.append(f"Kaliteyi artır; overall en az {min_score} olmalı.")

        if scores.policy_risk < 7:
            blocking_issues.append(f"policy_risk {scores.policy_risk} below 7")
            fixes.append("Clickbait, tekrar ve politika riskini azalt.")

        if scores.factual_safety < 7:
            blocking_issues.append(f"factual_safety {scores.factual_safety} below 7")
            fixes.append("Doğrulanamayan iddiaları kaldır veya yumuşat.")

        if blocking_issues and review.decision == ReviewDecision.APPROVE:
            return ReviewResult(
                decision=ReviewDecision.REJECT,
                scores=review.scores,
                overall=review.overall,
                issues=blocking_issues,
                fix_instructions=fixes or ["Reviewer eşiklerini karşılayacak şekilde yeniden yaz."],
                summary="Otomatik eşik kontrolü: APPROVE reddedildi.",
            )

        if review.decision == ReviewDecision.REJECT and not fixes:
            fixes = ["Reviewer geri bildirimine göre senaryoyu baştan yaz."]

        return ReviewResult(
            decision=review.decision,
            scores=review.scores,
            overall=review.overall,
            issues=blocking_issues or review.issues,
            fix_instructions=fixes if review.decision == ReviewDecision.REJECT else [],
            summary=review.summary,
        )

    def run_content_pipeline(
        self,
        *,
        used_topics: list[str] | None = None,
        trend_hints: str = "",
        manual_topic: str | None = None,
        manual_angle: str | None = None,
    ) -> ContentPipelineResult:
        if manual_topic:
            topic = TopicSelection(
                topic=manual_topic,
                angle=manual_angle or "Manuel seçilen konu",
                target_audience=self.config.channel.target_audience,
                estimated_interest=8,
                search_keywords=[manual_topic],
                why_now="Manuel üretim",
                risk_level="low",
                risk_note=None,
            )
        else:
            topic = self.run_topic_agent(used_topics=used_topics, trend_hints=trend_hints)

        max_attempts = self.config.production.reviewer_max_retries + 1
        fix_instructions: list[str] | None = None
        content_plan: ContentPlan | None = None
        review: ReviewResult | None = None

        for attempt in range(1, max_attempts + 1):
            content_plan = self.run_master_agent(topic, fix_instructions=fix_instructions)
            review = self.run_reviewer_agent(content_plan)
            if review.is_approved():
                return ContentPipelineResult(
                    topic=topic,
                    content_plan=content_plan,
                    review=review,
                    attempts=attempt,
                )
            fix_instructions = review.fix_instructions

        assert content_plan is not None and review is not None
        raise AgentPipelineError(
            f"Content not approved after {max_attempts} attempt(s). "
            f"Last issues: {review.issues}"
        )
