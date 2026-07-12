from billie_flow_worker.corrections import RULES, apply_corrections


def test_corrections_are_boundary_aware_case_insensitive_and_receipted():
    corrected, receipts = apply_corrections(
        "bIlLy FlOw on a Mac Book uses Swift UI, M L X and HuggingFace."
    )

    assert corrected == "Billie Flow on a MacBook uses SwiftUI, MLX and Hugging Face."
    assert receipts == [
        {"from": "huggingface", "to": "Hugging Face", "count": 1},
        {"from": "billy flow", "to": "Billie Flow", "count": 1},
        {"from": "mac book", "to": "MacBook", "count": 1},
        {"from": "swift ui", "to": "SwiftUI", "count": 1},
        {"from": "m l x", "to": "MLX", "count": 1},
    ]


def test_longest_first_rules_are_stable_and_count_repeats():
    assert list(RULES) == sorted(RULES, key=lambda rule: (-len(rule.source), rule.source))
    corrected, receipts = apply_corrections("Whisper Flow and whisper flow")
    assert corrected == "Wispr Flow and Wispr Flow"
    assert receipts == [{"from": "whisper flow", "to": "Wispr Flow", "count": 2}]


def test_ambiguous_and_embedded_phrases_are_never_changed():
    source = "Use it with flow, not embilly flowish or swift uihelper."
    corrected, receipts = apply_corrections(source)
    assert corrected == source
    assert receipts == []
