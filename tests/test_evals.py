from smallwonder.evals.runner import load_cases


def test_cases_load_and_cover_roles():
    cases = load_cases()
    assert len(cases) >= 6
    roles = {c.role for c in cases}
    assert {"coder", "general", "fast", "auto"} <= roles
    for c in cases:
        assert c.prompt and c.name
