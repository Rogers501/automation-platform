"""Unit tests for framework.reporting.notification (fake SMTP, rule 14)."""

from __future__ import annotations

from typing import Any

from framework.core.config import NotificationSettings
from framework.reporting.notification import EmailNotifier


class _FakeSMTP:
    """Fake smtplib.SMTP that records interactions."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.tls_started = False
        self.logged_in: tuple[str, str] | None = None
        self.quit_called = False
        self.fail_on_send = False

    def starttls(self) -> None:
        self.tls_started = True

    def login(self, user: str, password: str) -> None:
        self.logged_in = (user, password)

    def send_message(self, msg: Any) -> None:
        if self.fail_on_send:
            raise RuntimeError("SMTP send failed")
        self.sent.append(
            {
                "subject": msg["Subject"],
                "from": msg["From"],
                "to": msg["To"],
                "body": msg.get_content(),
            }
        )

    def quit(self) -> None:
        self.quit_called = True


def _settings(**kwargs: Any) -> NotificationSettings:
    defaults: dict[str, Any] = {
        "enabled": True,
        "smtp_host": "smtp.test.com",
        "smtp_port": 587,
        "smtp_user": "bot@test.com",
        "smtp_password": "secret",
        "use_tls": True,
        "from_addr": "bot@test.com",
        "to_addrs": ["dev@test.com"],
    }
    defaults.update(kwargs)
    return NotificationSettings(**defaults)


def _notifier(fake: _FakeSMTP, **settings: Any) -> EmailNotifier:
    s = _settings(**settings)
    return EmailNotifier(s, smtp_factory=lambda h, p, t: fake)


async def test_send_disabled_returns_false() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake, enabled=False)
    result = await notifier.send("Subject", "Body")
    assert result is False
    assert len(fake.sent) == 0


async def test_send_no_recipients_returns_false() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake, to_addrs=[])
    result = await notifier.send("Subject", "Body")
    assert result is False


async def test_send_success() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake)
    result = await notifier.send("Test Run", "All passed")

    assert result is True
    assert len(fake.sent) == 1
    msg = fake.sent[0]
    assert msg["subject"] == "[Automation] Test Run"
    assert msg["from"] == "bot@test.com"
    assert msg["to"] == "dev@test.com"
    assert "All passed" in msg["body"]
    assert fake.tls_started is True
    assert fake.logged_in == ("bot@test.com", "secret")
    assert fake.quit_called is True


async def test_send_failure_returns_false() -> None:
    fake = _FakeSMTP()
    fake.fail_on_send = True
    notifier = _notifier(fake)
    result = await notifier.send("Subject", "Body")
    assert result is False


async def test_send_override_recipients() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake)
    await notifier.send("S", "B", to_addrs=["custom@test.com"])
    assert fake.sent[0]["to"] == "custom@test.com"


async def test_send_test_report_passed() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake)
    result = await notifier.send_test_report(
        passed=100,
        failed=0,
        skipped=1,
        report_url="http://allure/x",
        duration_s=30.0,
    )

    assert result is True
    body = fake.sent[0]["body"]
    assert "PASSED" in body
    assert "Passed: 100" in body
    assert "Failed: 0" in body
    assert "http://allure/x" in body
    assert "30.0s" in body
    assert fake.sent[0]["subject"] == "[Automation] Test Report - PASSED"


async def test_send_test_report_failed() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake)
    await notifier.send_test_report(passed=80, failed=5)

    body = fake.sent[0]["body"]
    assert "FAILED" in body
    assert "Failed: 5" in body


async def test_send_without_tls() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake, use_tls=False)
    await notifier.send("S", "B")
    assert fake.tls_started is False


async def test_send_without_auth() -> None:
    fake = _FakeSMTP()
    notifier = _notifier(fake, smtp_user="")
    await notifier.send("S", "B")
    assert fake.logged_in is None
