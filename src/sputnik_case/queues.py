"""Расчет периодов очередей на кассах: цепочки чеков и 15-минутные слоты нагрузки."""
from __future__ import annotations
import numpy as np
import pandas as pd


DEFAULT_GAP_SEC = 15
DEFAULT_MIN_CHAIN = 3
DEFAULT_SLOT_QUEUE_CHECKS = 6
DEFAULT_SLOT_QUEUE_CHECKOUTS = 2


def enrich_receipts(
    df: pd.DataFrame,
    gap_threshold_sec: int = DEFAULT_GAP_SEC,
    min_chain_len: int = DEFAULT_MIN_CHAIN,
) -> pd.DataFrame:
    """Добавляет длительность обслуживания, паузу до предыдущего чека, цепочки и флаг очереди."""
    out = df.sort_values(
        ["store_id", "checkout_id", "start_dt", "end_dt", "checks_number"],
        kind="mergesort",
    ).reset_index(drop=True).copy()

    out["service_sec"] = (out["end_dt"] - out["start_dt"]).dt.total_seconds().astype("int64")
    out["zone"] = np.where(out["checkout_id"] >= 16, "КСО", "Касса")
    out["date"] = out["start_dt"].dt.date
    out["hour"] = out["start_dt"].dt.hour
    out["dow"] = out["start_dt"].dt.isocalendar().day.astype(int)
    out["slot_15m"] = out["start_dt"].dt.floor("15min")

    same_checkout = (
        (out["store_id"] == out["store_id"].shift(1))
        & (out["checkout_id"] == out["checkout_id"].shift(1))
    )
    same_day = out["date"] == out["date"].shift(1)
    prev_end = out["end_dt"].shift(1)

    gap = (out["start_dt"] - prev_end).dt.total_seconds()
    out["gap_sec"] = np.where(same_checkout, gap, np.nan)
    out["is_fast_handoff"] = np.where(
        same_checkout & same_day & (out["gap_sec"] <= gap_threshold_sec),
        1,
        0,
    )

    new_chain = np.where(out["is_fast_handoff"] == 1, 0, 1)
    out["chain_id"] = new_chain.cumsum()
    chain_sizes = out.groupby("chain_id")["checks_number"].transform("count")
    out["chain_len"] = chain_sizes.astype("int64")
    out["in_queue"] = (out["chain_len"] >= min_chain_len).astype("int64")
    return out


