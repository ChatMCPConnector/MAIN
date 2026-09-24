from glm2api.config import BUILTIN_EXPOSED_MODELS
from glm2api.model_variants import expand_model_variants, split_model_features
from glm2api.services.translator import resolve_chat_mode, resolve_networking, resolve_upstream_model


class _Config:
    glm_assistant_id = "65940acff94777010aa6b796"


def test_expand_model_variants_adds_think_search_and_combined_suffixes():
    models = expand_model_variants(("glm-4", "glm-image-1"), excluded_models={"glm-image-1"})

    assert models == [
        "glm-4",
        "glm-4-think",
        "glm-4-search",
        "glm-4-think-search",
        "glm-image-1",
    ]


def test_split_model_features_accepts_think_search_in_either_order():
    assert split_model_features("glm-4-think-search") == ("glm-4", {"think", "search"})
    assert split_model_features("glm-4-search-think") == ("glm-4", {"think", "search"})
    assert split_model_features("glm-deep-research") == ("glm-deep-research", set())


def test_variant_model_resolves_to_base_upstream_model():
    upstream_model, assistant_id = resolve_upstream_model("glm-4-think-search", _Config())

    assert upstream_model == "glm-4"
    assert assistant_id == _Config.glm_assistant_id


def test_assistant_id_model_name_is_used_as_assistant_id():
    # Ein modellname, der selbst eine 24-stellige hex-id ist, wird als
    # assistant_id interpretiert.
    upstream_model, assistant_id = resolve_upstream_model("65940acff94777010aa6b797", _Config())

    assert upstream_model == "65940acff94777010aa6b797"
    assert assistant_id == "65940acff94777010aa6b797"


def test_model_suffixes_resolve_chat_mode_and_networking_matrix():
    assert resolve_chat_mode("glm-4-think", None, None) == "thinking"
    assert resolve_networking("glm-4-think", None) is False

    assert resolve_chat_mode("glm-4-search", None, None) == ""
    assert resolve_networking("glm-4-search", None) is True

    assert resolve_chat_mode("glm-4-think-search", None, None) == "thinking"
    assert resolve_networking("glm-4-think-search", None) is True

    assert resolve_chat_mode("glm-4", None, None) == ""
    assert resolve_networking("glm-4", None) is False


def test_existing_thinking_model_name_still_enables_chat_mode():
    assert resolve_chat_mode("glm-4.1v-thinking-flashx", None, None) == "thinking"


def test_glm_5_2_is_exposed():
    assert "glm-5.2" in BUILTIN_EXPOSED_MODELS


def test_glm_5_3_is_exposed():
    assert "glm-5.3" in BUILTIN_EXPOSED_MODELS
