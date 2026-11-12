import copy
import datetime as dt
import json
import unittest

import httpx

from journal.obsidian import JournalError
from journal.planner import PlannerModel, build_planner
from plan_query import main


PLAN = {'questions': [{
    'question': 'Which unfinished tasks mention the synthetic garden project?',
    'target': 'todo', 'search_terms': ['garden', 'garden tasks', 'gardening'], 'entities': [],
    'filters': {'date_start': '2026-11-02', 'date_end': '2026-11-08',
                'source': None, 'checked': False},
}], 'clarification': None}


class PlannerTests(unittest.TestCase):
    def model(self, payload, inspect=None):
        def handler(request):
            if inspect:
                inspect(json.loads(request.content))
            return httpx.Response(200, json=payload)
        return PlannerModel(client=httpx.Client(transport=httpx.MockTransport(handler)))

    def response(self, plan=PLAN, finish='stop'):
        return {'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(plan)}}]}

    def test_real_graph_and_local_structured_request(self):
        def inspect(payload):
            self.assertNotIn('tools', payload)
            self.assertEqual(payload['response_format']['type'], 'json_schema')
            context = json.loads(payload['messages'][1]['content'])
            self.assertEqual(context['reference_date'], '2026-11-11')
            self.assertEqual(context['timezone'], 'America/Los_Angeles')
            self.assertEqual(context['calendar_ranges']['last week'], ['2026-11-02', '2026-11-08'])
            self.assertEqual(context['calendar_ranges']['last month'], ['2026-10-01', '2026-10-31'])
        with self.model(self.response(), inspect).client as client:
            graph = build_planner(PlannerModel(client=client))
            result = graph.invoke({'query': 'What garden tasks are unfinished from last week?',
                                   'reference_date': '2026-11-11', 'timezone': 'America/Los_Angeles'})
        self.assertEqual(result['plan'], PLAN)

    def test_malformed_plans_fail_without_echoing_content(self):
        invalid = []
        for change in ['date', 'target', 'checked', 'extra', 'empty', 'clarification']:
            plan = copy.deepcopy(PLAN)
            question = plan['questions'][0]
            if change == 'date':
                question['filters']['date_end'] = '2026-10-01'
            elif change == 'target':
                question['target'] = 'arbitrary_sql'
            elif change == 'checked':
                question['target'] = 'document'
            elif change == 'extra':
                plan['private_text'] = 'PRIVATE_SENTINEL'
            elif change == 'empty':
                plan['questions'] = []
            else:
                plan['clarification'] = 'PRIVATE_SENTINEL'
            invalid.append(self.response(plan))
        invalid.extend([{}, self.response(finish='length'),
                        {'choices': [{'finish_reason': 'stop', 'message': {'content': 'PRIVATE_SENTINEL'}}]}])
        for payload in invalid:
            with self.subTest(payload=payload), self.model(payload).client as client:
                with self.assertRaises(JournalError) as error:
                    PlannerModel(client=client).plan('synthetic', '2026-11-11', 'America/Los_Angeles')
                self.assertNotIn('PRIVATE_SENTINEL', str(error.exception))

    def test_clarification_and_run_isolation(self):
        requests = []
        plan = {'questions': [], 'clarification': 'Which project do you mean?'}
        with self.model(self.response(plan), requests.append).client as client:
            graph = build_planner(PlannerModel(client=client))
            for query in ['How did that project go?', 'What about that person?']:
                result = graph.invoke({'query': query, 'reference_date': '2026-11-11',
                                       'timezone': 'America/Los_Angeles'})
                self.assertEqual(result['plan'], plan)
        self.assertEqual(len(requests[1]['messages']), 2)
        self.assertNotIn('How did that project go?', requests[1]['messages'][1]['content'])

    def test_one_validation_retry_can_recover(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            payload = self.response({'questions': [], 'clarification': None}) if len(requests) == 1 else self.response()
            return httpx.Response(200, json=payload)
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = PlannerModel(client=client).plan('synthetic', '2026-11-11', 'America/Los_Angeles')
        self.assertEqual(result.model_dump(mode='json'), PLAN)
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(requests[1]['messages']), 2)

    def test_invalid_response_retry_is_bounded(self):
        requests = []
        with self.model(self.response({'questions': [], 'clarification': None}), requests.append).client as client:
            with self.assertRaisesRegex(JournalError, 'planner_invalid_response'):
                PlannerModel(client=client).plan('synthetic', '2026-11-11', 'America/Los_Angeles')
        self.assertEqual(len(requests), 2)

    def test_search_terms_require_three_distinct_short_phrases(self):
        invalid = [[], ['work'], ['work', 'work reflections'],
                   ['work', 'Work', 'work reflections'],
                   ['work', 'work reflections', 'What happened at work?'],
                   ['work', 'work reflections', 'one two three four five six seven eight nine'],
                   ['work', 'work reflections', 'work\nfeelings']]
        for terms in invalid:
            plan = copy.deepcopy(PLAN)
            plan['questions'][0]['search_terms'] = terms
            with self.subTest(terms=terms), self.model(self.response(plan)).client as client:
                with self.assertRaisesRegex(JournalError, 'planner_invalid_response'):
                    PlannerModel(client=client).plan('synthetic', '2026-11-11', 'America/Los_Angeles')

    def test_search_phrase_bounds_are_in_response_schema(self):
        from journal.planner import RetrievalPlan
        terms = RetrievalPlan.model_json_schema()['$defs']['RetrievalQuestion']['properties']['search_terms']
        self.assertEqual(terms['minItems'], 3)
        self.assertEqual(terms['maxItems'], 12)
        self.assertEqual(terms['items']['maxLength'], 100)

    def test_invalid_inputs_make_no_model_call(self):
        def unexpected(payload):
            self.fail('invalid input must not reach model')
        with self.model(self.response(), unexpected).client as client:
            graph = build_planner(PlannerModel(client=client))
            for updates in [{'query': ' '}, {'reference_date': 'not a date'}, {'timezone': 'invalid'}]:
                state = {'query': 'synthetic', 'reference_date': '2026-11-11', 'timezone': 'America/Los_Angeles'}
                state.update(updates)
                with self.assertRaises(JournalError):
                    graph.invoke(state)
            with self.assertRaisesRegex(JournalError, 'input_too_large'):
                PlannerModel(client=client, context_budget=10).plan('synthetic', '2026-11-11', 'America/Los_Angeles')

    def test_clock_refreshes_each_query_across_local_midnight(self):
        requests = []
        times = iter([dt.datetime(2026, 11, 12, 7, 59, tzinfo=dt.timezone.utc),
                      dt.datetime(2026, 11, 12, 8, 1, tzinfo=dt.timezone.utc)])
        with self.model(self.response(), requests.append).client as client:
            graph = build_planner(PlannerModel(client=client), clock=lambda: next(times))
            first = graph.invoke({'query': 'What happened yesterday?'})
            second = graph.invoke({'query': 'What happened yesterday?'})
        self.assertEqual(first['reference_date'], '2026-11-11')
        self.assertEqual(second['reference_date'], '2026-11-12')
        self.assertEqual(first['current_datetime'], '2026-11-11T23:59:00-08:00')
        context = json.loads(requests[1]['messages'][1]['content'])
        self.assertEqual(context['date_source'], 'clock')
        self.assertEqual(context['calendar_ranges']['yesterday'], ['2026-11-11', '2026-11-11'])

    def test_explicit_date_override_preserves_actual_datetime(self):
        requests = []
        now = dt.datetime(2027, 1, 1, 12, tzinfo=dt.timezone.utc)
        with self.model(self.response(), requests.append).client as client:
            graph = build_planner(PlannerModel(client=client), clock=lambda: now)
            result = graph.invoke({'query': 'What happened last week?', 'reference_date': '2026-11-11'})
        self.assertEqual(result['date_source'], 'override')
        self.assertEqual(result['current_datetime'], '2027-01-01T04:00:00-08:00')
        context = json.loads(requests[0]['messages'][1]['content'])
        self.assertEqual(context['reference_date'], '2026-11-11')
        self.assertEqual(context['calendar_ranges']['last week'], ['2026-11-02', '2026-11-08'])

    def test_cli_invalid_timezone(self):
        self.assertEqual(main(['synthetic', '--timezone', 'invalid']), 1)
