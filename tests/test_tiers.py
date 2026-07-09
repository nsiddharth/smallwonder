from smallwonder import tiers


def test_pick_tier_boundaries():
    assert tiers.pick_tier(16) == "16gb"
    assert tiers.pick_tier(23) == "16gb"
    assert tiers.pick_tier(24) == "32gb"
    assert tiers.pick_tier(36) == "32gb"
    assert tiers.pick_tier(48) == "48gb"
    assert tiers.pick_tier(128) == "48gb"


def test_every_tier_has_all_roles_and_both_backends():
    for tier, roles in tiers.TIERS.items():
        assert set(roles) == {"coder", "general", "fast"}, tier
        for spec in roles.values():
            assert spec.lmstudio and spec.gguf and spec.ram_gb > 0


def test_tier_models_resolution():
    m = tiers.tier_models("48gb", "lmstudio")
    assert m["coder"] == "qwen/qwen3.6-27b"
    assert m["embed"].startswith("text-embedding")
    g = tiers.tier_models("48gb", "llamaswap")
    assert ":" in g["coder"]  # repo:quant form


def test_tier_disk_estimate_positive():
    for tier in tiers.TIERS:
        assert tiers.tier_disk_gb(tier) > 1
