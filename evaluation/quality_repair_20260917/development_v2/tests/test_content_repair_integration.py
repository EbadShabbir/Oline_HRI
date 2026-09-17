"""Source quantities and factual checks reach the actual delivery boundary."""
import json
import unittest
from test_conversation_routed import FakeBackend, GENERAL_LARGE_MODEL, chat_result
from test_reliable_conversation import reliable, semantic_route


def parts(values):
    return chat_result(raw=json.dumps({"answer_parts": values}), model=GENERAL_LARGE_MODEL)


class ContentRepairTests(unittest.TestCase):
    def test_arithmetic_is_computed_and_original_expression_retained(self):
        raw = parts(["5*6+2"])
        backend = FakeBackend((raw,))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        reply = session.send("There are 5 marbles in each of 6 jars and 2 extra marbles. How many altogether? Return only the whole number.")
        self.assertEqual(reply.response.speech, "32")
        self.assertIs(reply.generation, raw)
        self.assertEqual(reviewer.calls[0]["answer"], "32")
        self.assertEqual(reply.response.memory_used, ())

    def test_fixed_durations_are_checked_before_the_model_reviewer(self):
        bad = parts(["Place the props.", "Arrange three cards."])
        good = parts(["1. Place the props (2 minutes).", "2. Arrange three cards (3 minutes). Total: 5 minutes."])
        backend = FakeBackend((bad, good))
        session, _, _, reviewer = reliable(backend, route=semantic_route(size="large"))
        reply = session.send("Turn these allocations into a 5-minute plan: 2 minutes to place the props, and 3 minutes to arrange three cards. Use exactly two numbered steps and state the total time.")
        self.assertIs(reply.generation, good)
        self.assertIn("supplied_plan_timing", reply.quality_issues)
        self.assertIn("supplied_plan_total", reply.quality_issues)
        self.assertEqual(len(reviewer.calls), 1)
        self.assertIn('"minutes": 2', str(backend.calls))


if __name__ == "__main__":
    unittest.main()
