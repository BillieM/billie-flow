from __future__ import annotations

import json

from billie_flow_worker import prefetch


class StubRuntime:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    def load_asr(self) -> None:
        self.loaded.append("asr")

    def load_cleanup(self) -> None:
        self.loaded.append("cleanup")


def test_prefetch_can_install_each_fixed_model_separately(monkeypatch, capsys):
    runtimes: list[StubRuntime] = []

    def make_runtime() -> StubRuntime:
        runtime = StubRuntime()
        runtimes.append(runtime)
        return runtime

    monkeypatch.setattr(prefetch, "MLXRuntime", make_runtime)

    assert prefetch.main(["--component", "asr"]) == 0
    asr_payload = json.loads(capsys.readouterr().out)
    assert asr_payload["component"] == "asr"
    assert runtimes[-1].loaded == ["asr"]

    assert prefetch.main(["--component", "cleanup"]) == 0
    cleanup_payload = json.loads(capsys.readouterr().out)
    assert cleanup_payload["component"] == "cleanup"
    assert runtimes[-1].loaded == ["cleanup"]


def test_prefetch_defaults_to_both_models(monkeypatch, capsys):
    runtime = StubRuntime()
    monkeypatch.setattr(prefetch, "MLXRuntime", lambda: runtime)

    assert prefetch.main([]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["component"] == "all"
    assert runtime.loaded == ["asr", "cleanup"]
