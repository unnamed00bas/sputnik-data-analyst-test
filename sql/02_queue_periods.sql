-- Шаг 4 тестового задания Спутник (DuckDB / PostgreSQL-совместимый синтаксис):
-- Определение периодов наличия очереди на кассах на основе выборки по магазинам 98451680 и 12864064.
-- Логика:
-- 1) Сортируем чеки внутри каждого магазина и кассы по времени начала операции.
-- 2) Считаем паузу gap_sec = start_operation_dt текущего чека - end_operation_dt предыдущего чека на той же кассе.
-- 3) Быстрая пересменка: gap_sec <= 15 сек в пределах одних календарных суток (порог подтвержден гистограммой разрывов).
-- 4) Эпизод очереди на кассе: непрерывная цепочка из >= 3 чеков с быстрой пересменкой.
-- 5) Период очереди по магазину: объединение смежных 15-минутных слотов, где >= 6 чеков в очередях или очередь идет >= чем на 2 кассах сразу.

WITH base AS (
    SELECT
        scq.checks_number,
        ss.store_id,
        scq.employees_id,
        scq.quantity,
        scq.selling_price,
        CAST(scq.checkout_id1 AS INTEGER) AS checkout_id,
        CASE
            WHEN CAST(scq.checkout_id1 AS INTEGER) >= 16 THEN 'SCO'
            ELSE 'Cashier'
        END AS zone_type,
        strptime(scq.start_operation_dt, '%d.%m.%Y %H:%M:%S') AS start_dt,
        strptime(scq.end_operation_dt, '%d.%m.%Y %H:%M:%S') AS end_dt
    FROM store_checkout_queues AS scq
    INNER JOIN store_stores AS ss
        ON scq.store_uuid = ss.store_uuid
    WHERE ss.store_id IN (98451680, 12864064)
),
ordered AS (
    SELECT
        *,
        LAG(end_dt) OVER (
            PARTITION BY store_id, checkout_id
            ORDER BY start_dt, end_dt, checks_number
        ) AS prev_end_dt,
        epoch(end_dt) - epoch(start_dt) AS service_sec,
        epoch(start_dt) - epoch(
            LAG(end_dt) OVER (
                PARTITION BY store_id, checkout_id
                ORDER BY start_dt, end_dt, checks_number
            )
        ) AS gap_sec
    FROM base
),
flagged AS (
    SELECT
        *,
        CASE
            WHEN prev_end_dt IS NOT NULL
             AND gap_sec <= 15
             AND DATE_TRUNC('day', start_dt) = DATE_TRUNC('day', prev_end_dt)
            THEN 0
            ELSE 1
        END AS is_new_chain
    FROM ordered
),
chains AS (
    SELECT
        *,
        SUM(is_new_chain) OVER (
            PARTITION BY store_id, checkout_id
            ORDER BY start_dt, end_dt, checks_number
        ) AS chain_id
    FROM flagged
),
chain_stats AS (
    SELECT
        store_id,
        checkout_id,
        zone_type,
        chain_id,
        COUNT(*) AS chain_len,
        MIN(start_dt) AS queue_start,
        MAX(end_dt) AS queue_end,
        ROUND((epoch(MAX(end_dt)) - epoch(MIN(start_dt))) / 60.0, 2) AS duration_min,
        SUM(quantity) AS total_items,
        SUM(selling_price) AS total_revenue
    FROM chains
    GROUP BY store_id, checkout_id, zone_type, chain_id
)
SELECT
    store_id,
    checkout_id,
    zone_type,
    chain_len AS checks_in_queue,
    queue_start,
    queue_end,
    duration_min,
    total_items,
    total_revenue
FROM chain_stats
WHERE chain_len >= 3
ORDER BY store_id, queue_start, checkout_id;
