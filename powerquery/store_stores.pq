let
    Source = Csv.Document(
        File.Contents("C:\data\store_stores.csv"),
        [Delimiter = ",", Columns = 2, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    PromotedHeaders = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    ChangedTypes = Table.TransformColumnTypes(
        PromotedHeaders,
        {
            {"store_id", Int64.Type},
            {"store_uuid", type text}
        }
    )
in
    ChangedTypes
