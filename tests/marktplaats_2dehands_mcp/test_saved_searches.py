"""Tests for saved-search persistence."""

from pathlib import Path

import pytest

from marktplaats_2dehands_mcp import saved_searches as ss


class TestLoadSave:
    def test_load_missing_file_returns_empty(self, state_path: Path):
        data = ss._load(state_path)
        assert data == {"version": 1, "searches": {}}

    def test_load_corrupt_file_returns_empty(self, state_path: Path):
        state_path.write_text("not json", encoding="utf-8")
        data = ss._load(state_path)
        assert data == {"version": 1, "searches": {}}

    def test_save_creates_directory(self, tmp_path: Path):
        nested = tmp_path / "deep" / "dir" / "state.json"
        ss._save(nested, {"version": 1, "searches": {}})
        assert nested.exists()

    def test_save_uses_atomic_write(self, state_path: Path):
        ss._save(state_path, {"version": 1, "searches": {"a": 1}})
        # Tmp file should be cleaned up
        assert not state_path.with_suffix(state_path.suffix + ".tmp").exists()
        assert state_path.exists()


class TestSaveSearch:
    def test_save_returns_metadata(self, state_path: Path):
        result = ss.save_search("test", {"site": "marktplaats", "query": "x"}, path=state_path)
        assert result == {
            "name": "test",
            "saved": True,
            "params": {"site": "marktplaats", "query": "x"},
        }

    def test_save_persists_to_disk(self, state_path: Path):
        ss.save_search("foo", {"site": "2dehands"}, path=state_path)
        assert state_path.exists()
        loaded = ss._load(state_path)
        assert "foo" in loaded["searches"]
        entry = loaded["searches"]["foo"]
        assert entry["params"] == {"site": "2dehands"}
        assert entry["created_at"] is not None
        assert entry["last_checked_at"] is None
        assert entry["seen_ids"] == []

    def test_save_replaces_existing(self, state_path: Path):
        ss.save_search("foo", {"site": "marktplaats"}, path=state_path)
        ss.save_search("foo", {"site": "2dehands"}, path=state_path)
        loaded = ss._load(state_path)
        assert loaded["searches"]["foo"]["params"]["site"] == "2dehands"


class TestListSearches:
    def test_empty(self, state_path: Path):
        assert ss.list_searches(path=state_path) == []

    def test_lists_all_with_metadata(self, state_path: Path):
        ss.save_search("a", {"site": "marktplaats"}, path=state_path)
        ss.save_search("b", {"site": "2dehands"}, path=state_path)
        result = ss.list_searches(path=state_path)
        assert len(result) == 2
        names = {s["name"] for s in result}
        assert names == {"a", "b"}
        for s in result:
            assert s["seen_count"] == 0
            assert s["last_checked_at"] is None


class TestGetSearch:
    def test_returns_none_when_missing(self, state_path: Path):
        assert ss.get_search("nope", path=state_path) is None

    def test_returns_entry(self, state_path: Path):
        ss.save_search("foo", {"site": "marktplaats", "query": "x"}, path=state_path)
        entry = ss.get_search("foo", path=state_path)
        assert entry is not None
        assert entry["params"] == {"site": "marktplaats", "query": "x"}


class TestDeleteSearch:
    def test_delete_existing(self, state_path: Path):
        ss.save_search("foo", {"site": "marktplaats"}, path=state_path)
        assert ss.delete_search("foo", path=state_path) is True
        assert ss.get_search("foo", path=state_path) is None

    def test_delete_missing_returns_false(self, state_path: Path):
        assert ss.delete_search("ghost", path=state_path) is False


class TestRecordCheck:
    def test_records_seen_ids(self, state_path: Path):
        ss.save_search("foo", {"site": "marktplaats"}, path=state_path)
        ss.record_check("foo", ["m1", "m2"], path=state_path)
        entry = ss.get_search("foo", path=state_path)
        assert entry is not None
        assert set(entry["seen_ids"]) == {"m1", "m2"}
        assert entry["last_checked_at"] is not None

    def test_appends_without_duplicates(self, state_path: Path):
        ss.save_search("foo", {"site": "marktplaats"}, path=state_path)
        ss.record_check("foo", ["m1", "m2"], path=state_path)
        ss.record_check("foo", ["m2", "m3"], path=state_path)
        entry = ss.get_search("foo", path=state_path)
        assert set(entry["seen_ids"]) == {"m1", "m2", "m3"}

    def test_caps_at_5000(self, state_path: Path):
        ss.save_search("foo", {"site": "marktplaats"}, path=state_path)
        ids = [f"m{i}" for i in range(6000)]
        ss.record_check("foo", ids, path=state_path)
        entry = ss.get_search("foo", path=state_path)
        assert len(entry["seen_ids"]) == 5000

    def test_record_for_unknown_name_is_noop(self, state_path: Path):
        ss.record_check("ghost", ["m1"], path=state_path)
        # File may not exist, but no exception is raised.
        assert ss.get_search("ghost", path=state_path) is None


class TestEnvDirOverride:
    def test_env_var_changes_default_state_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setenv("MARKTPLAATS_2DEHANDS_STATE_DIR", str(tmp_path))
        # Reload module to pick up the new env var.
        import importlib

        from marktplaats_2dehands_mcp import saved_searches

        reloaded = importlib.reload(saved_searches)
        assert reloaded.DEFAULT_STATE_DIR == tmp_path
        assert reloaded.DEFAULT_STATE_FILE == tmp_path / "saved_searches.json"
        # Reload back to defaults so other tests are unaffected.
        monkeypatch.delenv("MARKTPLAATS_2DEHANDS_STATE_DIR", raising=False)
        importlib.reload(saved_searches)
