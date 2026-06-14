#!/usr/bin/env python3
"""
MISQL PBI gateway (Azure SQL) access for AI regression RCA Allure attachments.

Used by ``allure_resolver_server.lookup_agent_by_allure_url`` to map an Allure URL to
``agent_full_path`` / ``model_input`` in ``mars_regression_agent_results``.

Requires:

* ``pip install pyodbc``
* System ODBC: ``unixODBC`` (provides ``libodbc.so.2``)
* Microsoft driver: ``ODBC Driver 18 for SQL Server`` (or 17)

On Fedora / RHEL (once per machine)::

    sudo dnf install -y unixODBC unixODBC-devel
    curl https://packages.microsoft.com/config/rhel/9/prod.repo | sudo tee /etc/yum.repos.d/mssql-release.repo
    sudo ACCEPT_EULA=Y dnf install -y msodbcsql18

Debug a single URL (same lookup as the resolver)::

    python3 ngts/scripts/ai_rca/server_side/misql_pbi_connect.py \\
        --lookup-allure 'https://allure.nvidia.com/.../index.html#suites/...'
"""
import argparse
import json
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

try:
    import pyodbc
except ImportError as e:
    msg = str(e)
    if "libodbc" in msg:
        raise ImportError(
            "pyodbc is installed but unixODBC is missing (libodbc.so.2). "
            "Install system packages, e.g. on Fedora: "
            "sudo dnf install -y unixODBC unixODBC-devel && "
            "sudo ACCEPT_EULA=Y dnf install -y msodbcsql18"
        ) from e
    raise ImportError(
        "misql_pbi_connect requires pyodbc: python3 -m pip install pyodbc"
    ) from e

# --- connection settings (password: set locally; do not commit real secrets) ---
MSSQL_HOST = "m-il-misql-01-prd.public.fbd32f5072b8.database.windows.net"
MSSQL_PORT = 3342
MSSQL_USERNAME = "Pbi_gateway"
MSSQL_PASSWORD = "pbi4ever"  # hard-code your password here
MSSQL_DATABASE = "sonic_mars"  # change to the target database name

# Prefer Driver 18; fall back to 17 if 18 is not installed.
ODBC_DRIVERS = (
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
)

MARS_LOOKUP_BY_ALLURE_SQL = """
SELECT TOP (1) agent_full_path, model_input
FROM mars_regression_agent_results
WHERE allure_url_2test = ?
ORDER BY run_time DESC
"""

FIT69_HOST_PREFIXES = (
    "http://fit69.mtl.labs.mlnx",
    "https://fit69.mtl.labs.mlnx",
)


def strip_fit69_url_prefix(url):
    # type: (str) -> str
    """Turn ``http://fit69.mtl.labs.mlnx/auto/...`` into ``/auto/...``."""
    url = (url or "").strip()
    if not url:
        return url
    for pfx in FIT69_HOST_PREFIXES:
        if url.startswith(pfx):
            return url[len(pfx):]
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc == "fit69.mtl.labs.mlnx" and parsed.path:
        return parsed.path
    return url


def _normalize_model_input(value):
    # type: (Any) -> Optional[Any]
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.startswith("{") or s.startswith("["):
            try:
                return json.loads(s)
            except ValueError:
                return s
        return s
    return value


def lookup_agent_by_allure_url(allure_url, db=None):
    # type: (str, Optional[MisqlPbiConnection]) -> Tuple[Optional[str], Optional[Any]]
    """
    Look up ``mars_regression_agent_results`` by exact ``allure_url_2test``.

    Returns ``(agent_full_path, agent_input)`` where ``agent_input`` is ``model_input`` from the row.
    Both are ``None`` when there is no match (no fallback).
    """
    target = (allure_url or "").strip()
    if not target:
        return None, None

    def _query(conn):
        # type: (MisqlPbiConnection) -> Tuple[Optional[str], Optional[Any]]
        rows = conn.query_dicts(MARS_LOOKUP_BY_ALLURE_SQL.strip(), (target,))
        if not rows:
            return None, None
        row = rows[0]
        agent_path = (row.get("agent_full_path") or "").strip() or None
        if not agent_path:
            return None, None
        return agent_path, _normalize_model_input(row.get("model_input"))

    if db is not None:
        return _query(db)
    with MisqlPbiConnection() as conn:
        return _query(conn)


