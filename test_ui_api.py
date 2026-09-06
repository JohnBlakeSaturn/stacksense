"""Regression checks for skill navigation and role chart data.
Run against a running API: python3 test_ui_api.py
"""
import json
import unittest
from urllib.parse import quote
from urllib.request import Request, urlopen


def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    with urlopen(Request('http://127.0.0.1:8000' + path, data=data,
                         headers={'Content-Type': 'application/json'}), timeout=30) as response:
        return json.load(response)


class NavigationAndCharts(unittest.TestCase):
    def test_slash_skill_and_trend(self):
        path = quote('Torch/PyTorch', safe='')
        skill = request('/skills/' + path)
        self.assertEqual(skill['canonical'], 'Torch/PyTorch')
        trend = request('/trends/' + path)
        self.assertEqual(trend['skill'], 'Torch/PyTorch')
        self.assertEqual(skill['trend']['rank_series'], trend['rank_series'])
        self.assertGreater(len(trend['rank_series']), 1)

    def test_seniority_chart_denominator_and_order(self):
        role = next(r for r in request('/roles')['roles'] if r['name'] == 'Data Engineer')
        for level in ['junior', 'senior']:
            gap = request('/roles/gap', {'skills': ['Python', 'SQL'],
                                         'role': role['name'], 'seniority': level})
            self.assertEqual(gap['postings_analysed'], role['by_seniority'][level])
            for row in gap['you_have'] + gap['gaps']:
                self.assertEqual(row['support'], row['by_seniority'][level])
                self.assertGreater(row['support'], 0)
                self.assertLessEqual(row['support'], 1)
            scores = [r['support'] * max(r['lift'], .1) for r in gap['gaps']]
            self.assertEqual(scores, sorted(scores, reverse=True))


if __name__ == '__main__':
    unittest.main()
