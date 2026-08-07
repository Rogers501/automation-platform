"""Data provider for load-test scenarios: template engine + CSV source.

Resolves {{...}} template expressions in scenario YAML fields at runtime.
Supports:

- {{faker.<method>}} -- Faker random data (e.g. {{faker.user_name}}).
- {{random.int(min,max)}} -- Random integer in [min, max].
- {{random.float(min,max)}} -- Random float in [min, max].
- {{random.choice(a,b,c)}} -- Random pick from comma-separated values.
- {{uuid}} -- A random UUID4.
- {{timestamp}} -- Current Unix timestamp (integer seconds).
- {{csv.<file>.<column>}} -- Sequential row from a CSV file.
- {{int:<expr>}} -- Cast any expression result to int (e.g. {{int:csv.users.id}}).
- {{float:<expr>}} -- Cast any expression result to float.

Example YAML scenario using data providers::

    scenarios:
      - name: create_order
        steps:
          - name: "POST /orders"
            method: POST
            url: /orders
            json:
              customer_name: "{{faker.name}}"
              order_id: "{{uuid}}"
              quantity: "{{random.int(1,100)}}"

Pure Python: Faker is an optional dependency (lazy import). CSV reading uses
only the standard library (rule 11).
"""

from __future__ import annotations

import csv
import random
import re
import time
import uuid as uuid_mod
from pathlib import Path
from typing import Any

from framework.core.exceptions import FrameworkError

__all__ = ["DataProvider", "DataProviderError", "resolve_templates"]

_TEMPLATE_RE = re.compile(r"\{\{([^}]+)\}\}")

_CSV_DEFAULT_DIR = "data"

_TYPE_CASTS: dict[str, type] = {"int": int, "float": float, "str": str}


class DataProviderError(FrameworkError):
    """Raised when a data provider template cannot be resolved."""


class DataProvider:
    """Resolves {{...}} templates for load-test scenario fields.

    Args:
        csv_dir: Directory containing CSV data files.
        faker_seed: Optional seed for reproducible Faker output.
        random_seed: Optional seed for reproducible random output.
    """

    def __init__(
        self,
        *,
        csv_dir: str | Path | None = None,
        faker_seed: int | None = None,
        random_seed: int | None = None,
    ) -> None:
        self._csv_dir = Path(csv_dir) if csv_dir else Path(_CSV_DEFAULT_DIR)
        self._faker: Any = None
        self._faker_seed = faker_seed
        self._random = random.Random(random_seed) if random_seed else random
        self._csv_cache: dict[str, list[dict[str, str]]] = {}
        self._csv_cursor: dict[str, int] = {}

    def _get_faker(self) -> Any:
        """Lazily import and cache the Faker instance."""
        if self._faker is None:
            try:
                from faker import Faker
            except ImportError as exc:
                raise DataProviderError(
                    "faker package is not installed; run 'pip install faker'"
                ) from exc
            self._faker = Faker(seed=self._faker_seed)
        return self._faker

    def resolve(self, value: Any) -> Any:
        """Recursively resolve templates in any value (str/dict/list)."""
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def _resolve_string(self, text: str) -> Any:
        """Resolve all {{...}} templates in a string."""
        full_match = _TEMPLATE_RE.fullmatch(text.strip())
        if full_match:
            return self._resolve_expr(full_match.group(1).strip())

        def _sub(m: re.Match[str]) -> str:
            return str(self._resolve_expr(m.group(1).strip()))

        return _TEMPLATE_RE.sub(_sub, text)

    def _resolve_expr(self, expr: str) -> Any:
        """Resolve a single template expression.

        Supports optional type-cast prefix before any expression::

            {{int:csv.users.id}}       # CSV string -> int
            {{float:random.int(0,1)}}  # random.int -> float
            {{str:uuid}}               # UUID -> str (explicit)

        The cast prefix and the expression are separated by the first ``:``.
        """
        if ":" in expr:
            cast_name, _, rest = expr.partition(":")
            cast_name = cast_name.strip()
            if cast_name in _TYPE_CASTS:
                value = self._resolve_expr(rest.strip())
                return _TYPE_CASTS[cast_name](value)

        if expr == "uuid":
            return str(uuid_mod.uuid4())
        if expr == "timestamp":
            return int(time.time())

        if expr.startswith("faker."):
            return self._resolve_faker(expr[len("faker.") :])

        if expr.startswith("random."):
            return self._resolve_random(expr[len("random.") :])

        if expr.startswith("csv."):
            return self._resolve_csv(expr[len("csv.") :])

        raise DataProviderError(f"unknown template expression: {{{{{expr}}}}}")

    def _resolve_faker(self, method: str) -> Any:
        """Resolve a Faker method call."""
        faker = self._get_faker()
        if not hasattr(faker, method):
            raise DataProviderError(f"faker has no method: {method}")
        return getattr(faker, method)()

    def _resolve_random(self, spec: str) -> Any:
        """Resolve a random.* expression."""
        if spec.startswith("int(") and spec.endswith(")"):
            args = spec[4:-1].split(",")
            if len(args) != 2:
                raise DataProviderError(f"random.int needs (min,max): {spec}")
            return self._random.randint(int(args[0].strip()), int(args[1].strip()))

        if spec.startswith("float(") and spec.endswith(")"):
            args = spec[6:-1].split(",")
            if len(args) != 2:
                raise DataProviderError(f"random.float needs (min,max): {spec}")
            return self._random.uniform(float(args[0].strip()), float(args[1].strip()))

        if spec.startswith("choice(") and spec.endswith(")"):
            items = [s.strip() for s in spec[7:-1].split(",")]
            return self._random.choice(items)

        raise DataProviderError(f"unknown random expression: {spec}")

    def _resolve_csv(self, spec: str) -> str:
        """Resolve a csv.<file>.<column> expression."""
        parts = spec.split(".")
        if len(parts) != 2:
            raise DataProviderError(f"csv expression must be csv.<file>.<column>: {spec}")
        file_name, column = parts
        if not file_name.endswith(".csv"):
            file_name = file_name + ".csv"

        rows = self._load_csv(file_name)
        if not rows:
            raise DataProviderError(f"CSV file is empty: {file_name}")
        if column not in rows[0]:
            raise DataProviderError(
                f"column '{column}' not found in {file_name}; available: {list(rows[0].keys())}"
            )

        cursor = self._csv_cursor.get(file_name, 0)
        row = rows[cursor % len(rows)]
        self._csv_cursor[file_name] = cursor + 1
        return row[column]

    def _load_csv(self, file_name: str) -> list[dict[str, str]]:
        """Load and cache a CSV file as a list of row dicts."""
        if file_name in self._csv_cache:
            return self._csv_cache[file_name]
        path = self._csv_dir / file_name
        if not path.exists():
            raise DataProviderError(f"CSV file not found: {path}")
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        self._csv_cache[file_name] = rows
        return rows


def resolve_templates(data: Any, provider: DataProvider | None = None) -> Any:
    """Convenience: resolve templates in *data* using a (default) provider."""
    p = provider or DataProvider()
    return p.resolve(data)
