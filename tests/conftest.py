"""Shared test setup: no real pauses, no real ControlMaster probing.

Pacing (see ``_remote`` in sftp_helper.main) sleeps between contacts and asks
the local ssh for a live master. Tests that stub ``_system`` must not pay
seconds per call nor spawn ``ssh -O check``; the pacing tests themselves
re-enable what they measure.
"""

import pytest

from sftp_helper import main as sftph_main


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    monkeypatch.setattr(sftph_main, "_PACE_CONNECT", (0.0, 0.0))
    monkeypatch.setattr(sftph_main, "_PACE_REUSE", (0.0, 0.0))
    monkeypatch.setattr(sftph_main, "_master_alive", lambda _cred: False)
    monkeypatch.setattr(sftph_main, "_ensure_master", lambda _cred: None)
    sftph_main._last_contact.clear()
    sftph_main._authenticated.clear()
    sftph_main._master_failed_at.clear()
