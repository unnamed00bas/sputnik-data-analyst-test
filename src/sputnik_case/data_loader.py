"""Загрузка данных и проверка качества исходных CSV и SQL-запросов."""
from pathlib import Path
import duckdb
import pandas as pd

TARGET_STORES = (98451680, 12864064)
REQUIRED_COLUMNS = [
    "checks_number",
    "store_id",
    "employees_id",
    "quantity",
    "selling_price",
    "checkout_id",
    "start_operation_dt",
    "end_operation_dt",
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT.parent / "raw"
DEFAULT_FILTERED_CSV = REPO_ROOT / "data" / "filtered_queues.csv"
DEFAULT_STORES_CSV = REPO_ROOT / "data" / "store_stores.csv"


def load_filtered_data(
    raw_dir: Path | None = None,
    filtered_csv: Path | None = None,
) -> pd.DataFrame:
    """Читает объединенную и отфильтрованную выборку (из raw CSV или готового data/filtered_queues.csv)."""
    raw_dir = raw_dir or DEFAULT_RAW_DIR
    filtered_csv = filtered_csv or DEFAULT_FILTERED_CSV

    raw_queues = raw_dir / "store_checkout_queues.csv"
    raw_stores = raw_dir / "store_stores.csv"

    con = duckdb.connect()
    if raw_queues.exists() and raw_stores.exists():
        sql = (REPO_ROOT / "sql" / "01_merge_and_filter.sql").read_text(encoding="utf-8")
        con.execute(
            f"""
            CREATE TEMP VIEW store_checkout_queues AS
            SELECT * FROM read_csv('{raw_queues}', header=true, delim=',', quote='"',
                columns={{
                    'checks_number':'BIGINT',
                    'store_uuid':'VARCHAR',
                    'employees_id':'BIGINT',
                    'quantity':'BIGINT',
                    'selling_price':'BIGINT',
                    'checkout_id1':'VARCHAR',
                    'start_operation_dt':'VARCHAR',
                    'end_operation_dt':'VARCHAR'
                }});
            CREATE TEMP VIEW store_stores AS
            SELECT * FROM read_csv_auto('{raw_stores}');
            """
        )
        # Выполняем точный SQL-запрос из задания, затем сортируем с парсингом дат
        df = con.execute(sql).fetchdf()
    elif filtered_csv.exists():
        df = con.execute(
            f"""
            SELECT checks_number, store_id, employees_id, quantity, selling_price,
                   checkout_id, start_operation_dt, end_operation_dt
            FROM read_csv('{filtered_csv}', header=true, delim=',', quote='"',
                columns={{
                    'checks_number':'BIGINT',
                    'store_id':'BIGINT',
                    'employees_id':'BIGINT',
                    'quantity':'BIGINT',
                    'selling_price':'BIGINT',
                    'checkout_id':'BIGINT',
                    'start_operation_dt':'VARCHAR',
                    'end_operation_dt':'VARCHAR'
                }})
            """
        ).fetchdf()
    else:
        raise FileNotFoundError(
            f"Не найдены ни исходные файлы в {raw_dir}, ни {filtered_csv}"
        )

    df["checkout_id"] = df["checkout_id"].astype(int)
    df["start_dt"] = pd.to_datetime(df["start_operation_dt"], format="%d.%m.%Y %H:%M:%S")
    df["end_dt"] = pd.to_datetime(df["end_operation_dt"], format="%d.%m.%Y %H:%M:%S")
    df = df.sort_values(
        ["store_id", "checkout_id", "start_dt", "end_dt", "checks_number"],
        kind="mergesort",
    ).reset_index(drop=True)
    return df


def network_audit(raw_dir: Path | None = None) -> dict | None:
    """Возвращает аудит качества по полным CSV (если raw файлы присутствуют)."""
    raw_dir = raw_dir or DEFAULT_RAW_DIR
    raw_queues = raw_dir / "store_checkout_queues.csv"
    raw_stores = raw_dir / "store_stores.csv"
    if not (raw_queues.exists() and raw_stores.exists()):
        return None

    con = duckdb.connect()
    row = con.execute(
        f"""
        WITH q AS (
            SELECT * FROM read_csv('{raw_queues}', header=true, delim=',', quote='"',
                columns={{
                    'checks_number':'BIGINT','store_uuid':'VARCHAR','employees_id':'BIGINT',
                    'quantity':'BIGINT','selling_price':'BIGINT','checkout_id1':'VARCHAR',
                    'start_operation_dt':'VARCHAR','end_operation_dt':'VARCHAR'
                }})
        ),
        s AS (SELECT * FROM read_csv_auto('{raw_stores}')),
        per_store AS (
            SELECT s.store_id, COUNT(*) AS checks,
                   ROUND(100.0 * SUM(CASE WHEN TRY_CAST(q.checkout_id1 AS INT) >= 16 THEN 1 ELSE 0 END) / COUNT(*), 1) AS sco_pct
            FROM q JOIN s ON q.store_uuid = s.store_uuid
            GROUP BY s.store_id
        ),
        ranked AS (
            SELECT *, DENSE_RANK() OVER (ORDER BY checks DESC) AS rank_by_checks
            FROM per_store
        )
        SELECT
            (SELECT COUNT(*) FROM s) AS total_stores,
            (SELECT COUNT(*) FROM q) AS total_raw_rows,
            (SELECT COUNT(*) FROM q LEFT JOIN s ON q.store_uuid = s.store_uuid WHERE s.store_uuid IS NULL) AS unmatched_rows,
            (SELECT MEDIAN(checks) FROM per_store) AS median_store_checks,
            (SELECT rank_by_checks FROM ranked WHERE store_id = 12864064) AS rank_12864064,
            (SELECT rank_by_checks FROM ranked WHERE store_id = 98451680) AS rank_98451680
        """
    ).fetchone()
    return {
        "total_stores": int(row[0]),
        "total_raw_rows": int(row[1]),
        "unmatched_rows": int(row[2]),
        "median_store_checks": float(row[3]),
        "rank_12864064": int(row[4]),
        "rank_98451680": int(row[5]),
    }
