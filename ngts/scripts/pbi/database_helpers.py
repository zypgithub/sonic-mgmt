from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ngts.nvos_constants.constants_nvos import OperationTimeConsts
from ngts.scripts.pbi.models import Args, Summary, TestResult, LABug

if TYPE_CHECKING:
    from ngts.tools.mars_test_cases_results.Connect_to_MSSQL import ConnectMSSQL

logger = logging.getLogger(__name__)


# **********************************************************************************************************************
# SQL Queries
# **********************************************************************************************************************
_TEST_ANALYTICS_COLUMNS_QUERY = f"""\
    INSERT test_analytics (
        {OperationTimeConsts.SETUP_COL},
        suite_path,
        test_name,
        status,
        session_id,
        {OperationTimeConsts.DATE_COL},
        dut_hwsku,
        report_url,
        branch,
        version,
        duration
    )
    VALUES {{values}};
"""

_REGRESSION_MATRIX_COLUMNS_QUERY = f"""\
    INSERT regression_matrix (
        {OperationTimeConsts.SETUP_COL},
        pass_rate,
        version,
        executed,
        session_id,
        report_url,
        {OperationTimeConsts.DATE_COL},
        dut_hwsku,
        branch
    )
    VALUES {{values}};
"""


_LA_BUG_COLUMNS_QUERY = f"""\
INSERT INTO la_bugs (
    test_name,
    test_url,
    test_runtime_mins,
    session_id,
    {OperationTimeConsts.SETUP_COL},
    setup_mins,
    test_body_mins,
    teardown_mins,
    la_runtime_mins,
    nvos_version,
    branch,
    {OperationTimeConsts.DATE_COL},

    -- Bug Level Data (The "Nested" Data)
    bug_id,
    bug_url,
    occurrences,
    bug_handler_runtime_mins
)
VALUES {{values}};
"""


# **********************************************************************************************************************
# SQL Helper Functions
# **********************************************************************************************************************
def sql_str(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def sql_float(value: float | None) -> str:
    return "NULL" if value is None else str(float(value))


# **********************************************************************************************************************
# Database Helper Functions
# **********************************************************************************************************************
def insert_regression_matrix_data_to_pbi_db(args: Args, mssql_connection_obj: ConnectMSSQL, summary: Summary) -> None:
    values = summary.to_db_values(args.setup_name, args.target_version, args.session_id, args.dut_hwsku, args.branch)
    logger.info("Inserting data to regression_matrix table")

    try:
        mssql_connection_obj.query_insert(q := _REGRESSION_MATRIX_COLUMNS_QUERY.format(values=values))
        logger.info(f"Query: {q}")
        logger.info("--------- insert to regression_matrix DB table successfully ---------\n")
    except Exception as e:
        print(f"FAILED TO INSERT DATA TO REGRESSION_MATRIX, ERROR: {e}")


def insert_test_analytics_data_to_pbi_db(args: Args, mssql_connection_obj: ConnectMSSQL, parsed_results: list[TestResult]) -> None:
    values = ""
    for result in parsed_results:
        value = result.to_db_values(args.setup_name, args.session_id, args.dut_hwsku, args.branch, args.target_version)
        values = f"{values}, {value}" if values else value

    if values:
        logger.info("Inserting data to test_analytics table")
        try:
            mssql_connection_obj.query_insert(q := _TEST_ANALYTICS_COLUMNS_QUERY.format(values=values))
            logger.info(f"Query: {q}")
            logger.info("--------- insert to test_analytics DB table successfully ---------\n")
        except Exception as e:
            print(f"FAILED TO INSERT DATA TO TEST_ANALYTICS, ERROR: {e}")


def insert_loganalyzer_bugs_data_to_pbi_db(
    args: Args,
    mssql_connection_obj: ConnectMSSQL,
    loganalyzer_bugs_summary: list[LABug],
) -> None:
    values = ""
    for bug in loganalyzer_bugs_summary:
        value = bug.to_db_values(args.session_id, args.setup_name, args.target_version, args.branch)
        values = f"{values}, {value}" if values else value

    if values:
        logger.info("Inserting data to loganalyzer_bug table")
        try:
            mssql_connection_obj.query_insert(q := _LA_BUG_COLUMNS_QUERY.format(values=values))
            logger.info(f"Query: {q}")
            logger.info("--------- insert to loganalyzer_bug DB table successfully ---------\n")
        except Exception as e:
            print(f"FAILED TO INSERT DATA TO LOGANALYZER_BUG, ERROR: {e}")
