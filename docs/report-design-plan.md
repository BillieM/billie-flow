# Report Design Plan

Status: implemented in `reports/voice-memo.html`.

The report is a BillieM artefact: editorial, direct, slightly rough-edged, and
built for making a decision rather than admiring a dashboard.

## Design Goals

- Make the branching pipeline visible.
- Make the recommended path obvious.
- Let the user compare outputs through a diagram first, then click into evidence
  only when needed.
- Preserve transcript and failure evidence in the cleaned results contract, not
  by embedding raw runner JSON in the public page.
- Avoid generic card-heavy AI-dashboard styling.
- Avoid over-polishing the language; the report should sound like an engineer
  reviewing evidence.

## Information Architecture

First viewport:

- title: `Voice Memo ASR Bake-off`
- recommended path summary
- one-line verdict
- compact branch diagram

Main sections:

1. **Pipeline Tree**
   Diagram from audio to chunker to ASR to cleanup model to style.

2. **Recommended Defaults**
   The chosen ASR/cleanup/style combination, with reasons and caveats.

3. **ASR Evidence**
   Compact branch rows with transcript excerpts hidden behind details elements,
   highlighting vocabulary errors when opened.

4. **Cleanup Examples**
   A curated set of useful style outputs, not every model/style combination.

5. **Vocabulary Failures**
   Explicit list of terms that models got wrong:
   `Wispr Flow`, `Billie Flow`, `LLM`, `MacBook`.

6. **Method**
   Short explanation of the clip, split ASR/cleanup stages, model statuses, and
   why raw runner files are not embedded.

7. **App Implications**
   What this means for the Swift app defaults and manual settings.

## Diagram Requirements

The report should include a visual branch tree.

Minimum tree:

```text
Source voice memo
  -> normalize 16 kHz mono
    -> whole-file
      -> mlx-whisper-large-v3-turbo
        -> stitched transcript
          -> cleanup model
            -> verbatim-context-corrected
            -> light-cleanup
            -> notes
    -> fixed-25s-overlap-2s
      -> gemma-4-12b-audio
    -> long-form
      -> voxtral-mini-3b
```

The recommended branch should be visually highlighted.

## Visual Direction

Use restrained, editorial styling:

- warm off-white page background
- strong black/dark text
- restrained accent colours
- high-quality typography using system fonts
- narrow reading columns for prose
- dense comparison tables where needed
- thin rules and clear hierarchy
- exact BillieM shared chrome snapshot
- no glossy gradient-orb decoration
- no generic SaaS hero treatment

Cards are acceptable for selected outputs, but page sections should not look
like nested card soup. The page should use the BillieM `58rem` width, system
type, muted metadata, thin rules, and restrained purple accent.

## Interaction

The report is static HTML. It may use small inline JavaScript only when it makes
comparison easier.

Useful interactions:

- expand/collapse ASR evidence
- highlight known vocabulary terms and observed errors

Do not require a dev server to view the report.

Do not embed raw runner JSON, full prompts, raw responses, or raw path
breadcrumbs in the public artifact. Keep local raw output ignored by Git.

## Review Voice

The reviewer copy should be blunt and useful:

- "Best current default"
- "Good smoke test, not good enough for quality"
- "This output hid an ASR mistake"
- "Too polished for Billie-style dictation"
- "Fast enough for app use"

Avoid vague praise like "impressive" unless it is tied to evidence.
