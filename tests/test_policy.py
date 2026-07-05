from noble_ridge_agents.policy.permissions import PermissionPolicy


def test_iris_permissions_allow_read_and_draft_but_block_send():
    policy = PermissionPolicy.default()

    assert policy.is_allowed("iris", "gmail.search") is True
    assert policy.is_allowed("iris", "gmail.thread_read") is True
    assert policy.is_allowed("iris", "gmail.draft_reply") is True
    assert policy.is_allowed("iris", "gmail.send") is False
    assert policy.is_allowed("iris", "discord.post_approval") is True
    assert policy.is_allowed("iris", "ads.change_budget") is False
    assert policy.is_allowed("iris", "website.deploy") is False


def test_unknown_agent_has_no_permissions():
    policy = PermissionPolicy.default()

    assert policy.is_allowed("unknown", "gmail.search") is False
