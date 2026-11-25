"""Построение графиков анализа очередей по магазинам 12864064 и 98451680."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Liberation Sans", "Arial"]
plt.rcParams["axes.edgecolor"] = "#cccccc"
plt.rcParams["axes.linewidth"] = 0.8

COLOR_128 = "#1f6feb"
COLOR_984 = "#e36209"
COLOR_SCO = "#2da44e"


def generate_all_charts(enriched: pd.DataFrame, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return [
        _chart_hourly_profile(enriched, out_dir / "01_hourly_load_and_queues.png"),
        _chart_gap_distribution(enriched, out_dir / "02_gap_distribution.png"),
        _chart_cashier_vs_sco(enriched, out_dir / "03_cashier_vs_sco_mix.png"),
        _chart_daily_and_dow(enriched, out_dir / "04_daily_and_weekday_queues.png"),
    ]


def _chart_hourly_profile(enriched: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), dpi=160)
    hours = np.arange(24)

    for ax_idx, (sid, title, col) in enumerate([
        (12864064, "Магазин 12864064 (дневной, 08:00 - 23:00)", COLOR_128),
        (98451680, "Магазин 98451680 (круглосуточный, 24/7)", COLOR_984),
    ]):
        ax = axes[ax_idx]
        sub = enriched[enriched["store_id"] == sid]
        grp = sub.groupby("hour").agg(
            total=("checks_number", "count"),
            q_cnt=("in_queue", "sum"),
        ).reindex(hours, fill_value=0)
        grp["q_pct"] = np.where(grp["total"] > 0, grp["q_cnt"] * 100.0 / grp["total"], 0.0)

        ax.bar(hours, grp["total"], color=col, alpha=0.35, label="Всего чеков за период")
        ax.set_title(title, fontsize=11, fontweight="bold", pad=10)
        ax.set_xlabel("Час суток", fontsize=9.5)
        ax.set_ylabel("Количество чеков", fontsize=9.5, color="#333333")
        ax.set_xticks(hours)
        ax.set_xticklabels([f"{h:02d}" for h in hours], fontsize=8)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.set_ylim(0, grp["total"].max() * 1.24)

        ax2 = ax.twinx()
        ax2.plot(hours, grp["q_pct"], color=col, marker="o", linewidth=2.2, markersize=4.5,
                 label="Доля чеков в очереди (%)")
        ax2.set_ylabel("Доля чеков в очереди, %", fontsize=9.5, color=col)
        ax2.set_ylim(0, 62)
        ax2.spines["top"].set_visible(False)

        if sid == 12864064:
            ax2.annotate("Пики: 17:00 (40,1%) и 20:00 (41,2%)", xy=(20, 41.2), xytext=(9.5, 53),
                         arrowprops=dict(arrowstyle="->", color=col, lw=1.2), fontsize=8.5, fontweight="bold", color=col)
        else:
            ax2.annotate("Обеденный пик:\n12:00 (47,5%)", xy=(12, 47.5), xytext=(15.0, 52.0),
                         arrowprops=dict(arrowstyle="->", color=col, lw=1.2), fontsize=8.5, fontweight="bold", color=col)

        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=True)

    fig.suptitle("Почасовая нагрузка и доля чеков в очередях (порог: пауза <= 15 сек, цепочка >= 3 чеков)",
                 fontsize=12.5, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_gap_distribution(enriched: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.0), dpi=160)

    ax = axes[0]
    secs = np.arange(0, 41)
    for sid, label, col in [
        (12864064, "Магазин 12864064 (Кассы 6-8)", COLOR_128),
        (98451680, "Магазин 98451680 (Кассы 6-8)", COLOR_984),
    ]:
        sub = enriched[(enriched["store_id"] == sid) & (enriched["zone"] == "Касса") & (enriched["gap_sec"].between(0, 40))]
        cnts = sub["gap_sec"].astype(int).value_counts().reindex(secs, fill_value=0)
        ax.plot(secs, cnts.values, marker=".", linewidth=2, color=col, label=label)

    ax.axvline(15, color="#cf222e", linestyle="--", linewidth=1.8, label="Выбранный порог 15 сек")
    ax.axvspan(0, 15, color="#cf222e", alpha=0.07)
    ax.set_title("Распределение пауз между чеками на кассах (0 - 40 сек)", fontsize=11, fontweight="bold")
    ax.set_xlabel("Пауза до предыдущего чека (gap_sec), сек", fontsize=9.5)
    ax.set_ylabel("Число переходов", fontsize=9.5)
    ax.set_ylim(0, 1620)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.annotate("Пик пересменки 4 сек\n(1468 и 1389 переходов)", xy=(4, 1468), xytext=(17, 1020),
                arrowprops=dict(arrowstyle="->", color="#333333"), fontsize=8.5,
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#dddddd", alpha=0.9))
    ax.legend(fontsize=8.5, loc="upper right")

    ax2 = axes[1]
    configs = [("10c, >=3", 10, 3), ("15c, >=3 (база)", 15, 3), ("15c, >=4", 15, 4), ("20c, >=3", 20, 3)]
    x = np.arange(len(configs))
    w = 0.36
    vals_128, vals_984 = [], []
    from sputnik_case.queues import enrich_receipts
    for _, g_s, n_min in configs:
        tmp = enrich_receipts(enriched[["checks_number", "store_id", "employees_id", "quantity",
                                        "selling_price", "checkout_id", "start_operation_dt",
                                        "end_operation_dt", "start_dt", "end_dt"]],
                              gap_threshold_sec=g_s, min_chain_len=n_min)
        vals_128.append(tmp.loc[tmp["store_id"] == 12864064, "in_queue"].mean() * 100.0)
        vals_984.append(tmp.loc[tmp["store_id"] == 98451680, "in_queue"].mean() * 100.0)

    b1 = ax2.bar(x - w / 2, vals_128, width=w, color=COLOR_128, alpha=0.85, label="Магазин 12864064")
    b2 = ax2.bar(x + w / 2, vals_984, width=w, color=COLOR_984, alpha=0.85, label="Магазин 98451680")
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, h + 0.8, f"{h:.1f}%", ha="center", va="bottom", fontsize=8.5)
    ax2.set_title("Чувствительность доли очереди к выбору порогов", fontsize=11, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels([c[0] for c in configs], fontsize=9)
    ax2.set_ylabel("Доля чеков в очередях, %", fontsize=9.5)
    ax2.set_ylim(0, 56)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)
    ax2.legend(fontsize=8.5)

    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_cashier_vs_sco(enriched: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.2), dpi=160)
    co_order = [6, 7, 8, 16, 17, 18]
    x = np.arange(len(co_order))

    for idx, (sid, title) in enumerate([
        (12864064, "Магазин 12864064: доля КСО 29,1% (7 668 чеков)"),
        (98451680, "Магазин 98451680: доля КСО 8,7% (2 110 чеков)"),
    ]):
        ax = axes[idx]
        sub = enriched[enriched["store_id"] == sid]
        grp = sub.groupby("checkout_id").agg(
            total=("checks_number", "count"),
            q_cnt=("in_queue", "sum"),
        ).reindex(co_order, fill_value=0)
        grp["no_q"] = grp["total"] - grp["q_cnt"]
        grp["q_pct"] = np.where(grp["total"] > 0, grp["q_cnt"] * 100.0 / grp["total"], 0.0)

        ax.bar(x, grp["q_cnt"], color="#cf222e", alpha=0.82, label="Чеки в очередях")
        ax.bar(x, grp["no_q"], bottom=grp["q_cnt"], color="#8c959f", alpha=0.45, label="Чеки без очереди")
        for i, co in enumerate(co_order):
            tot = grp.loc[co, "total"]
            qp = grp.loc[co, "q_pct"]
            if tot > 0:
                ax.text(i, tot + 220, f"{tot:,}\n({qp:.0f}% оч.)".replace(",", " "),
                        ha="center", va="bottom", fontsize=8)
        ax.axvline(2.5, color="#333333", linestyle=":", linewidth=1.2)
        ax.text(1.0, 14400, "Обычные кассы (6-8)", ha="center", fontsize=9, fontweight="bold", color="#333333")
        ax.text(4.0, 11400, "КСО (16-18)", ha="center", fontsize=9, fontweight="bold", color=COLOR_SCO)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels([f"Касса {c}" for c in co_order], fontsize=8.5)
        ax.set_ylabel("Чеков за период", fontsize=9.5)
        ax.set_ylim(0, 15600)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.legend(fontsize=8.5, loc="upper right")

    fig.suptitle("Распределение чеков и очередей между обычными кассами и кассами самообслуживания (КСО)",
                 fontsize=12.5, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path


def _chart_daily_and_dow(enriched: pd.DataFrame, path: Path) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 4.9), dpi=160, gridspec_kw={"width_ratios": [1.55, 1]})

    ax = axes[0]
    for sid, label, col in [
        (12864064, "Магазин 12864064", COLOR_128),
        (98451680, "Магазин 98451680", COLOR_984),
    ]:
        sub = enriched[enriched["store_id"] == sid]
        daily = sub.groupby("date").agg(
            total=("checks_number", "count"),
            q_cnt=("in_queue", "sum"),
        )
        daily.index = pd.to_datetime(daily.index)
        ax.plot(daily.index, daily["q_cnt"], marker="o", markersize=3.5, linewidth=1.8, color=col, label=f"{label}: чеки в очередях")

    ax.axvspan(pd.Timestamp("2024-11-21"), pd.Timestamp("2024-11-26 12:00"), color="#8c959f", alpha=0.14)
    ax.text(pd.Timestamp("2024-11-23 12:00"), 230, "Неполные дни\n(9-18 чек/сут)", ha="center", fontsize=8, color="#555555")
    ax.set_title("Чеки в очередях по дням (21.11.2024 - 26.12.2024)", fontsize=11, fontweight="bold")
    ax.set_ylabel("Чеков в очередях за день", fontsize=9.5)
    ax.set_ylim(-20, 535)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(fontsize=8.5, loc="upper left")

    ax2 = axes[1]
    dows = [1, 2, 3, 4, 5, 6, 7]
    dow_labels = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    w = 0.36
    x = np.arange(7)
    for offset, sid, label, col in [
        (-w / 2, 12864064, "12864064", COLOR_128),
        (+w / 2, 98451680, "98451680", COLOR_984),
    ]:
        sub = enriched[enriched["store_id"] == sid]
        grp = sub.groupby("dow").agg(total=("checks_number", "count"), q=("in_queue", "sum")).reindex(dows)
        pct = grp["q"] * 100.0 / grp["total"]
        bars = ax2.bar(x + offset, pct.values, width=w, color=col, alpha=0.85, label=label)
        for bar in bars:
            h = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width() / 2, h + 0.5, f"{h:.0f}%", ha="center", va="bottom", fontsize=7.5)

    ax2.set_title("Доля чеков в очереди по дням недели", fontsize=11, fontweight="bold")
    ax2.set_xticks(x)
    ax2.set_xticklabels(dow_labels, fontsize=9)
    ax2.set_ylabel("Доля чеков в очередях, %", fontsize=9.5)
    ax2.set_ylim(0, 48)
    ax2.grid(axis="y", linestyle="--", alpha=0.4)
    ax2.legend(fontsize=8.5)

    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