def extract_checkout_episodes(
    enriched: pd.DataFrame,
    min_chain_len: int = DEFAULT_MIN_CHAIN,
) -> pd.DataFrame:
    """Таблица непрерывных эпизодов очереди на отдельных кассах (цепочки длиной >= min_chain_len)."""
    q = enriched[enriched["chain_len"] >= min_chain_len]
    episodes = (
        q.groupby(["store_id", "checkout_id", "zone", "chain_id"], as_index=False)
        .agg(
            checks_in_queue=("checks_number", "count"),
            queue_start=("start_dt", "min"),
            queue_end=("end_dt", "max"),
            total_items=("quantity", "sum"),
            total_revenue=("selling_price", "sum"),
            avg_service_sec=("service_sec", "mean"),
        )
    )
    episodes["duration_min"] = (
        (episodes["queue_end"] - episodes["queue_start"]).dt.total_seconds() / 60.0
    ).round(2)
    episodes["avg_service_sec"] = episodes["avg_service_sec"].round(1)
    episodes = episodes.sort_values(
        ["checks_in_queue", "duration_min", "store_id", "queue_start"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)
    return episodes


def build_slots_15m(
    enriched: pd.DataFrame,
    slot_queue_checks: int = DEFAULT_SLOT_QUEUE_CHECKS,
    slot_queue_checkouts: int = DEFAULT_SLOT_QUEUE_CHECKOUTS,
) -> pd.DataFrame:
    """Агрегация по 15-минутным интервалам и флаг общемагазинной очереди."""
    slots = (
        enriched.groupby(["store_id", "slot_15m"], as_index=False)
        .agg(
            total_checks=("checks_number", "count"),
            queue_checks=("in_queue", "sum"),
            cashier_checks=("zone", lambda s: int((s == "Касса").sum())),
            sco_checks=("zone", lambda s: int((s == "КСО").sum())),
            active_checkouts=("checkout_id", "nunique"),
            capped_service_sec=("service_sec", lambda s: int(np.minimum(s, 300).sum())),
            total_items=("quantity", "sum"),
            total_revenue=("selling_price", "sum"),
        )
    )
    q_co = (
        enriched[enriched["in_queue"] == 1]
        .groupby(["store_id", "slot_15m"])["checkout_id"]
        .nunique()
        .rename("queue_checkouts")
    )
    slots = slots.merge(q_co, on=["store_id", "slot_15m"], how="left")
    slots["queue_checkouts"] = slots["queue_checkouts"].fillna(0).astype(int)
    slots["queue_share_pct"] = (slots["queue_checks"] * 100.0 / slots["total_checks"]).round(1)
    slots["busy_checkout_equiv"] = (slots["capped_service_sec"] / 900.0).round(2)
    slots["is_store_queue_slot"] = (
        (slots["queue_checks"] >= slot_queue_checks)
        | (slots["queue_checkouts"] >= slot_queue_checkouts)
    ).astype(int)
    return slots.sort_values(["store_id", "slot_15m"]).reset_index(drop=True)


def extract_store_queue_periods(slots: pd.DataFrame) -> pd.DataFrame:
    """Объединяет смежные 15-минутные пиковые слоты в непрерывные периоды очереди по магазину."""
    peak = slots[slots["is_store_queue_slot"] == 1].sort_values(["store_id", "slot_15m"]).copy()
    prev_slot = peak.groupby("store_id")["slot_15m"].shift(1)
    is_new = ((peak["slot_15m"] - prev_slot) != pd.Timedelta(minutes=15)).astype(int)
    peak["period_id"] = is_new.cumsum()

    periods = (
        peak.groupby(["store_id", "period_id"], as_index=False)
        .agg(
            period_start=("slot_15m", "min"),
            last_slot=("slot_15m", "max"),
            slots_count=("slot_15m", "count"),
            total_checks=("total_checks", "sum"),
            queue_checks=("queue_checks", "sum"),
            max_active_checkouts=("active_checkouts", "max"),
        )
    )
    periods["period_end"] = periods["last_slot"] + pd.Timedelta(minutes=15)
    periods["duration_min"] = periods["slots_count"] * 15
    periods = periods.drop(columns=["last_slot"])
    return periods.sort_values(["store_id", "period_start"]).reset_index(drop=True)


def store_summary(enriched: pd.DataFrame, episodes: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    """Сводные показатели по каждому магазину."""
    rows = []
    for sid, g in enriched.groupby("store_id"):
        ep = episodes[episodes["store_id"] == sid]
        pr = periods[periods["store_id"] == sid]
        total = len(g)
        sco = int((g["zone"] == "КСО").sum())
        q_checks = int(g["in_queue"].sum())
        rows.append(
            {
                "store_id": int(sid),
                "total_checks": total,
                "active_checkouts": int(g["checkout_id"].nunique()),
                "active_employees": int(g["employees_id"].nunique()),
                "cashier_checks": total - sco,
                "sco_checks": sco,
                "sco_share_pct": round(sco * 100.0 / total, 1),
                "median_service_sec": float(g["service_sec"].median()),
                "avg_service_sec": round(float(g["service_sec"].mean()), 1),
                "median_gap_sec": float(g["gap_sec"].dropna().median()),
                "queue_checks": q_checks,
                "queue_share_pct": round(q_checks * 100.0 / total, 1),
                "checkout_episodes": int(len(ep)),
                "avg_episode_min": round(float(ep["duration_min"].mean()), 2),
                "max_chain_checks": int(ep["checks_in_queue"].max()),
                "store_queue_periods": int(len(pr)),
                "store_queue_hours": round(float(pr["duration_min"].sum()) / 60.0, 1),
                "max_store_period_min": int(pr["duration_min"].max()),
            }
        )
    return pd.DataFrame(rows).sort_values("store_id").reset_index(drop=True)


def sensitivity_grid(df: pd.DataFrame) -> pd.DataFrame:
    """Проверка устойчивости числа эпизодов очереди при разных порогах G (сек) и N (чеков)."""
    records = []
    for g_sec in (10, 15, 20):
        enr = enrich_receipts(df, gap_threshold_sec=g_sec, min_chain_len=3)
        for min_n in (3, 4, 5):
            ep = extract_checkout_episodes(enr, min_chain_len=min_n)
            for sid, grp in ep.groupby("store_id"):
                total_checks = int((df["store_id"] == sid).sum())
                q_checks = int(grp["checks_in_queue"].sum())
                records.append(
                    {
                        "gap_sec": g_sec,
                        "min_chain": min_n,
                        "store_id": int(sid),
                        "episodes": int(len(grp)),
                        "queue_checks": q_checks,
                        "queue_share_pct": round(q_checks * 100.0 / total_checks, 1),
                        "total_queue_min": round(float(grp["duration_min"].sum()), 1),
                        "avg_episode_min": round(float(grp["duration_min"].mean()), 2),
                    }
                )
    return pd.DataFrame(records)
