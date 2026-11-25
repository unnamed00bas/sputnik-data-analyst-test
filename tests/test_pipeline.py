from pathlib import Path
import duckdb
import openpyxl
import pytest

from sputnik_case.data_loader import REQUIRED_COLUMNS, load_filtered_data
from sputnik_case.queues import (
    build_slots_15m,
    enrich_receipts,
    extract_checkout_episodes,
    extract_store_queue_periods,
    sensitivity_grid,
    store_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_filtered_dataset_schema_and_counts():
    df = load_filtered_data(raw_dir=REPO_ROOT / "__missing_raw__")
    assert list(df.columns[:8]) == REQUIRED_COLUMNS
    assert len(df) == 50581
    counts = df["store_id"].value_counts().to_dict()
    assert counts == {12864064: 26387, 98451680: 24194}
    assert df["checks_number"].nunique() == 50581


def test_sql_matches_python_episodes():
    df = load_filtered_data(raw_dir=REPO_ROOT / "__missing_raw__")
    enriched = enrich_receipts(df)
    py_ep = extract_checkout_episodes(enriched)

    con = duckdb.connect()
    con.execute(
        f"""
        CREATE TEMP VIEW store_stores AS
        SELECT * FROM read_csv_auto('{REPO_ROOT / "data" / "store_stores.csv"}');

        CREATE TEMP VIEW store_checkout_queues AS
        SELECT
            f.checks_number,
            s.store_uuid,
            f.employees_id,
            f.quantity,
            f.selling_price,
            CAST(f.checkout_id AS VARCHAR) AS checkout_id1,
            f.start_operation_dt,
            f.end_operation_dt
        FROM read_csv('{REPO_ROOT / "data" / "filtered_queues.csv"}',
                      header=true, delim=',', quote='"',
                      columns={{
                          'checks_number':'BIGINT','store_id':'BIGINT','employees_id':'BIGINT',
                          'quantity':'BIGINT','selling_price':'BIGINT','checkout_id':'BIGINT',
                          'start_operation_dt':'VARCHAR','end_operation_dt':'VARCHAR'
                      }}) f
        JOIN store_stores s ON f.store_id = s.store_id;
        """
    )
    sql1 = (REPO_ROOT / "sql" / "01_merge_and_filter.sql").read_text(encoding="utf-8")
    res1 = con.execute(sql1).fetchdf()
    assert list(res1.columns) == REQUIRED_COLUMNS
    assert len(res1) == 50581

    sql2 = (REPO_ROOT / "sql" / "02_queue_periods.sql").read_text(encoding="utf-8")
    res2 = con.execute(sql2).fetchdf()
    assert len(res2) == len(py_ep) == 4295
    assert int(res2["checks_in_queue"].sum()) == int(py_ep["checks_in_queue"].sum()) == 17847


def test_queue_invariants_and_summary():
    df = load_filtered_data(raw_dir=REPO_ROOT / "__missing_raw__")
    enr = enrich_receipts(df)
    assert (enr["service_sec"] > 0).all()
    assert (enr["gap_sec"].dropna() >= 0).all()

    ep = extract_checkout_episodes(enr)
    slots = build_slots_15m(enr)
    periods = extract_store_queue_periods(slots)
    summary = store_summary(enr, ep, periods).set_index("store_id")

    assert summary.loc[12864064, "queue_checks"] == 9391
    assert summary.loc[98451680, "queue_checks"] == 8456
    assert summary.loc[12864064, "checkout_episodes"] == 2195
    assert summary.loc[98451680, "checkout_episodes"] == 2100
    assert summary.loc[12864064, "sco_checks"] == 7668
    assert summary.loc[98451680, "sco_checks"] == 2110
    assert summary.loc[12864064, "max_chain_checks"] == 23
    assert summary.loc[98451680, "max_chain_checks"] == 15


def test_sensitivity_monotonic():
    df = load_filtered_data(raw_dir=REPO_ROOT / "__missing_raw__")
    grid = sensitivity_grid(df)
    for sid in (12864064, 98451680):
        sub3 = grid[(grid["store_id"] == sid) & (grid["min_chain"] == 3)].sort_values("gap_sec")
        assert list(sub3["queue_checks"]) == sorted(sub3["queue_checks"])
        sub15 = grid[(grid["store_id"] == sid) & (grid["gap_sec"] == 15)].sort_values("min_chain")
        assert list(sub15["queue_checks"]) == sorted(sub15["queue_checks"], reverse=True)


def test_excel_contains_live_formulas():
    xlsx_path = REPO_ROOT / "excel" / "sputnik_queues_solution.xlsx"
    assert xlsx_path.exists()
    wb = openpyxl.load_workbook(xlsx_path, data_only=False, read_only=True)
    expected_sheets = {
        "Описание_и_логика",
        "Сводка_по_магазинам",
        "Часы_и_зоны",
        "Эпизоды_очередей",
        "Слоты_15мин",
        "Данные_и_расчет",
    }
    assert expected_sheets.issubset(set(wb.sheetnames))

    ws_sum = wb["Сводка_по_магазинам"]
    row4 = [c.value for c in next(ws_sum.iter_rows(min_row=4, max_row=4, min_col=3, max_col=12))]
    assert all(isinstance(v, str) and v.startswith("=") for v in row4)

    ws_data = wb["Данные_и_расчет"]
    row10 = [c.value for c in next(ws_data.iter_rows(min_row=10, max_row=10, min_col=9, max_col=17))]
    assert all(isinstance(v, str) and v.startswith("=") for v in row10)
    wb.close()
