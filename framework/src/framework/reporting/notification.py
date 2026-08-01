"""Email notification for test report delivery (async, no blocking calls).

Sends test result summaries and report links via SMTP after a test run.
Uses :mod:`smtplib` (stdlib) wrapped in :func:`asyncio.to_thread` so it
never blocks the event loop (rule 16). The SMTP factory is injectable
for unit tests (rule 14).

Layering: depends on ``core`` (config, logger). Never depends on
``clients`` or ``testing`` (rule 11).
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

from framework.core.config import NotificationSettings, get_settings
from framework.core.logger import get_logger

__all__ = ["EmailNotifier", "SMTPFactory"]

_LOGGER = get_logger("notification")


class SMTPFactory(Protocol):
    """Protocol for SMTP client creation (injectable for tests)."""

    def __call__(self, host: str, port: int, timeout: float) -> smtplib.SMTP:
        """Create and return an SMTP connection."""
        ...


def _default_smtp_factory(host: str, port: int, timeout: float) -> smtplib.SMTP:
    """Default SMTP factory using stdlib smtplib."""
    return smtplib.SMTP(host, port, timeout=timeout)


class EmailNotifier:
    """Async email notifier for test report delivery.

    Args:
        settings: Notification settings; defaults to
            :func:`get_settings().notification`.
        smtp_factory: Callable that creates an SMTP connection (injectable
            for tests, rule 14).
    """

    def __init__(
        self,
        settings: NotificationSettings | None = None,
        *,
        smtp_factory: SMTPFactory | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_settings().notification
        self._smtp_factory = smtp_factory or _default_smtp_factory

    async def send(
        self,
        subject: str,
        body: str,
        *,
        to_addrs: list[str] | None = None,
    ) -> bool:
        """Send an email notification.

        Args:
            subject: Email subject (prefixed with ``subject_prefix``).
            body: Email body (plain text).
            to_addrs: Override recipients; defaults to settings.

        Returns:
            ``True`` if sent successfully, ``False`` on failure or when
            disabled.
        """
        if not self._settings.enabled:
            _LOGGER.debug("Email notifications disabled, skipping send")
            return False

        recipients = to_addrs or self._settings.to_addrs
        if not recipients:
            _LOGGER.warning("No recipients configured, skipping send")
            return False

        full_subject = f"{self._settings.subject_prefix} {subject}"
        try:
            await asyncio.to_thread(
                self._send_sync,
                full_subject,
                body,
                recipients,
            )
            _LOGGER.info("Email sent to {} recipients", len(recipients))
            return True
        except Exception as exc:
            _LOGGER.error("Failed to send email: {}", exc)
            return False

    async def send_test_report(
        self,
        *,
        passed: int,
        failed: int,
        skipped: int = 0,
        report_url: str = "",
        duration_s: float = 0.0,
    ) -> bool:
        """Send a test result summary email.

        Args:
            passed: Number of passed tests.
            failed: Number of failed tests.
            skipped: Number of skipped tests.
            report_url: Optional Allure report URL.
            duration_s: Total duration in seconds.

        Returns:
            ``True`` if sent successfully.
        """
        status = "PASSED" if failed == 0 else "FAILED"
        lines = [
            f"Test Result: {status}",
            f"Passed: {passed}",
            f"Failed: {failed}",
            f"Skipped: {skipped}",
        ]
        if duration_s > 0:
            lines.append(f"Duration: {duration_s:.1f}s")
        if report_url:
            lines.append(f"Report: {report_url}")
        body = "\n".join(lines)
        return await self.send(f"Test Report - {status}", body)

    def _send_sync(
        self,
        subject: str,
        body: str,
        recipients: list[str],
    ) -> None:
        """Send email synchronously (called via asyncio.to_thread)."""
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._settings.from_addr
        msg["To"] = ", ".join(recipients)
        msg.set_content(body)

        smtp = self._smtp_factory(
            self._settings.smtp_host,
            self._settings.smtp_port,
            30.0,
        )
        try:
            if self._settings.use_tls:
                smtp.starttls()
            if self._settings.smtp_user:
                smtp.login(self._settings.smtp_user, self._settings.smtp_password)
            smtp.send_message(msg)
        finally:
            smtp.quit()
