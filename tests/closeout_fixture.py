def prepare_success(store, run_id, summary="Observed reason"):
    return store.closeout_record(run_id, summary, "Synthetic text-only test outcome", "passed", "Synthetic verified observation", "No external delivery or execution is exercised", no_artifact_reason="The synthetic test produces no user file")
