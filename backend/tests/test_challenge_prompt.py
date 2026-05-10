import unittest
from backend.app.graph.workspace_prompts import CHALLENGE_SYSTEM, CHALLENGE_USER_TEMPLATE


class TestChallengePrompt(unittest.TestCase):
    def test_system_prompt_long_enough_for_caching(self):
        self.assertGreater(len(CHALLENGE_SYSTEM), 500)

    def test_user_template_has_required_slots(self):
        for slot in ("prior_thesis", "kill_criteria", "catalysts", "model_deltas", "new_sources"):
            self.assertIn("{" + slot + "}", CHALLENGE_USER_TEMPLATE)

    def test_system_prompt_locks_verdict_vocab(self):
        for verdict in ("healthy", "imminent", "triggered", "broken"):
            self.assertIn(verdict, CHALLENGE_SYSTEM)
