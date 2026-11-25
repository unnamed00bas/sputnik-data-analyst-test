-- Объединение и фильтрация кассовых логов:
-- Воспроизведение объединения таблиц store_checkout_queues (алиас scq)
-- и store_stores (алиас ss) и выборка магазинов id = 98451680 и id = 12864064.
-- Примечание: в исходном файле store_checkout_queues.csv столбец кассы называется checkout_id1,
-- поэтому в результирующей выборке ему задается требуемое имя checkout_id.

SELECT
    scq.checks_number,
    ss.store_id,
    scq.employees_id,
    scq.quantity,
    scq.selling_price,
    scq.checkout_id1 AS checkout_id,
    scq.start_operation_dt,
    scq.end_operation_dt
FROM store_checkout_queues AS scq
INNER JOIN store_stores AS ss
    ON scq.store_uuid = ss.store_uuid
WHERE ss.store_id IN (98451680, 12864064)
ORDER BY
    ss.store_id,
    CAST(scq.checkout_id1 AS INTEGER),
    scq.start_operation_dt,
    scq.end_operation_dt,
    scq.checks_number;
