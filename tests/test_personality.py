from __future__ import annotations

from thoughtpins.chat.personality import enforce_response_style


def test_friendly_voice_removes_unrequested_direct_address_slang():
    assert enforce_response_style("Bro, here is what I found.", "friendly") == "Here is what I found."
    assert (
        enforce_response_style("Here is the detail, bro - it matters.", "friendly")
        == "Here is the detail - it matters."
    )
    assert (
        enforce_response_style("That word appears in the source as 'brother'.", "friendly")
        == "That word appears in the source as 'brother'."
    )


def test_mirror_voice_preserves_user_selected_casual_address():
    assert enforce_response_style("Got it, bro.", "mirror") == "Got it, bro."
