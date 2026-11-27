import os

from db.envfile import load_repo_env


def test_values_a_shell_cannot_parse_load_intact_and_existing_variables_win(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('TOOL_SECRET=)Ka9#i_2,\nTOOL_JSON=["http://a","http://b"]\nTOOL_KEPT=from-file\n')
    monkeypatch.delenv("TOOL_SECRET", raising=False)
    monkeypatch.delenv("TOOL_JSON", raising=False)
    monkeypatch.setenv("TOOL_KEPT", "from-environment")
    assert load_repo_env(env) is True
    assert os.environ["TOOL_SECRET"] == ")Ka9#i_2,"
    assert os.environ["TOOL_JSON"] == '["http://a","http://b"]'
    assert os.environ["TOOL_KEPT"] == "from-environment"
    for name in ("TOOL_SECRET", "TOOL_JSON"):
        monkeypatch.delenv(name, raising=False)


def test_a_missing_file_is_not_an_error(tmp_path):
    assert load_repo_env(tmp_path / "nope.env") is False
