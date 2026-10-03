import unittest

class CurrentCompanionBindingsTests(unittest.TestCase):
    def test_two_exact_current_bindings_and_no_name_inference(self):
        from dots_panel.companion_sources import installation_observations,scheduler_is_bundled
        observations=installation_observations({'current_companion_scheduler_bindings':[{'component':'scheduler_configuration','status':'verified','reference':key,'source_reference':'Synthetic returned configuration','explicit_current_binding':True} for key in ('task-a','task-b')]})
        for key in ('task-a','task-b'):
            self.assertTrue(scheduler_is_bundled({'platform_observation':{'task_id':key,'enabled':False}},observations))
        self.assertFalse(scheduler_is_bundled({'name':'Panel bundled','platform_observation':{'task_id':'other'}},observations))
    def test_empty_current_set_does_not_reuse_old_binding(self):
        from dots_panel.companion_sources import installation_observations,scheduler_is_bundled
        observations=installation_observations({'current_companion_scheduler_bindings':[],'installation_observations':[{'component':'scheduler_configuration','status':'verified','reference':'old'}]})
        self.assertFalse(scheduler_is_bundled({'platform_observation':{'task_id':'old'}},observations))
