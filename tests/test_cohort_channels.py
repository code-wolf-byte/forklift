import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("cohort_channels", Path(__file__).parent.parent / "scripts" / "cohort_channels.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def test_permissions_round_trip_including_unknown_flags():
    names = {"1": "@everyone", "2": "Admin"}
    overwrites = [{"id": "1", "type": 0, "allow": "1024", "deny": "0"},
                  {"id": "2", "type": 0, "allow": "8854365862820689", "deny": "2048"},
                  {"id": "3", "type": 1, "allow": "1024", "deny": "0"}]  # member overwrite: dropped
    perms = cc.to_config_perms(overwrites, names)
    assert perms["@everyone"] == {"allow": ["view_channel"]}
    assert cc.to_overwrites(perms, {v: k for k, v in names.items()}) == overwrites[:2]


def test_forum_payload_strips_tag_ids_and_syncs_to_category():
    cat = {"permission_overwrites": [{"id": "1", "type": 0, "allow": "0", "deny": "1024"}]}
    forum = {"id": "9", "name": "🔎・tempe", "type": 15, "topic": "t", "nsfw": False, "permission_overwrites": cat["permission_overwrites"],
             "available_tags": [{"id": "5", "name": "Looking", "moderated": False, "emoji_name": "🏠", "emoji_id": None}]}
    entry = cc.channel_config(forum, cat, {"1": "@everyone"}, qna_id="9")
    assert entry == {"name": "🔎・tempe", "type": "forum", "qna_forum": True, "topic": "t",
                     "available_tags": [{"name": "Looking", "emoji_name": "🏠"}]}
    body = cc.channel_payload(entry, "42", {"@everyone": {"deny": ["view_channel"]}}, {"@everyone": "1"})
    assert body["type"] == 15 and body["parent_id"] == "42" and "qna_forum" not in body
    assert body["permission_overwrites"] == cat["permission_overwrites"]
