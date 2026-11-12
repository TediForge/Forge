import csv
import os
import sqlite3
import sys
import time
from types import SimpleNamespace

from orchestrator.tools.definitions.data import (
    TOOLS,
    data,
)
from orchestrator.sandbox import cleanupTmp


def test_all_enterprise_data_tools_declare_output_schemas():
    assert len(TOOLS) == 1
    assert all("outputSchema" in tool for tool in TOOLS)
    assert {tool["function"]["name"] for tool in TOOLS} == {
        "data",
    }
    assert TOOLS[0]["function"]["parameters"]["properties"]["operation"]["enum"] == [
        "table", "sql", "profile", "join", "report", "chart",
    ]


def test_dataset_tools_reject_paths_outside_configured_root(sandboxWorkspace):
    profileResult = data("table", path="..\\secret.csv", options={"operation": "profile"})
    dataset = data("profile", path="..\\secret.csv")
    joined = data("join", left_path="..\\left.csv", right_path="right.csv", left_key="id")
    chartResult = data("chart", path="..\\input.csv", chart_type="line", x_column="x", y_column="y")

    assert profileResult["errorCode"] == "PATH_NOT_ALLOWED"
    assert dataset["errorCode"] == "PATH_NOT_ALLOWED"
    assert joined["errorCode"] == "PATH_NOT_ALLOWED"
    assert chartResult["errorCode"] == "PATH_NOT_ALLOWED"


def test_sql_query_uses_read_only_sqlite_and_returns_structured_errors(sandboxWorkspace):
    database = sandboxWorkspace / "outputs" / "analytics.db"
    with sqlite3.connect(database) as client:
        client.execute("CREATE TABLE records (id INTEGER, value TEXT)")
        client.execute("INSERT INTO records VALUES (1, 'ok')")

    connection = f"sqlite:{database}"
    result = data("sql", connection=connection, query="SELECT id, value FROM records")
    writeAttempt = data("sql", connection=connection, query="PRAGMA user_version = 1")
    escapedPath = data("sql", connection=f"sqlite:{sandboxWorkspace.parent.parent / 'outside.db'}", query="SELECT 1")

    assert result["success"] is True
    assert result["rows"] == [{"id": 1, "value": "ok"}]
    assert writeAttempt["success"] is False
    assert writeAttempt["errorCode"] == "QUERY_ERROR"
    assert escapedPath["errorCode"] == "PATH_NOT_ALLOWED"
    with sqlite3.connect(database) as client:
        assert client.execute("PRAGMA user_version").fetchone()[0] == 0


def test_groupby_requires_a_valid_value_column(monkeypatch, sandboxWorkspace):
    csvPath = sandboxWorkspace / "outputs" / "records.csv"
    csvPath.write_text("team,sales\nA,2\n", encoding="utf-8")
    frame = SimpleNamespace(columns=["team", "sales"])
    monkeypatch.setitem(sys.modules, "pandas", SimpleNamespace(read_csv=lambda _: frame))

    result = data(
        "table",
        path="outputs/records.csv",
        options={"operation": "groupby", "column": "team", "aggregate": "mean"},
    )

    assert result["success"] is False
    assert result["errorCode"] == "MISSING_VALUE_COLUMN"


def test_report_csv_escapes_formula_cells_and_confines_output(sandboxWorkspace):
    result = data(
        "report",
        title="=Quarterly report",
        sections=[{"title": "+Revenue", "content": "@SUM(A1:A5)"}],
        format="csv",
        output_path="outputs/reports/summary.csv",
    )

    with (sandboxWorkspace / "outputs" / "reports" / "summary.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    outside = data("report", title="Report", sections=[], format="json", output_path="../outside.json")

    assert result["success"] is True
    assert rows[1] == ["'=Quarterly report", "'+Revenue", "'@SUM(A1:A5)"]
    assert outside["success"] is False
    assert outside["errorCode"] == "PATH_NOT_ALLOWED"


def test_data_dispatch_rejects_unknown_operations_and_missing_arguments():
    unknown = data("unknown")
    missing = data("sql", connection="sqlite:analytics.db")
    missingTableOptions = data("table", path="sales.csv")

    assert unknown["errorCode"] == "INVALID_OPERATION"
    assert missing["errorCode"] == "INVALID_ARGUMENTS"
    assert missingTableOptions["errorCode"] == "INVALID_ARGUMENTS"


def test_sandbox_cleanup_removes_expired_tmp_files(sandboxWorkspace):
    temporaryRoot = sandboxWorkspace / "tmp"
    expiredFile = temporaryRoot / "expired.txt"
    recentFile = temporaryRoot / "recent.txt"
    expiredFile.write_text("old", encoding="utf-8")
    recentFile.write_text("new", encoding="utf-8")
    now = time.time()
    oldTime = now - (25 * 60 * 60)
    os.utime(expiredFile, (oldTime, oldTime))

    removed = cleanupTmp(now=now)

    assert removed == 1
    assert not expiredFile.exists()
    assert recentFile.exists()
