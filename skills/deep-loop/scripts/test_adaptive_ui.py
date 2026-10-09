import copy
import unittest
import deep_loop


class AdaptiveExplorationTests(unittest.TestCase):
    def route(self):
        return {'kind': 'greenfield', 'options': ['Compact', 'Editorial', 'Dashboard'],
                'selectedDirection': 'Compact', 'selection': {'source': 'user', 'evidence': 'Owner picked Compact'},
                'designProvenance': {'route': 'product-design', 'evidence': 'Design packet'},
                'mobbin': {'status': 'no_comparable', 'evidence': 'Inspected library'},
                'affectedSurfaces': ['settings'], 'plannedEvidence': ['Rendered responsive proof']}

    def issues(self, route):
        return deep_loop.schema_four_issues({'uiRoute': route})

    def test_material_choice_allows_two_or_three_options(self):
        for count in (2, 3):
            route = self.route()
            route.update(exploration='material_choice', options=route['options'][:count])
            self.assertEqual(self.issues(route), [])

    def test_broad_and_legacy_require_three_options(self):
        for exploration in (None, 'broad'):
            route = self.route()
            if exploration:
                route['exploration'] = exploration
            self.assertEqual(self.issues(route), [])
            route['options'] = route['options'][:2]
            self.assertTrue(self.issues(route))

    def test_unknown_exploration_is_not_a_count_bypass(self):
        for exploration in ('quick', '', None, True, []):
            route = self.route()
            route['exploration'] = exploration
            self.assertTrue(self.issues(route))

    def test_material_choice_keeps_selection_and_provenance_gates(self):
        route = self.route()
        route.update(exploration='material_choice', options=route['options'][:2])
        mutations = [('selection', {'source': 'assistant', 'evidence': 'Suggested'}),
                     ('selectedDirection', 'Other'), ('designProvenance', {}), ('mobbin', {})]
        for key, value in mutations:
            changed = copy.deepcopy(route)
            changed[key] = value
            self.assertTrue(self.issues(changed))
        for options in (['Compact'], ['Compact'] * 2, ['Compact', 'Compact '], ['Compact', 'Editorial', 'Dashboard', 'Other']):
            changed = copy.deepcopy(route)
            changed['options'] = options
            self.assertTrue(self.issues(changed))


if __name__ == '__main__': unittest.main()
