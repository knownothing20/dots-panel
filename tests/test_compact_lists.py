"""Recovery-time checks for compact Activities rendering; not a retained original."""
from pathlib import Path
import unittest
from dots_panel.app import ROOT

class ReconstructedCompactTests(unittest.TestCase):
    def test_activities_use_shared_filter_and_separate_search(self):
        js=(ROOT/'web/app.js').read_text()
        self.assertIn("PanelWorkspace.rows(state.tasks,state.latest_runs||state.runs,workspaceFilter,workspaceQuery)",js)
        self.assertIn("PanelWorkspace.rows(state.tasks,state.latest_runs||state.runs,workspaceFilter)",js)
    def test_activity_cards_are_compact_css(self):
        css=(ROOT/'web/style.css').read_text()
        self.assertIn('#task-list.task-grid{display:flex;flex-direction:column',css)
    def test_all_seven_navigation_destinations(self):
        html=(ROOT/'web/index.html').read_text()
        for page in ('overview','conversations','agents','schedules','software','rules','about'):
            self.assertEqual(html.count('data-nav="'+page+'"'),1)
            self.assertEqual(html.count('data-page="'+page+'"'),1)
