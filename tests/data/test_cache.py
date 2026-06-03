from wcmodel.data.cache import content_key, cached_pull


def test_content_key_is_deterministic_and_input_sensitive():
    assert content_key("results", {"v": 1}) == content_key("results", {"v": 1})
    assert content_key("results", {"v": 1}) != content_key("results", {"v": 2})


def test_cached_pull_runs_once_then_reads_cache(tmp_path):
    calls = {"n": 0}
    def fetch():
        calls["n"] += 1
        import pandas as pd
        return pd.DataFrame({"a": [1, 2]})
    df1 = cached_pull("x", {"p": 1}, fetch, cache_dir=tmp_path)
    df2 = cached_pull("x", {"p": 1}, fetch, cache_dir=tmp_path)
    assert calls["n"] == 1
    assert df1.equals(df2)
