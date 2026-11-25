# Power Query (шаги 1 и 2)

В этой папке лежит готовый M-код для надстройки Power Query в Excel.

## Логика объединения и фильтрации

1. Запрос `store_stores.pq` читает справочник `store_stores.csv` (кодировка UTF-8, разделитель `,`), поднимает заголовки и приводит `store_id` к целому числу (`Int64.Type`), а `store_uuid` к тексту.
2. Запрос `store_checkout_queues.pq` читает `store_checkout_queues.csv` (8 столбцов, разделитель `,`).
3. Выполняется внутреннее объединение (`JoinKind.Inner`) с запросом `store_stores` по полю `store_uuid`, после чего из связанной таблицы разворачивается поле `store_id`.
4. Поле `checkout_id1` переименовывается в `checkout_id`.
5. Оставляются ровно 8 целевых столбцов в нужном порядке: `checks_number`, `store_id`, `employees_id`, `quantity`, `selling_price`, `checkout_id`, `start_operation_dt`, `end_operation_dt`.
6. Даты `start_operation_dt` и `end_operation_dt` приводятся к типу `datetime` с локалью `"ru-RU"` (формат `dd.MM.yyyy HH:mm:ss`).
7. Фильтр `Table.SelectRows` отбирает магазины `98451680` и `12864064`, а сортировка по `store_id -> checkout_id -> start_operation_dt` подготавливает таблицу к расчетам очереди формулами Excel без пересохранения в значения.

## Как применить в Excel

1. В Excel открыть **Данные -> Получить данные -> Из файла -> Из текстового/CSV-файла** (или через **Пустой запрос** в редакторе Power Query).
2. Создать запрос `store_stores` из `store_stores.pq` (только подключение).
3. Создать запрос `store_checkout_queues` из `store_checkout_queues.pq` и выгрузить таблицу на лист (заменив путь `C:\data\...` на локальный путь к файлам).
