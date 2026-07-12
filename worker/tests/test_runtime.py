from billie_flow_worker.runtime import _normalise_model_output


def test_normalises_only_common_model_wrappers():
    assert _normalise_model_output('  "Hello there."  ') == "Hello there."
    assert _normalise_model_output("```text\nHello there.\n```") == "Hello there."
    assert _normalise_model_output("A 'quoted' word") == "A 'quoted' word"
