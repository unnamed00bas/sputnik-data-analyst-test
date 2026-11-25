"""Главный сценарий: выполняет SQL/Python-анализ, строит графики и собирает Excel-книгу с живыми формулами."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from sputnik_case.data_loader import load_filtered_data, network_audit  # noqa: E402
from sputnik_case.queues import (  # noqa: E402
    enrich_receipts,
    extract_checkout_episodes,
    build_slots_15m,
    extract_store_queue_periods,
    store_summary,
    sensitivity_grid,
)
from sputnik_case.charts import generate_all_charts  # noqa: E402
from sputnik_case.excel_builder import build_workbook  # noqa: E402


def main(build_excel: bool = True, build_charts: bool = True) -> None:
    audit = network_audit()
    if audit is not None:
        print("=== Аудит сети (все 68 магазинов) ===")
        print(
            f"Магазинов: {audit['total_stores']}, чеков всего: {audit['total_raw_rows']:,}, "
            f"несопоставленных store_uuid: {audit['unmatched_rows']}, "
            f"медиана чеков на магазин: {audit['median_store_checks']:.1f}"
        )
        print(
            f"Ранг по числу чеков: 12864064 -> #{audit['rank_12864064']} из 68, "
            f"98451680 -> #{audit['rank_98451680']} из 68\n"
        )

    df = load_filtered_data()
    enriched = enrich_receipts(df)
    episodes = extract_checkout_episodes(enriched)
    slots = build_slots_15m(enriched)
    periods = extract_store_queue_periods(slots)
    summary = store_summary(enriched, episodes, periods)

    print("=== Сводка по целевым магазинам (gap <= 15 сек, цепочка >= 3 чеков) ===")
    print(summary.to_string(index=False))

    print("\n=== Разрез по зонам (Касса 6-8 vs КСО 16-18) ===")
    zone_df = (
        enriched.groupby(["store_id", "zone"], as_index=False)
        .agg(
            checks=("checks_number", "count"),
            queue_checks=("in_queue", "sum"),
            med_service_sec=("service_sec", "median"),
            med_gap_sec=("gap_sec", "median"),
        )
    )
    zone_df["queue_share_pct"] = (zone_df["queue_checks"] * 100.0 / zone_df["checks"]).round(1)
    print(zone_df.to_string(index=False))

    print("\n=== Проверка чувствительности порогов ===")
    print(sensitivity_grid(df).to_string(index=False))

    print("\n=== Топ-10 самых длинных эпизодов очереди на кассах ===")
    print(
        episodes.head(10)[
            ["store_id", "checkout_id", "zone", "checks_in_queue", "queue_start", "queue_end", "duration_min"]
        ].to_string(index=False)
    )

    if build_charts:
        chart_paths = generate_all_charts(enriched, ROOT / "reports" / "figures")
        print(f"\nГрафики сохранены ({len(chart_paths)} шт.):")
        for p in chart_paths:
            print(" -", p.relative_to(ROOT))

    if build_excel:
        xlsx_path = build_workbook(enriched, slots, episodes, ROOT / "excel" / "sputnik_queues_solution.xlsx")
        print(f"\nExcel-книга с формулами сохранена: {xlsx_path.relative_to(ROOT)} ({xlsx_path.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
