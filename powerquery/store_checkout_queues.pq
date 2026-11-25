let
    Source = Csv.Document(
        File.Contents("C:\data\store_checkout_queues.csv"),
        [Delimiter = ",", Columns = 8, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    MergedStores = Table.NestedJoin(
        PromotedHeaders,
        {"store_uuid"},
        store_stores,
        {"store_uuid"},
        "ss",
        JoinKind.Inner
    ),
    ExpandedStoreId = Table.ExpandTableColumn(MergedStores, "ss", {"store_id"}, {"store_id"}),
    RenamedCheckout = Table.RenameColumns(ExpandedStoreId, {{"checkout_id1", "checkout_id"}}),
    SelectedColumns = Table.SelectColumns(
        RenamedCheckout,
        {
            "checks_number",
            "store_id",
            "employees_id",
            "quantity",
            "selling_price",
            "checkout_id",
            "start_operation_dt",
            "end_operation_dt"
        }
    ),
    TypedColumns = Table.TransformColumnTypes(
        SelectedColumns,
        {
            {"checks_number", Int64.Type},
            {"store_id", Int64.Type},
            {"employees_id", Int64.Type},
            {"quantity", Int64.Type},
            {"selling_price", Int64.Type},
            {"checkout_id", Int64.Type},
            {"start_operation_dt", type datetime},
            {"end_operation_dt", type datetime}
        },
        "ru-RU"
    ),
    FilteredStores = Table.SelectRows(
        TypedColumns,
        each ([store_id] = 98451680 or [store_id] = 12864064)
    ),
    SortedRows = Table.Sort(
        FilteredStores,
        {
            {"store_id", Order.Ascending},
            {"checkout_id", Order.Ascending},
            {"start_operation_dt", Order.Ascending},
            {"end_operation_dt", Order.Ascending},
            {"checks_number", Order.Ascending}
        }
    )
in
    SortedRows
