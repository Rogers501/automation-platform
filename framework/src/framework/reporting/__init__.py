"""Allure reporting extensions.

All helpers gracefully no-op when ``allure`` is not installed. Enable the
pytest plugin in a consuming system by installing ``allure-pytest`` and running
``pytest --alluredir=<dir>``.

For enterprise reports, use :mod:`framework.reporting.labels` for dynamic
severity/feature/story labels and issue links,
:mod:`framework.reporting.environment` to write ``environment.properties``
and ``categories.json`` to the results directory,
:mod:`framework.reporting.history` for trend tracking, and
:mod:`framework.reporting.notification` for email report delivery.
"""

from framework.reporting.allure import (
    attach_db_result,
    attach_exchanges,
    attach_http_exchange,
    attach_json,
    attach_text,
    is_allure_available,
    step,
)
from framework.reporting.environment import (
    default_categories,
    write_categories,
    write_environment,
)
from framework.reporting.history import (
    copy_history_to_results,
    preserve_history,
)
from framework.reporting.labels import (
    description,
    epic,
    feature,
    issue,
    label,
    link,
    owner,
    severity,
    story,
    suite,
    tag,
    test_case,
)
from framework.reporting.notification import EmailNotifier

__all__ = [
    "EmailNotifier",
    "attach_db_result",
    "attach_exchanges",
    "attach_http_exchange",
    "attach_json",
    "attach_text",
    "copy_history_to_results",
    "default_categories",
    "description",
    "epic",
    "feature",
    "is_allure_available",
    "issue",
    "label",
    "link",
    "owner",
    "preserve_history",
    "severity",
    "step",
    "story",
    "suite",
    "tag",
    "test_case",
    "write_categories",
    "write_environment",
]
