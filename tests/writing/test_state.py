def test_init_state_sets_defaults():
    import sys, types
    # stub streamlit before importing state
    st_stub = types.ModuleType("streamlit")
    ss = {}
    st_stub.session_state = ss
    sys.modules["streamlit"] = st_stub

    # must re-import after stub
    if "core.writing.ui.state" in sys.modules:
        del sys.modules["core.writing.ui.state"]

    from core.writing.ui.state import init_state
    init_state()

    assert ss["writing_phase"] == "idle"
    assert ss["writing_task_type"] is None
    assert ss["writing_topic"] is None
    assert ss["writing_essay"] == ""
    assert ss["writing_eval_result"] is None
