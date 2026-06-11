"""Smoke test for Tier 1.2 question log.

Exercises:
1. Direct DB persist of synthetic extracted questions (mimics deep_dive merge)
2. node_targeted_followup against the synthetic run (Sonnet mocked)
3. Manual dismiss
4. Cross-run resurfacing query

Cleans up synthetic rows on success AND on caught ValueError/AssertionError.

Run from project root:
    PYTHONPATH=. backend/venv/bin/python backend/scripts/smoke_question_log.py
"""
import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from backend.app.db import async_session
from backend.app.graph import nodes
from backend.app.graph.state import CategoryResult, ResearchState
from backend.app.models.question import Question
from backend.app.models.research_run import ResearchRun
from backend.app.models.theme import Theme
from sqlalchemy import delete, select

SYNTH_TICKER = "ZZZQ"


async def _seed_synthetic_run() -> str:
    """Create a minimal ResearchRun row so questions can FK to it.

    ResearchRun.theme_id is NOT NULL so we pick the first existing theme."""
    async with async_session() as db:
        first_theme = (await db.execute(select(Theme).limit(1))).scalar_one_or_none()
        if first_theme is None:
            raise ValueError("no themes in DB; smoke needs at least one theme to FK against")
        run_id = str(uuid4())
        run = ResearchRun(
            id=run_id,
            ticker=SYNTH_TICKER,
            theme_id=first_theme.id,
            status="completed",
            phase="completed",
            state={"ticker": SYNTH_TICKER, "theme_id": "", "run_id": run_id, "phase_outputs": {}},
        )
        db.add(run)
        await db.commit()
        return run_id


async def _persist_extracted(run_id: str, items: list[dict]) -> list[str]:
    ids: list[str] = []
    async with async_session() as db:
        for it in items:
            q = Question(
                ticker=SYNTH_TICKER,
                theme_id=None,
                category=it["category"],
                question_text=it["text"],
                priority=it["priority"],
                auto_answerable=it["auto_answerable"],
                status="open",
                created_run_id=run_id,
            )
            db.add(q)
            await db.flush()
            ids.append(q.id)
        await db.commit()
    return ids


async def _cleanup(run_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Question).where(Question.ticker == SYNTH_TICKER))
        await db.execute(delete(ResearchRun).where(ResearchRun.id == run_id))
        await db.commit()


async def _mock_complete(*args, **kwargs):
    """Return a JSON string matching the TargetedAnswer schema. The
    assistant_prefill prefix '{"answer_text":' is included because
    complete() prepends it back on real calls."""
    return '{"answer_text": "MOCK_ANSWER: data shows X."}'


async def main() -> None:
    print("== Tier 1.2 question log smoke ==")
    run_id = await _seed_synthetic_run()
    try:
        # 1. Synthesize extraction: P1+auto and P3+not
        ids = await _persist_extracted(run_id, [
            {"category": "Macro & Regime", "text": "P1 auto Q?", "priority": 1, "auto_answerable": True},
            {"category": "Macro & Regime", "text": "P3 manual Q?", "priority": 3, "auto_answerable": False},
        ])
        p1_id, p3_id = ids
        print(f"  ✓ persisted 2 synthetic questions ({p1_id[:8]}..., {p3_id[:8]}...)")

        # 2. Run node_targeted_followup with Sonnet mocked
        state = ResearchState(
            ticker=SYNTH_TICKER, theme_id="", run_id=run_id,
            phase="targeted_followup",
        )
        cat_result = CategoryResult(
            category="Macro & Regime",
            content="Mock category content.",
            score=70,
            key_findings=["finding 1", "finding 2"],
        )
        state.phase_outputs["Macro & Regime"] = cat_result.to_dict()

        with patch("backend.app.graph.nodes.complete", _mock_complete):
            new_state = await nodes.node_targeted_followup(state)

        async with async_session() as db:
            p1 = (await db.execute(select(Question).where(Question.id == p1_id))).scalar_one()
            assert p1.status == "resolved_auto", f"expected resolved_auto, got {p1.status}"
            assert p1.answer_text and "MOCK_ANSWER" in p1.answer_text, "answer_text not populated"
            assert p1.answer_source == "targeted_followup"
            print("  ✓ P1 resolved_auto by node_targeted_followup")

            p3 = (await db.execute(select(Question).where(Question.id == p3_id))).scalar_one()
            assert p3.status == "open", f"expected open, got {p3.status}"
            print("  ✓ P3 still open (priority filter)")

        assert len(new_state.questions_resolved_this_run) == 1
        assert "MOCK_ANSWER" in new_state.questions_resolved_this_run[0]["answer_text"]
        print("  ✓ state.questions_resolved_this_run staged for thesis prompt")

        # 3. Manual dismiss the P3 row (mimics endpoint)
        async with async_session() as db:
            p3 = (await db.execute(select(Question).where(Question.id == p3_id))).scalar_one()
            p3.status = "dismissed"
            p3.dismissed_at = datetime.now(timezone.utc)
            p3.dismiss_note = "smoke dismissal"
            await db.commit()
        print("  ✓ P3 dismissed")

        # 4. Synthesize a P2 open question, then test cross-run resurfacing query
        await _persist_extracted(run_id, [
            {"category": "Macro & Regime", "text": "P2 fresh Q?", "priority": 2, "auto_answerable": False},
        ])

        prior = await nodes._fetch_prior_open_questions(SYNTH_TICKER, "Macro & Regime")
        assert len(prior) == 1, f"expected 1 prior open question, got {len(prior)}"
        assert prior[0]["question_text"] == "P2 fresh Q?"
        assert prior[0]["priority"] == 2
        print("  ✓ cross-run resurfacing query returns P2 only (P1 resolved, P3 dismissed)")

        rendered = nodes._render_prior_questions_slot(prior)
        assert "P2 fresh Q?" in rendered, "rendered slot missing question text"
        assert prior[0]["id"] in rendered, "rendered slot missing question id"
        print("  ✓ prior-questions prompt slot renders correctly")

        print("\n✅ Tier 1.2 smoke 4/4 PASS")
    except (AssertionError, ValueError) as e:
        print(f"\n❌ FAIL: {e}")
        await _cleanup(run_id)
        sys.exit(1)
    except Exception:
        await _cleanup(run_id)
        raise

    await _cleanup(run_id)
    print("✓ cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
