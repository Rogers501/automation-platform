"""Data provider for load-test scenarios: template engine + CSV source.

Resolves {{...}} template expressions in scenario YAML fields at runtime.
Supports:

- {{faker.<method>}} -- Faker random data (e.g. {{faker.user_name}}).
- {{random.int(min,max)}} -- Random integer in [min, max].
- {{random.float(min,max)}} -- Random float in [min, max].
- {{random.choice(a,b,c)}} -- Random pick from comma-separated values.
- {{uuid}} -- A random UUID4.
- {{timestamp}} -- Current Unix timestamp (integer seconds).
- {{csv.<file>.<column>}} -- Sequential row from a CSV file (legacy alias).
- {{data.<file>.<column>}} -- Sequential row from any supported data file.
  Supports .csv, .txt (single column 'value'), .json (array of objects),
  .jsonl (JSON Lines, one object per line).
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
import json
import random
import re
import time
import uuid as uuid_mod
from pathlib import Path
from typing import Any

from framework.core.exceptions import FrameworkError

__all__ = ["DataProvider", "DataProviderError", "resolve_templates"]

_TEMPLATE_RE = re.compile(r"\{\{([^}]+)\}\}")

_DATA_DEFAULT_DIR = "data"

_TYPE_CASTS: dict[str, type] = {"int": int, "float": float, "str": str}

# Supported data-source file extensions -> loader methods.
_DATA_EXTENSIONS = {".csv", ".txt", ".json", ".jsonl"}


class DataProviderError(FrameworkError):
    """Raised when a data provider template cannot be resolved."""


class DataProvider:
    """Resolves {{...}} templates for load-test scenario fields.

    Args:
        csv_dir: Directory containing data files (CSV/TXT/JSON/JSONL).
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
        self._data_dir = Path(csv_dir) if csv_dir else Path(_DATA_DEFAULT_DIR)
        self._faker: Any = None
        self._faker_seed = faker_seed
        self._random = random.Random(random_seed) if random_seed else random
        self._data_cache: dict[str, list[dict[str, str]]] = {}
        self._data_cursor: dict[str, int] = {}
        # Per-resolve row lock: when resolving a single request body, all
        # data references to the same file should read the same row.
        self._resolve_locked_rows: dict[str, int] = {}

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
        """Recursively resolve templates in any value (str/dict/list).

        Within a single resolve() call, all data-file references to the
        same file read the same row (row consistency). The cursor advances
        only after the top-level resolve completes.
        """
        self._resolve_locked_rows.clear()
        try:
            result = self._resolve_recursive(value)
        finally:
            # Advance cursors for all files locked during this resolve.
            for file_name in self._resolve_locked_rows:
                self._data_cursor[file_name] = self._resolve_locked_rows[file_name] + 1
            self._resolve_locked_rows.clear()
        return result

    def _resolve_recursive(self, value: Any) -> Any:
        """Internal recursive resolver (does not clear locked rows)."""
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, dict):
            return {k: self._resolve_recursive(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_recursive(v) for v in value]
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
            return self._resolve_data(expr[len("csv.") :])

        if expr.startswith("data."):
            return self._resolve_data(expr[len("data.") :])

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

    def _resolve_data(self, spec: str) -> str:
        """Resolve a data.<file>.<column> or csv.<file>.<column> expression.

        Supports .csv, .txt, .json, .jsonl files. The file extension
        determines the parsing strategy:
        - .csv: comma-separated with header row -> dict per row
        - .txt: one value per line (single column, column name is 'value')
        - .json: JSON array of objects -> dict per element
        - .jsonl: JSON Lines (one JSON object per line) -> dict per line
        """
        parts = spec.split(".")
        if len(parts) < 2:
            raise DataProviderError(f"data expression must be <file>.<column>: {spec}")
        # The last part is the column name; the rest is the file name
        # (file names may contain dots, e.g. "users.v2").
        column = parts[-1]
        file_name = ".".join(parts[:-1])
        if "." not in file_name:
            # No extension specified; try common extensions in order.
            for ext in _DATA_EXTENSIONS:
                candidate = f"{file_name}{ext}"
                if (self._data_dir / candidate).exists():
                    file_name = candidate
                    break
        if "." not in file_name:
            raise DataProviderError(
                f"could not resolve data file: {file_name} (tried extensions: {_DATA_EXTENSIONS})"
            )

        rows = self._load_data(file_name)
        if not rows:
            raise DataProviderError(f"data file is empty: {file_name}")
        if column not in rows[0]:
            available = list(rows[0].keys())
            raise DataProviderError(
                f"column '{column}' not found in {file_name}; available: {available}"
            )

        # Row consistency: within a single resolve() call, all references
        # to the same file read the same row. The cursor advances once at
        # the end of the resolve (see resolve()).
        if file_name in self._resolve_locked_rows:
            cursor = self._resolve_locked_rows[file_name]
        else:
            cursor = self._data_cursor.get(file_name, 0)
            self._resolve_locked_rows[file_name] = cursor
        row = rows[cursor % len(rows)]
        return row[column]

    def _load_data(self, file_name: str) -> list[dict[str, str]]:
        """Load and cache a data file as a list of row dicts.

        Dispatches on file extension:
        - .csv  -> csv.DictReader
        - .txt  -> one value per line, column name 'value'
        - .json -> JSON array of objects
        - .jsonl-> JSON Lines (one object per line)
        """
        if file_name in self._data_cache:
            return self._data_cache[file_name]
        path = self._data_dir / file_name
        if not path.exists():
            raise DataProviderError(f"data file not found: {path}")
        ext = path.suffix.lower()
        if ext == ".csv":
            with path.open("r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
        elif ext == ".txt":
            with path.open("r", encoding="utf-8") as f:
                rows = [{"value": line.strip()} for line in f if line.strip()]
        elif ext == ".json":
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, list):
                raise DataProviderError(f"JSON data file must be a list of objects: {file_name}")
            rows = [{k: str(v) for k, v in item.items()} for item in raw]
        elif ext == ".jsonl":
            rows = []
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        obj = json.loads(line)
                        rows.append({k: str(v) for k, v in obj.items()})
        else:
            raise DataProviderError(
                f"unsupported data file extension: {ext} (supported: {_DATA_EXTENSIONS})"
            )
        self._data_cache[file_name] = rows
        return rows


def resolve_templates(data: Any, provider: DataProvider | None = None) -> Any:
    """Convenience: resolve templates in *data* using a (default) provider."""
    p = provider or DataProvider()
    return p.resolve(data)
