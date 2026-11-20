from trapyze.envmatch import match


def test_matches_names_and_flags_the_rest():
    found = {"TIINGO_API_KEY": "t1", "FMP_API_KEY": "f1", "HF_API_KEY": "h", "HFDATA_KEY": "h2",
             "GITHUB_TOKEN": "g", "OPENAI_API_KEY": "o", "FMP_BASE_URL": "https://x", "EMPTY_TOKEN": ""}
    plan = match(found, {"tiingo": {"key_var": "TIINGO_API_KEY", "current": "t1"},
                         "github": {"key_var": "GITHUB_TOKEN", "current": "old"}})
    by = {i["preset"]: i for i in plan["items"]}
    assert by["tiingo"]["action"] == "same" and by["github"]["action"] == "update" and by["fmp"]["action"] == "new"
    assert by["hfdata"]["var"] == "HF_API_KEY"
    names = {o["name"] for o in plan["other"]}
    assert {"OPENAI_API_KEY", "FMP_BASE_URL", "HFDATA_KEY", "EMPTY_TOKEN"} <= names
    assert "t1" not in str(plan) and "old" not in str(plan)
