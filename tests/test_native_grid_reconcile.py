"""Headless regressions for retained card membership and responsive placement."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from dots_panel.desktop_view import Dashboard
from test_native_retained_updates import Canvas, Widget


class StrictGridMixin:
    def grid(self, **kwargs):
        if not self.exists:
            raise RuntimeError('grid called on a destroyed widget')
        self.managed = True
        self.position = (kwargs['row'], kwargs['column'])
        self.grid_calls = getattr(self, 'grid_calls', 0) + 1


class GridWidget(StrictGridMixin, Widget):
    pass


class GridCanvas(StrictGridMixin, Canvas):
    pass


class CardGridReconcileTests(unittest.TestCase):
    def view(self):
        v = Dashboard.__new__(Dashboard)
        v.tk = SimpleNamespace(Frame=GridWidget, Canvas=GridCanvas, Label=GridWidget)
        v.root = Mock()
        v.language = 'en'
        v.font = 'sans'
        v.bg = v.panel = 'white'
        v.fg = 'black'
        v.muted = 'gray'
        v.accent = 'green'
        v.live_updates = []
        v.snapshot = {}
        v.workspace_filter = 'all'
        v.search_query = SimpleNamespace(get=lambda: '')
        v.workspace_toolbar = Mock()
        v.backup_card = Mock(return_value=lambda: None)
        v.area = GridWidget()
        v.scroll_area = lambda: v.area
        v.resource_card = lambda parent: GridCanvas(parent)
        v.schedules_summary_card = lambda parent: GridCanvas(parent)
        v.output_button = lambda *args: None
        v.t = lambda text, **values: text.format(**values)
        return v

    def rows(self, keys):
        return [{'id': key, 'status': 'running', 'warning': '',
                 'values': (key, '', 'Running', '', '', ''),
                 'run': {'id': 'run-' + key}} for key in keys]

    def assert_positions(self, grid, expected):
        self.assertEqual(len(grid.card_items), len(expected))
        self.assertEqual([card.position for card in grid.card_items],
                         [(index // 2, index % 2) for index in range(len(expected))])
        self.assertTrue(all(card.exists for card in grid.card_items))
        self.assertEqual(grid.card_items, expected)

    def test_overview_four_to_three_to_four_and_reorder_retains_cards(self):
        v = self.view()
        v.rows = self.rows('abcd')
        v.render_overview()
        grid = next(child for child in v.area.children if hasattr(child, 'card_items'))
        a, b, c, d = grid.card_items
        self.assert_positions(grid, [a, b, c, d])
        v.rows = self.rows('bcd')
        v.background_refresh()
        self.assert_positions(grid, [b, c, d])
        self.assertEqual(a.deleted, 1)
        v.rows = self.rows('ebcd')
        v.background_refresh()
        e = grid.card_items[0]
        self.assert_positions(grid, [e, b, c, d])
        v.rows = self.rows('dceb')
        v.background_refresh()
        self.assert_positions(grid, [d, c, e, b])
        before = [card.grid_calls for card in grid.card_items]
        v.background_refresh()
        self.assertEqual([card.grid_calls for card in grid.card_items], before)
        self.assertTrue(all(card.deleted == 0 for card in [b, c, d, e]))
        self.assertEqual(len(grid.children), 5, 'Only the newly added card was constructed')

    def test_same_size_front_replacement_does_not_layout_destroyed_card(self):
        v = self.view()
        v.rows = self.rows('abcd')
        v.render_overview()
        grid = next(child for child in v.area.children if hasattr(child, 'card_items'))
        a, b, c, d = grid.card_items
        v.rows = self.rows('ebcd')
        v.background_refresh()
        e = grid.card_items[0]
        self.assert_positions(grid, [e, b, c, d])
        self.assertEqual(a.deleted, 1)
        self.assertTrue(all(card.deleted == 0 for card in [b, c, d, e]))

    def test_resize_after_destroy_prunes_stale_slots_without_rebuilding(self):
        v = self.view()
        grid = v.card_grid(v.area, minimum=370, maximum=2)
        a, b, c, d = [GridCanvas(grid) for _ in range(4)]
        grid.card_items = [a, b, c, d]
        grid.reflow_cards()
        a.destroy()
        grid.reflow_cards(SimpleNamespace(width=800))
        self.assert_positions(grid, [b, c, d])
        grid.reflow_cards(SimpleNamespace(width=380))
        self.assertEqual(grid.card_items, [b, c, d])
        self.assertEqual([card.position for card in grid.card_items], [(0, 0), (1, 0), (2, 0)])


if __name__ == '__main__':
    unittest.main()
