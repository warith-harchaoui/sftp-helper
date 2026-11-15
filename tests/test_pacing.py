"""Pacing: jittered gaps between contacts, backoff only after earlier success."""

from sftp_helper import main as sftph_main

# Captured at import, before the conftest fixture stubs it for every other test.
REAL_ENSURE_MASTER = sftph_main._ensure_master

CRED = {"sftp_host": "example.org", "sftp_login": "u", "sftp_port": 22}
DENIED = "u@example.org: Permission denied (publickey,password).\n"


def _clock(monkeypatch):
    """Fake monotonic clock advanced by time.sleep; returns the list of sleeps."""
    now = [1000.0]
    sleeps = []
    monkeypatch.setattr(sftph_main.time, "monotonic", lambda: now[0])

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(sftph_main.time, "sleep", fake_sleep)
    return sleeps


def test_gap_between_two_contacts_is_random_and_in_range(monkeypatch):
    sleeps = _clock(monkeypatch)
    monkeypatch.setattr(sftph_main, "_PACE_CONNECT", (1.5, 4.0))
    monkeypatch.setattr(sftph_main, "_system", lambda argv, env: (0, "", ""))
    for _ in range(6):
        sftph_main._remote(CRED, ["sftp"], {})
    assert len(sleeps) == 5  # the first contact never waits
    assert all(1.5 <= s <= 4.0 for s in sleeps)
    assert len(set(sleeps)) > 1  # jittered, not a fixed interval


def test_live_master_uses_the_shorter_gap(monkeypatch):
    sleeps = _clock(monkeypatch)
    monkeypatch.setattr(sftph_main, "_PACE_CONNECT", (10.0, 10.0))
    monkeypatch.setattr(sftph_main, "_PACE_REUSE", (0.3, 1.5))
    monkeypatch.setattr(sftph_main, "_master_alive", lambda _c: True)
    monkeypatch.setattr(sftph_main, "_system", lambda argv, env: (0, "", ""))
    sftph_main._remote(CRED, ["sftp"], {})
    sftph_main._remote(CRED, ["sftp"], {})
    assert len(sleeps) == 1 and 0.3 <= sleeps[0] <= 1.5


def test_first_login_refused_is_not_retried(monkeypatch):
    sleeps = _clock(monkeypatch)
    calls = []

    def fake_system(argv, env):
        calls.append(argv)
        return 255, "", DENIED

    monkeypatch.setattr(sftph_main, "_system", fake_system)
    code, _out, err = sftph_main._remote(CRED, ["sftp"], {})
    assert code == 255 and "Permission denied" in err
    assert len(calls) == 1 and sleeps == []


def test_refusal_after_success_backs_off_at_least_a_minute(monkeypatch):
    sleeps = _clock(monkeypatch)
    answers = iter([(0, "ok", ""), (255, "", DENIED), (255, "", DENIED), (0, "ok", "")])
    monkeypatch.setattr(sftph_main, "_system", lambda argv, env: next(answers))
    sftph_main._remote(CRED, ["sftp"], {})
    code, out, _err = sftph_main._remote(CRED, ["sftp"], {})
    assert (code, out) == (0, "ok")
    assert len(sleeps) == 2 and all(s >= 60 for s in sleeps)


def test_refusals_stop_after_the_retry_budget(monkeypatch):
    _clock(monkeypatch)
    monkeypatch.setattr(sftph_main, "_REFUSAL_RETRIES", 2)
    answers = iter([(0, "", "")] + [(255, "", DENIED)] * 10)
    calls = []

    def fake_system(argv, env):
        calls.append(1)
        return next(answers)

    monkeypatch.setattr(sftph_main, "_system", fake_system)
    sftph_main._remote(CRED, ["sftp"], {})
    code, _o, _e = sftph_main._remote(CRED, ["sftp"], {})
    assert code == 255 and len(calls) == 1 + 3


def test_backoff_is_full_jitter_and_capped():
    for attempt in range(12):
        d = sftph_main._backoff_delay(attempt)
        assert 0 <= d <= min(sftph_main._BACKOFF_CAP, 2.0 * 2**attempt)
    assert sftph_main._backoff_delay(0, floor=60) >= 60


def test_env_range_parsing(monkeypatch):
    monkeypatch.setenv("X_PACE", "4,1")
    assert sftph_main._env_range("X_PACE", (0, 0)) == (1.0, 4.0)
    monkeypatch.setenv("X_PACE", "nope")
    assert sftph_main._env_range("X_PACE", (2.0, 3.0)) == (2.0, 3.0)


def _password_auth(monkeypatch):
    monkeypatch.setattr(
        sftph_main, "_password_prefix", lambda _c: (["sshpass", "-e"], {"SSHPASS": "x"}, True)
    )
    calls = []

    def fake_system(argv, env):
        calls.append(argv)
        return 0, "", ""

    monkeypatch.setattr(sftph_main, "_system", fake_system)
    return calls


def test_master_waits_for_a_first_successful_login(monkeypatch):
    _clock(monkeypatch)
    calls = _password_auth(monkeypatch)
    REAL_ENSURE_MASTER(CRED)
    assert calls == []  # never logged in yet: no master attempt
    sftph_main._authenticated.add(sftph_main._control_path(CRED))
    REAL_ENSURE_MASTER(CRED)
    assert len(calls) == 1 and calls[0][-3:] == ["-f", "-N", "u@example.org"]
    assert "ControlMaster=yes" in calls[0]


def test_failed_master_is_not_retried_for_ten_minutes(monkeypatch):
    _clock(monkeypatch)
    _password_auth(monkeypatch)
    calls = []

    def refusing(argv, env):
        calls.append(argv)
        return 255, "", DENIED

    monkeypatch.setattr(sftph_main, "_system", refusing)
    sftph_main._authenticated.add(sftph_main._control_path(CRED))
    REAL_ENSURE_MASTER(CRED)
    REAL_ENSURE_MASTER(CRED)
    assert len(calls) == 1
    sftph_main.time.sleep(sftph_main._MASTER_RETRY_AFTER + 1)
    REAL_ENSURE_MASTER(CRED)
    assert len(calls) == 2


def test_key_auth_never_opens_a_master_by_hand(monkeypatch):
    _clock(monkeypatch)
    monkeypatch.setattr(sftph_main, "_password_prefix", lambda _c: ([], {}, False))
    calls = []
    monkeypatch.setattr(sftph_main, "_system", lambda argv, env: calls.append(argv) or (0, "", ""))
    sftph_main._authenticated.add(sftph_main._control_path(CRED))
    REAL_ENSURE_MASTER(CRED)
    assert calls == []
