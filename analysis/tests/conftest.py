"""Test types. Every test carries at least one of: unit, integration, e2e, regression, acceptance, security (see docs/TESTING.md).
Run one kind with `python -m pytest -m security` (or unit, integration, e2e, regression, acceptance). A module can also mark tests itself (pytestmark or
@pytest.mark.x); the lists below only add the type for the older modules, by what the module does."""
import pytest

# several parts together: real ffmpeg, files on disk, fake providers and local servers
INTEGRATION = {
    "test_captions", "test_cleanup", "test_comfy", "test_comfy_setup", "test_local_ai", "test_chaining", "test_promptwriter", "test_compose", "test_comfy_install", "test_midjourney", "test_lighting", "test_extend", "test_render_queue", "test_customframe", "test_editor_export", "test_keyframes", "test_layerkit", "test_llm", "test_media",
    "test_native_dialogue", "test_overlays", "test_overnight", "test_pipeline", "test_recorded_dialogue", "test_refgen",
    "test_refgen_cards", "test_render", "test_review", "test_shapes", "test_show", "test_show_finish", "test_stills", "test_supervisor", "test_title_motion",
    "test_titlecard", "test_library", "test_e2e_journey", "test_create_from_song_flow", "test_transitions", "test_lipsync_timing", "test_changes", "test_track",
}
E2E = {"test_e2e_journey", "test_create_from_song_flow"}
# bugs that really happened (real renders, real crashes), kept from coming back
REGRESSION = {"test_video_models", "test_render", "test_replace_retry", "test_tmp_names", "test_crash_report", "test_doc_text", "test_stills", "test_regressions_sound", "test_choreography_scope", "test_offscreen_names", "test_prompt_dedupe", "test_acting_defaults", "test_lipsync_mode", "test_packer_nested", "test_sing_setting", "test_styleguard", "test_review_fix", "test_modelinfo"}
# promises the product makes to the user
ACCEPTANCE = {"test_golden", "test_acceptance", "test_create_from_song_flow", "test_e2e_journey", "test_transitions"}
# hostile input, paths and secrets
SECURITY = {"test_security", "test_fonts", "test_updates", "test_security_sound", "test_security_timeline", "test_packer_nested", "test_upscale", "test_openrouter"}


def pytest_collection_modifyitems(items):
    for item in items:
        name = item.module.__name__.rsplit(".", 1)[-1]
        have = {m.name for m in item.iter_markers()}
        for marker, group in (("integration", INTEGRATION), ("e2e", E2E), ("regression", REGRESSION), ("acceptance", ACCEPTANCE), ("security", SECURITY)):
            if name in group and marker not in have:
                item.add_marker(getattr(pytest.mark, marker))
        have = {m.name for m in item.iter_markers()}
        if not have & {"integration", "e2e"}:
            item.add_marker(pytest.mark.unit)
