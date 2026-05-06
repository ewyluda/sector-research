import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.graph import nodes


class TargetedFollowupPromptTests(unittest.TestCase):
    def test_prompt_includes_original_routed_payload_context(self) -> None:
        msg = nodes._build_targeted_followup_user_msg(
            question_text="How much RPO is tied to AI infrastructure?",
            category="Growth & Earnings",
            key_findings=["RPO grew sequentially"],
            analysis="The published analysis summarized backlog.",
            routed_context=(
                "SEC EDGAR XBRL facts:\n"
                "RevenueRemainingPerformanceObligation [2025 Q4]: $12.30B"
            ),
        )

        self.assertIn("Original data payload and routed context", msg)
        self.assertIn("RevenueRemainingPerformanceObligation", msg)
        self.assertIn("$12.30B", msg)


if __name__ == "__main__":
    unittest.main()
