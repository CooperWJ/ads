"""同条件对照必须拒绝 JSON 布尔/数字的隐式相等。"""
import copy
import unittest
from ads.benchmark import compare
from ads.project import Blocked

class BenchmarkInputTests(unittest.TestCase):
    def observation(self):
        return {'schema':'ads-benchmark-observations/v1','model':'synthetic/model',
                'budget':{'seconds':1},'runs':[{'case_id':'fictional','seed':1,'split':'fresh',
                'evidence_ref':'synthetic-only','cost':0,'duration_seconds':1,
                'requirements':'UNKNOWN','engineering':'FAIL','delivery':'FAIL'}]}

    def test_both_budgets_reject_bool_even_when_equal_to_number(self):
        for field in ('base','candidate'):
            with self.subTest(field=field):
                base=self.observation()
                candidate=copy.deepcopy(base)
                (base if field=='base' else candidate)['budget']['seconds']=True
                with self.assertRaises(Blocked):
                    compare(base,candidate)

    def test_invalid_budget_values_and_models_cannot_pair(self):
        for value in (None,{}, {'seconds':False},{'seconds':float('nan')},
                      {'seconds':float('inf')},{'seconds':0}):
            with self.subTest(value=value):
                base=self.observation()
                candidate=copy.deepcopy(base)
                candidate['budget']=value
                with self.assertRaises(Blocked):
                    compare(base,candidate)
        base=self.observation()
        candidate=copy.deepcopy(base)
        base['model']=candidate['model']=' '
        with self.assertRaises(Blocked):
            compare(base,candidate)

    def test_seed_types_and_empty_case_identity_are_rejected(self):
        for value in (True,1.0,'1',None):
            with self.subTest(seed=value):
                base=self.observation()
                candidate=copy.deepcopy(base)
                candidate['runs'][0]['seed']=value
                with self.assertRaises(Blocked):
                    compare(base,candidate)
        base=self.observation()
        candidate=copy.deepcopy(base)
        base['runs'][0]['case_id']=candidate['runs'][0]['case_id']=' '
        with self.assertRaises(Blocked):
            compare(base,candidate)

    def test_valid_paired_observations_retain_unknowns(self):
        base=self.observation()
        candidate=copy.deepcopy(base)
        candidate['runs'][0]['requirements']='PASS'
        result=compare(base,candidate)
        self.assertEqual(result['paired_runs'],1)
        self.assertEqual(result['axes']['requirements']['base']['unknown'],1)
        self.assertEqual(result['axes']['requirements']['candidate']['pass'],1)
