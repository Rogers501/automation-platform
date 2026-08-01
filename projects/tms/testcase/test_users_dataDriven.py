"""yaml 数据驱动示例."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from api.users import UsersApi

from framework.clients.http.client import AsyncHttpClient
from framework.testing.datadriven import case_ids, load_cases

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CASES = load_cases(_DATA_DIR / "users_cases.yaml")


@pytest.mark.regression
@pytest.mark.parametrize("case", _CASES, ids=case_ids(_CASES))
async def test_create_user_data_driven(api_client: AsyncHttpClient, case: dict[str, Any]) -> None:
    """每个 yaml 用例创建一个用户并校验回显."""
    user = await UsersApi(api_client).create_user(case["name"], case["email"])
    assert user["name"] == case["name"]
    assert user["email"] == case["email"]
