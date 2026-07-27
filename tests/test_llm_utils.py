import pytest

from determine.llm.client import extract_json, load_dotenv, make_client


def test_extract_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    assert extract_json('Here you go:\n```json\n{"a": [1, 2]}\n```\nDone.') == {"a": [1, 2]}


def test_extract_json_with_prose():
    assert extract_json('Sure! The plan is {"steps": []} as requested.') == {"steps": []}


def test_extract_json_with_nested_braces_in_strings():
    assert extract_json('x {"q": "a {weird} value", "n": 2} y') == {"q": "a {weird} value", "n": 2}


def test_extract_json_failure():
    with pytest.raises(ValueError):
        extract_json("no json here at all")


def test_cache_hit_avoids_network(tmp_path):
    """A cached response is returned without any vendor SDK/network involvement."""
    import hashlib, json
    client = make_client("anthropic", "some-model", cache_dir=str(tmp_path))
    key = client._cache_key("sys", "user", 100)
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(json.dumps({"model": "some-model", "text": "cached!"}))
    assert client.complete("sys", "user", 100) == "cached!"


def test_unknown_family_rejected():
    with pytest.raises(ValueError):
        make_client("mystery", "model-x")


def test_load_dotenv_missing_file_is_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    load_dotenv()  # should not raise
