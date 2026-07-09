"""Regression tests for the Open WebUI tool source (it ships as a string)."""

from smallwonder.openwebui_tool import TOOL_CONTENT


# --- issue: base64 data-URLs in chat content poisoned the history ------------
# (megabytes of base64 resent as text on the next turn overflowed any
#  context and made the model deny its own tool results)
def test_no_inline_base64_emission():
    assert "data:image/png;base64,{b64}" not in TOOL_CONTENT
    assert "upload_image" in TOOL_CONTENT
    assert '"type": "files"' in TOOL_CONTENT


# --- issue #1: LLM-supplied partial strength made edits no-ops ----------------
def test_edit_image_has_no_strength_parameter():
    edit_src = TOOL_CONTENT.split("async def edit_image")[1].split("async def")[0]
    assert "strength" not in edit_src.split('"""')[0]  # not in the signature


# --- issue: 12MP photos must be downscaled before editing ---------------------
def test_edit_downscales_before_sending():
    assert "1024 / max" in TOOL_CONTENT
    assert "// 64 * 64" in TOOL_CONTENT


# --- narration must not deny successful tool runs -----------------------------
def test_tool_results_assert_success():
    assert TOOL_CONTENT.count("SUCCESS") >= 2
    assert "Never say you cannot" in TOOL_CONTENT


def test_tool_content_is_valid_python():
    compile(TOOL_CONTENT.replace("{shim_base}", "http://x/v1"), "<tool>", "exec")