def _pick_odbc_driver():
    # type: () -> str
    installed = {d.strip() for d in pyodbc.drivers()}
    for name in ODBC_DRIVERS:
        if name in installed:
            return name
    raise RuntimeError(
        "No supported ODBC driver found. Installed: {!r}. Expected one of: {!r}".format(
            sorted(installed), ODBC_DRIVERS
        )
    )


def build_connection_string(
    host=MSSQL_HOST,
    port=MSSQL_PORT,
    database=MSSQL_DATABASE,
    username=MSSQL_USERNAME,
    password=MSSQL_PASSWORD,
    driver=None,
    encrypt="yes",
    trust_server_certificate="no",
):
    # type: (...) -> str
    """Build a pyodbc connection string for Azure SQL."""
    if not password:
        raise ValueError("MSSQL_PASSWORD is empty; set it in misql_pbi_connect.py")
    if not database:
        raise ValueError("MSSQL_DATABASE is empty; set the target database name")
    drv = driver or _pick_odbc_driver()
    server = "{},{}".format(host, port)
    return (
        "DRIVER={{{}}};"
        "SERVER={};"
        "DATABASE={};"
        "UID={};"
        "PWD={};"
        "Encrypt={};"
        "TrustServerCertificate={};"
    ).format(drv, server, database, username, password, encrypt, trust_server_certificate)


def connect_misql(database=None, password=None, connection_string=None):
    # type: (Optional[str], Optional[str], Optional[str]) -> Any
    """Open and return a pyodbc connection (caller must close it)."""
    conn_str = connection_string or build_connection_string(
        database=database or MSSQL_DATABASE,
        password=password if password is not None else MSSQL_PASSWORD,
    )
    return pyodbc.connect(conn_str, timeout=30)


class MisqlPbiConnection(object):
    """Thin wrapper around pyodbc for MISQL PBI gateway queries."""

    def __init__(self, database=None, password=None, connection_string=None):
        # type: (Optional[str], Optional[str], Optional[str]) -> None
        self._database = database
        self._password = password
        self._connection_string = connection_string
        self._conn = None  # type: Optional[Any]
        self._cursor = None  # type: Optional[Any]

    def connect(self):
        # type: () -> None
        self._conn = connect_misql(
            database=self._database,
            password=self._password,
            connection_string=self._connection_string,
        )
        self._cursor = self._conn.cursor()

    def close(self):
        # type: () -> None
        if self._cursor is not None:
            self._cursor.close()
            self._cursor = None
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        # type: () -> MisqlPbiConnection
        self.connect()
        return self

    def __exit__(self, *exc):
        # type: (*object) -> None
        self.close()

    @property
    def cursor(self):
        # type: () -> Any
        if self._cursor is None:
            raise RuntimeError("not connected; call connect() or use as context manager")
        return self._cursor

    def execute(self, sql, params=None):
        # type: (str, Optional[Sequence[Any]]) -> Any
        if params is None:
            return self.cursor.execute(sql)
        return self.cursor.execute(sql, params)

    def query_dicts(self, sql, params=None):
        # type: (str, Optional[Sequence[Any]]) -> List[Dict[str, Any]]
        """Run SQL and return each row as a dict (column name -> value)."""
        self.execute(sql, params)
        if self.cursor.description is None:
            return []
        columns = [col[0] for col in self.cursor.description]
        return [dict(zip(columns, row)) for row in self.cursor.fetchall()]


def _main():
    # type: () -> int
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--lookup-allure",
        required=True,
        metavar="URL",
        help="Lookup agent_full_path and model_input for one Allure URL",
    )
    args = ap.parse_args()

    try:
        path, agent_input = lookup_agent_by_allure_url(args.lookup_allure)
        print(json.dumps({"agent_full_path": path, "agent_input": agent_input}, default=str))
        return 0
    except Exception as e:
        print("failed: {}".format(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(_main())
