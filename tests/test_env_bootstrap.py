"""`.env` 载入：文件是兜底，显式环境变量是权威。"""

from __future__ import annotations

import os

from finer.ops.env_bootstrap import load_env_file


def _write(tmp_path, body):
    p = tmp_path / ".env"
    p.write_text(body, encoding="utf-8")
    return p


def test_loads_plain_and_quoted_values(tmp_path, monkeypatch):
    for k in ("FINER_T_A", "FINER_T_B", "FINER_T_C"):
        monkeypatch.delenv(k, raising=False)
    n = load_env_file(_write(tmp_path, '\n'.join([
        "FINER_T_A=plain",
        "FINER_T_B='single'",
        'FINER_T_C="double"',
    ])))
    assert n == 3
    assert os.environ["FINER_T_A"] == "plain"
    assert os.environ["FINER_T_B"] == "single"
    assert os.environ["FINER_T_C"] == "double"


def test_existing_env_wins(tmp_path, monkeypatch):
    """显式 FOO=bar 或 CI secret 必须压过文件——文件不是权威。"""
    monkeypatch.setenv("FINER_T_KEEP", "from-shell")
    load_env_file(_write(tmp_path, "FINER_T_KEEP=from-file"))
    assert os.environ["FINER_T_KEEP"] == "from-shell"


def test_comments_blanks_and_malformed_lines_are_skipped(tmp_path, monkeypatch):
    monkeypatch.delenv("FINER_T_OK", raising=False)
    n = load_env_file(_write(tmp_path, '\n'.join([
        "# comment", "", "   ", "no_equals_sign", "FINER_T_OK=1",
    ])))
    assert n == 1 and os.environ["FINER_T_OK"] == "1"


def test_export_prefix_is_tolerated(tmp_path, monkeypatch):
    monkeypatch.delenv("FINER_T_EXP", raising=False)
    load_env_file(_write(tmp_path, "export FINER_T_EXP=v"))
    assert os.environ["FINER_T_EXP"] == "v"


def test_unbalanced_quote_is_left_alone(tmp_path, monkeypatch):
    """不成对的引号不猜用户意图。"""
    monkeypatch.delenv("FINER_T_Q", raising=False)
    load_env_file(_write(tmp_path, 'FINER_T_Q="oops'))
    assert os.environ["FINER_T_Q"] == '"oops'


def test_missing_file_is_not_an_error(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == 0
