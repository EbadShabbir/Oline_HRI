"""Bounded software plans must honor counts and cannot override extra constraints."""

from copy import deepcopy
import unittest

from oline_hri.operational_planning import compose_operational_plan
from oline_hri.conversation import Conversation
from oline_hri.evaluation import load_evaluation_suite
from oline_hri.evaluation_scoring import _cascade, EvaluationScoringError
from oline_hri.response import ResponseValidationError
from test_grounded_composition import SchemaBackend
from test_conversation_routed import FakeRouter, FakeRetriever, routing_result
from test_evaluation_scoring import _raw_records


class OperationalPlanningTests(unittest.TestCase):
    def test_supported_original_cases_have_concrete_bounded_plans(self):
        suite = load_evaluation_suite()
        for n in (9, 12, 14):
            result = compose_operational_plan(suite.cases[n - 1].prompt)
            self.assertIsNotNone(result)
            self.assertLessEqual(len(result.speech.split()), 80)
            self.assertLessEqual(len(result.speech), 850)
        validation = compose_operational_plan(suite.cases[8].prompt).speech
        for n in range(1, 6):
            self.assertIn(f'{n}.', validation)
        self.assertEqual(validation.count('stop on'), 5)
        self.assertLessEqual(len(validation.split()), 60)
        self.assertIn('isolated copies', validation)
        self.assertIn('roll back', validation)

    def test_new_counts_and_domains_not_just_fixture_names(self):
        result = compose_operational_plan('Give a three-stage test plan for an offline speech assistant.')
        self.assertEqual(result.speech.count('stop on'), 3)
        self.assertNotIn('4.', result.speech)
        self.assertIsNotNone(compose_operational_plan('Plan a three-stage release of a disconnected Python kiosk.'))

    def test_absent_backup_is_not_invented_or_assumed(self):
        speech = compose_operational_plan('Give a recovery plan for a corrupt local database with no verified backup.').speech
        self.assertNotIn('Restore a verified', speech)
        self.assertIn('work on a copy', speech)
        self.assertIn('cannot be guaranteed', speech)
        self.assertIn('Verify row counts', speech)

    def test_unsupported_counts_formats_domains_and_constraints_decline(self):
        for request in (
            'Give a two-stage test plan for an offline assistant.',
            'Give an eight-stage release plan for an offline kiosk.',
            'Give a three-stage test plan for an offline assistant in JSON.',
            'Give a three-stage test plan for an offline assistant; omit data corruption.',
            'Give a three-stage test plan for an offline assistant without corrupting data.',
            'Give a three-stage test plan for an offline assistant in Spanish.',
            'Plan a release of an offline service without verified backups.',
            'Give a three-stage test plan for an offline assistant that must not write files.',
            'Give a three-stage medical treatment plan.',
            'Give a three-stage plan for local travel.',
            'Give a three-stage test plan for an offline assistant with a budget.',
            'Give a three-stage test plan for an offline assistant in two hours.',
        ):
            with self.subTest(request=request):
                self.assertIsNone(compose_operational_plan(request))

    def test_runtime_uses_one_small_decode_with_no_personal_citations(self):
        backend = SchemaBackend()
        convo = Conversation(backend, system_prompt='Be safe.',
            router=FakeRouter((routing_result(False, 'large'),)), retriever=FakeRetriever(),
            small_model='qwen3:0.6b', general_large_model='qwen3:1.7b', large_model='qwen3:1.7b')
        reply = convo.send('Give a three-stage validation plan for a local software service.')
        self.assertEqual(reply.generation.model, 'qwen3:0.6b')
        self.assertEqual(reply.generation_policy, 'verified_constraint_small')
        self.assertEqual(reply.answer_constraint, 'bounded_software_validation')
        self.assertEqual(reply.response.memory_used, ())
        self.assertEqual(len(backend.calls), 1)

    def test_untrusted_backend_cannot_change_the_runbook(self):
        convo = Conversation(SchemaBackend(speech='I will provide a plan later.'), system_prompt='Be safe.',
            router=FakeRouter((routing_result(False, 'large'),)), retriever=FakeRetriever(),
            small_model='qwen3:0.6b', large_model='qwen3:1.7b')
        with self.assertRaisesRegex(ResponseValidationError, 'verified composition'):
            convo.send('Give a three-stage validation plan for a local software service.')

    def test_scoring_separates_runbooks_from_memory_compositions(self):
        record = next(r['cascade'] for r in _raw_records() if r.get('record_type') == 'case'
                      and not r['cascade']['retrieval_invoked'])
        valid = deepcopy(record)
        valid['answer_constraint'] = 'bounded_software_release'
        self.assertEqual(_cascade(valid)['answer_constraint'], 'bounded_software_release')
        for key, value in (('retrieval_invoked', True), ('privacy_gate', True),
                           ('answer_constraint', 'verified_presentation_plan')):
            invalid = deepcopy(valid)
            invalid[key] = value
            with self.assertRaises(EvaluationScoringError):
                _cascade(invalid)
