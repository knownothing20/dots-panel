"""Native backup card patches only its own labels; no display or real data."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from dots_panel.desktop_view import Dashboard
from test_native_retained_updates import Widget


class BackupNativeTests(unittest.TestCase):
    def view(self):
        v=Dashboard.__new__(Dashboard)
        v.tk=SimpleNamespace(Frame=Widget)
        v.root=Mock();v.language='en';v.accent='green';v.muted='gray';v.panel='white'
        v.snapshot={'backup':{'status':'unconfigured'}}
        v.stamp=lambda value:'LOCAL_TIME'
        card,box=Widget(),Widget()
        v.card=Mock(return_value=(card,box))
        v.label=Mock(side_effect=lambda *args,**kwargs:Widget())
        v.filter_chip=Mock(return_value=Widget())
        v.fit_card=Mock();v.navigate=Mock();v.render_page=Mock()
        return v,card,box

    def test_readonly_card_retains_widgets_and_fits_once(self):
        v,card,box=self.view()
        refresh=v.backup_card(Widget())
        labels=v.label.call_count
        v.snapshot['backup']={'status':'unavailable','state_dir':'/private/synthetic/state'}
        refresh();refresh()
        self.assertEqual(v.label.call_count,labels)
        self.assertEqual(v.card.call_count,1)
        self.assertEqual(v.fit_card.call_count,1)
        v.render_page.assert_not_called()
        self.assertTrue(card.exists)

    def test_compact_card_navigation_is_only_action(self):
        v,card,box=self.view()
        refresh=v.backup_card(Widget(),compact=True)
        self.assertEqual(v.filter_chip.call_count,1)
        v.filter_chip.call_args.args[2]()
        v.navigate.assert_called_once_with('settings')
        refresh();v.root.clipboard_append.assert_not_called()

    def test_explicit_copy_does_not_open_remote_or_change_files(self):
        v,card,box=self.view()
        v.snapshot={'backup':{'status':'unconfigured','destination':{'provider':'ChatGPT Library','label':'Synthetic','path':'/private/synthetic'}}}
        v.backup_card(Widget())
        v.filter_chip.call_args.args[2]()
        v.root.clipboard_append.assert_called_once_with('/private/synthetic')
        v.navigate.assert_not_called()
