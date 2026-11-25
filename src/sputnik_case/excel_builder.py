"""Генератор Excel-книги решения с живыми формулами (без пересохранения в значения)."""
from __future__ import annotations
from pathlib import Path
import openpyxl
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd


HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
SUB_FILL = PatternFill("solid", fgColor="D9E1F2")
PARAM_FILL = PatternFill("solid", fgColor="FFF2CC")
BOLD_FONT = Font(name="Calibri", size=10, bold=True)
BASE_FONT = Font(name="Calibri", size=10)
TITLE_FONT = Font(name="Calibri", size=14, bold=True, color="1F4E78")
THIN_BORDER = Border(
    left=Side(style="thin", color="D9D9D9"),
    right=Side(style="thin", color="D9D9D9"),
    top=Side(style="thin", color="D9D9D9"),
    bottom=Side(style="thin", color="D9D9D9"),
)


def build_workbook(
    df_sorted: pd.DataFrame,
    slots_df: pd.DataFrame,
    episodes_df: pd.DataFrame,
    out_path: Path,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()

    n_rows = len(df_sorted)
    last_data_row = n_rows + 1
    n_slots = len(slots_df)
    last_slot_row = n_slots + 1

    ws_desc = wb.active
    ws_desc.title = "Описание_и_логика"
    _build_desc_sheet(ws_desc)

    ws_sum = wb.create_sheet("Сводка_по_магазинам")
    _build_summary_sheet(ws_sum, last_data_row, last_slot_row)

    ws_hr = wb.create_sheet("Часы_и_зоны")
    _build_hourly_sheet(ws_hr, last_data_row)

    ws_ep = wb.create_sheet("Эпизоды_очередей")
    _build_episodes_sheet(ws_ep, episodes_df)

    ws_slots = wb.create_sheet("Слоты_15мин")
    _build_slots_sheet(ws_slots, slots_df, last_data_row)

    ws_data = wb.create_sheet("Данные_и_расчет")
    _build_data_sheet(ws_data, df_sorted, last_data_row)

    wb.save(out_path)
    return out_path


def _style_header(ws, row: int, max_col: int) -> None:
    ws.row_dimensions[row].height = 24
    for col in range(1, max_col + 1):
        c = ws.cell(row=row, column=col)
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = THIN_BORDER


def _build_desc_sheet(ws) -> None:
    ws["A1"] = "Анализ очередей на кассах розничной сети"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Модель полностью построена на живых формулах Excel без пересохранения в значения."
    ws["A2"].font = BASE_FONT

    ws["A4"] = "Параметр модели"
    ws["B4"] = "Описание"
    ws["C4"] = "Значение"
    ws["D4"] = "Единица измерения"
    _style_header(ws, 4, 4)

    params = [
        ("Порог быстрой пересменки", "Макс. пауза от закрытия предыдущего чека до открытия следующего на той же кассе", 15, "сек"),
        ("Мин. длина цепочки", "Мин. число чеков подряд с быстрой пересменкой для фиксации очереди на кассе", 3, "чеков"),
        ("Порог пикового слота", "Мин. число чеков в очередях за 15 мин для фиксации общемагазинной очереди", 6, "чеков / 15 мин"),
    ]
    for idx, (name, desc, val, unit) in enumerate(params, start=5):
        ws.cell(idx, 1, name).font = BOLD_FONT
        ws.cell(idx, 2, desc).font = BASE_FONT
        c_val = ws.cell(idx, 3, val)
        c_val.fill = PARAM_FILL
        c_val.font = BOLD_FONT
        c_val.alignment = Alignment(horizontal="center")
        ws.cell(idx, 4, unit).font = BASE_FONT
        for col in range(1, 5):
            ws.cell(idx, col).border = THIN_BORDER

    notes = [
        "",
        "1. Объединение данных (Power Query и SQL):",
        "- Таблица store_checkout_queues объединена со справочником store_stores по ключу store_uuid (внутреннее соединение, 0 несопоставленных строк).",
        "- Поле checkout_id1 переименовано в checkout_id; оставлены ровно 8 требуемых столбцов.",
        "- Выполнена выборка по целевым магазинам store_id = 98451680 и store_id = 12864064 (50 581 чек, период 21.11.2024 - 26.12.2024).",
        "",
        "2. Методика определения периодов очереди на кассах:",
        "- Данные отсортированы по магазину -> номеру кассы -> времени начала операции.",
        "- Для каждого чека формулой вычисляется пауза Пауза_сек = start_operation_dt(текущий) - end_operation_dt(предыдущий) на той же кассе.",
        "- Гистограмма пауз показала выраженный пик пересменки на 3-5 сек и серию пиков до 15 сек; кассы 6-8 работают с кассиром, кассы 16-18 - это КСО (employees_id = 599).",
        "- Цепочка из >= 3 чеков подряд с паузой <= 15 сек в пределах одних суток фиксирует эпизод очереди на кассе (листы Данные_и_расчет и Эпизоды_очередей).",
        "- На листе Слоты_15мин нагрузка агрегируется по 15-минутным интервалам формулами COUNTIFS/SUMIFS по целочисленному ключу слота, выделяются пиковые периоды магазина.",
        "",
        "3. Структура листов:",
        "- Сводка_по_магазинам: итоговые KPI по магазинам и типам касс (формулы COUNTIFS, SUMIFS, AVERAGEIFS).",
        "- Часы_и_зоны: почасовой профиль трафика и доли очередей + график.",
        "- Эпизоды_очередей: выявленные непрерывные цепочки очередей на кассах (отсортированы по длине).",
        "- Слоты_15мин: 15-минутные интервалы и объединенные периоды пиковой очереди магазина.",
        "- Данные_и_расчет: 50 581 строка выборки с 9 формульными столбцами (I:Q).",
    ]
    for offset, line in enumerate(notes, start=9):
        cell = ws.cell(offset, 1, line)
        cell.font = BOLD_FONT if line and line[0].isdigit() else BASE_FONT

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 62
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 18


def _build_summary_sheet(ws, last_data_row: int, last_slot_row: int) -> None:
    ws["A1"] = "Сводка показателей очередей по магазинам (живые формулы)"
    ws["A1"].font = TITLE_FONT

    headers = [
        "store_id", "Режим работы", "Всего чеков", "Чеков на КСО",
        "Доля КСО", "Чеков в очередях", "Доля очередей",
        "Ср. обсл., сек", "Ср. пауза (между чеками), сек",
        "Выручка всего, руб", "Пиковых 15-мин слотов", "Часов пиковой очереди"
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(3, c, h)
    _style_header(ws, 3, len(headers))

    d_rng_sid = f"Данные_и_расчет!$B$2:$B${last_data_row}"
    d_rng_zone = f"Данные_и_расчет!$J$2:$J${last_data_row}"
    d_rng_q = f"Данные_и_расчет!$O$2:$O${last_data_row}"
    d_rng_dur = f"Данные_и_расчет!$I$2:$I${last_data_row}"
    d_rng_gap = f"Данные_и_расчет!$K$2:$K${last_data_row}"
    d_rng_rev = f"Данные_и_расчет!$E$2:$E${last_data_row}"
    s_rng_sid = f"Слоты_15мин!$A$2:$A${last_slot_row}"
    s_rng_peak = f"Слоты_15мин!$J$2:$J${last_slot_row}"

    stores = [(12864064, "Дневной (08:00-23:00)"), (98451680, "Круглосуточный (24/7)")]
    for idx, (sid, mode) in enumerate(stores, start=4):
        ws.cell(idx, 1, sid)
        ws.cell(idx, 2, mode)
        ws.cell(idx, 3, f"=COUNTIFS({d_rng_sid}, A{idx})")
        ws.cell(idx, 4, f'=COUNTIFS({d_rng_sid}, A{idx}, {d_rng_zone}, "КСО")')
        ws.cell(idx, 5, f"=IF(C{idx}>0, D{idx}/C{idx}, 0)")
        ws.cell(idx, 6, f"=COUNTIFS({d_rng_sid}, A{idx}, {d_rng_q}, 1)")
        ws.cell(idx, 7, f"=IF(C{idx}>0, F{idx}/C{idx}, 0)")
        ws.cell(idx, 8, f"=AVERAGEIFS({d_rng_dur}, {d_rng_sid}, A{idx})")
        ws.cell(idx, 9, f"=AVERAGEIFS({d_rng_gap}, {d_rng_sid}, A{idx})")
        ws.cell(idx, 10, f"=SUMIFS({d_rng_rev}, {d_rng_sid}, A{idx})")
        ws.cell(idx, 11, f"=COUNTIFS({s_rng_sid}, A{idx}, {s_rng_peak}, 1)")
        ws.cell(idx, 12, f"=K{idx}*0.25")

    ws.cell(6, 1, "Итого")
    ws.cell(6, 2, "Оба магазина")
    ws.cell(6, 3, "=SUM(C4:C5)")
    ws.cell(6, 4, "=SUM(D4:D5)")
    ws.cell(6, 5, "=IF(C6>0, D6/C6, 0)")
    ws.cell(6, 6, "=SUM(F4:F5)")
    ws.cell(6, 7, "=IF(C6>0, F6/C6, 0)")
    ws.cell(6, 8, f"=AVERAGE({d_rng_dur})")
    ws.cell(6, 9, f"=AVERAGE({d_rng_gap})")
    ws.cell(6, 10, "=SUM(J4:J5)")
    ws.cell(6, 11, "=SUM(K4:K5)")
    ws.cell(6, 12, "=SUM(L4:L5)")

    for r in (4, 5, 6):
        for c in range(1, 13):
            cell = ws.cell(r, c)
            cell.border = THIN_BORDER
            cell.font = BOLD_FONT if r == 6 else BASE_FONT
            if r == 6:
                cell.fill = SUB_FILL
            if c in (3, 4, 6, 10, 11):
                cell.number_format = "#,##0"
            elif c in (5, 7):
                cell.number_format = "0.0%"
            elif c in (8, 9, 12):
                cell.number_format = "0.0"

    ws["A9"] = "Разрез по типу касс (обычные кассы 6-8 и КСО 16-18)"
    ws["A9"].font = BOLD_FONT
    z_headers = ["store_id", "Тип кассы", "Всего чеков", "Чеков в очередях", "Доля очередей", "Ср. обсл., сек"]
    for c, h in enumerate(z_headers, start=1):
        ws.cell(10, c, h)
    _style_header(ws, 10, len(z_headers))

    rows_z = [(12864064, "Касса"), (12864064, "КСО"), (98451680, "Касса"), (98451680, "КСО")]
    for idx, (sid, z) in enumerate(rows_z, start=11):
        ws.cell(idx, 1, sid)
        ws.cell(idx, 2, z)
        ws.cell(idx, 3, f"=COUNTIFS({d_rng_sid}, A{idx}, {d_rng_zone}, B{idx})")
        ws.cell(idx, 4, f"=COUNTIFS({d_rng_sid}, A{idx}, {d_rng_zone}, B{idx}, {d_rng_q}, 1)")
        ws.cell(idx, 5, f"=IF(C{idx}>0, D{idx}/C{idx}, 0)")
        ws.cell(idx, 6, f"=AVERAGEIFS({d_rng_dur}, {d_rng_sid}, A{idx}, {d_rng_zone}, B{idx})")
        for c in range(1, 7):
            cell = ws.cell(idx, c)
            cell.border = THIN_BORDER
            cell.font = BASE_FONT
            if c in (3, 4):
                cell.number_format = "#,##0"
            elif c == 5:
                cell.number_format = "0.0%"
            elif c == 6:
                cell.number_format = "0.0"

    widths = [14, 24, 14, 15, 13, 18, 15, 14, 24, 18, 20, 20]
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _build_hourly_sheet(ws, last_data_row: int) -> None:
    ws["A1"] = "Почасовой профиль нагрузки и очередей (формулы COUNTIFS)"
    ws["A1"].font = TITLE_FONT

    headers = [
        "Час",
        "Чеки 12864064", "В очереди 12864064", "Доля оч. 12864064",
        "Чеки 98451680", "В очереди 98451680", "Доля оч. 98451680",
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(3, c, h)
    _style_header(ws, 3, len(headers))

    d_rng_sid = f"Данные_и_расчет!$B$2:$B${last_data_row}"
    d_rng_hr = f"Данные_и_расчет!$Q$2:$Q${last_data_row}"
    d_rng_q = f"Данные_и_расчет!$O$2:$O${last_data_row}"

    for hr in range(24):
        r = 4 + hr
        ws.cell(r, 1, hr)
        ws.cell(r, 2, f"=COUNTIFS({d_rng_sid}, 12864064, {d_rng_hr}, A{r})")
        ws.cell(r, 3, f"=COUNTIFS({d_rng_sid}, 12864064, {d_rng_hr}, A{r}, {d_rng_q}, 1)")
        ws.cell(r, 4, f"=IF(B{r}>0, C{r}/B{r}, 0)")
        ws.cell(r, 5, f"=COUNTIFS({d_rng_sid}, 98451680, {d_rng_hr}, A{r})")
        ws.cell(r, 6, f"=COUNTIFS({d_rng_sid}, 98451680, {d_rng_hr}, A{r}, {d_rng_q}, 1)")
        ws.cell(r, 7, f"=IF(E{r}>0, F{r}/E{r}, 0)")
        for c in range(1, 8):
            cell = ws.cell(r, c)
            cell.border = THIN_BORDER
            cell.font = BASE_FONT
            if c in (2, 3, 5, 6):
                cell.number_format = "#,##0"
            elif c in (4, 7):
                cell.number_format = "0.0%"

    ws.cell(28, 1, "Итого")
    for c in (2, 3, 5, 6):
        col_let = get_column_letter(c)
        ws.cell(28, c, f"=SUM({col_let}4:{col_let}27)")
    ws.cell(28, 4, "=IF(B28>0, C28/B28, 0)")
    ws.cell(28, 7, "=IF(E28>0, F28/E28, 0)")
    for c in range(1, 8):
        cell = ws.cell(28, c)
        cell.border = THIN_BORDER
        cell.font = BOLD_FONT
        cell.fill = SUB_FILL
        if c in (2, 3, 5, 6):
            cell.number_format = "#,##0"
        elif c in (4, 7):
            cell.number_format = "0.0%"

    chart = LineChart()
    chart.title = "Доля чеков в очередях по часам суток"
    chart.y_axis.title = "Доля чеков в очереди"
    chart.x_axis.title = "Час суток"
    chart.y_axis.number_format = "0%"
    chart.width = 18
    chart.height = 10

    data_ref1 = Reference(ws, min_col=4, min_row=3, max_row=27)
    data_ref2 = Reference(ws, min_col=7, min_row=3, max_row=27)
    cats = Reference(ws, min_col=1, min_row=4, max_row=27)
    chart.add_data(data_ref1, titles_from_data=True)
    chart.add_data(data_ref2, titles_from_data=True)
    chart.set_categories(cats)
    ws.add_chart(chart, "I3")

    for c, w in enumerate([10, 16, 18, 16, 16, 18, 16], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _build_episodes_sheet(ws, episodes_df: pd.DataFrame) -> None:
    headers = [
        "store_id", "checkout_id", "Тип кассы", "Чеков в очереди",
        "Начало очереди", "Конец очереди", "Длительность, мин",
        "Товаров, шт", "Сумма, руб", "Ср. время на чек, сек"
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h)
    _style_header(ws, 1, len(headers))

    for idx, row in enumerate(episodes_df.itertuples(index=False), start=2):
        ws.cell(idx, 1, int(row.store_id))
        ws.cell(idx, 2, int(row.checkout_id))
        ws.cell(idx, 3, f'=IF(B{idx}>=16,"КСО","Касса")')
        ws.cell(idx, 4, int(row.checks_in_queue))
        c_s = ws.cell(idx, 5, row.queue_start.to_pydatetime())
        c_e = ws.cell(idx, 6, row.queue_end.to_pydatetime())
        c_s.number_format = "dd.mm.yyyy hh:mm:ss"
        c_e.number_format = "dd.mm.yyyy hh:mm:ss"
        c_dur = ws.cell(idx, 7, f"=ROUND((F{idx}-E{idx})*1440, 2)")
        c_dur.number_format = "0.00"
        ws.cell(idx, 8, int(row.total_items)).number_format = "#,##0"
        ws.cell(idx, 9, int(row.total_revenue)).number_format = "#,##0"
        c_avg = ws.cell(idx, 10, f"=ROUND((F{idx}-E{idx})*86400/D{idx}, 1)")
        c_avg.number_format = "0.0"

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{len(episodes_df) + 1}"
    for c, w in enumerate([12, 12, 12, 16, 20, 20, 18, 14, 14, 20], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _build_slots_sheet(ws, slots_df: pd.DataFrame, last_data_row: int) -> None:
    headers = [
        "store_id", "Слот_15мин", "Ключ_слота", "Чеков_всего", "Чеков_в_очереди",
        "Доля_очереди", "Чеков_на_КСО", "Время_обсл_сек",
        "Занятых_касс_экв", "Пик_очереди_флаг", "Начало_периода_очереди", "Статус"
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h)
    _style_header(ws, 1, len(headers))

    d_sid = f"Данные_и_расчет!$B$2:$B${last_data_row}"
    d_slot = f"Данные_и_расчет!$P$2:$P${last_data_row}"
    d_q = f"Данные_и_расчет!$O$2:$O${last_data_row}"
    d_zone = f"Данные_и_расчет!$J$2:$J${last_data_row}"
    d_dur = f"Данные_и_расчет!$I$2:$I${last_data_row}"

    for idx, row in enumerate(slots_df.itertuples(index=False), start=2):
        ws.cell(idx, 1, int(row.store_id))
        c_dt = ws.cell(idx, 2, row.slot_15m.to_pydatetime())
        c_dt.number_format = "dd.mm.yyyy hh:mm"
        ws.cell(idx, 3, f"=INT((B{idx}+1E-9)*96)")
        ws.cell(idx, 4, f"=COUNTIFS({d_sid}, A{idx}, {d_slot}, C{idx})").number_format = "#,##0"
        ws.cell(idx, 5, f"=COUNTIFS({d_sid}, A{idx}, {d_slot}, C{idx}, {d_q}, 1)").number_format = "#,##0"
        ws.cell(idx, 6, f"=IF(D{idx}>0, E{idx}/D{idx}, 0)").number_format = "0.0%"
        ws.cell(idx, 7, f'=COUNTIFS({d_sid}, A{idx}, {d_slot}, C{idx}, {d_zone}, "КСО")').number_format = "#,##0"
        ws.cell(idx, 8, f"=SUMIFS({d_dur}, {d_sid}, A{idx}, {d_slot}, C{idx})").number_format = "#,##0"
        ws.cell(idx, 9, f"=ROUND(H{idx}/900, 2)").number_format = "0.00"
        ws.cell(idx, 10, f"=IF(E{idx}>=Описание_и_логика!$C$7, 1, 0)")
        if idx == 2:
            c_per = ws.cell(idx, 11, f'=IF(J{idx}=1, B{idx}, "")')
        else:
            c_per = ws.cell(
                idx,
                11,
                f'=IF(J{idx}=1, IF(AND(A{idx}=A{idx-1}, J{idx-1}=1, C{idx}-C{idx-1}=1), K{idx-1}, B{idx}), "")',
            )
        c_per.number_format = "dd.mm.yyyy hh:mm"
        ws.cell(idx, 12, f'=IF(J{idx}=1, "Пиковая очередь", IF(E{idx}>=3, "Локальная очередь", "Свободно"))')

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:L{len(slots_df) + 1}"
    for c, w in enumerate([12, 18, 12, 14, 16, 14, 14, 16, 18, 17, 22, 19], start=1):
        ws.column_dimensions[get_column_letter(c)].width = w


def _build_data_sheet(ws, df_sorted: pd.DataFrame, last_data_row: int) -> None:
    headers = [
        "checks_number", "store_id", "employees_id", "quantity",
        "selling_price", "checkout_id", "start_operation_dt", "end_operation_dt",
        "Длительность_сек", "Тип_кассы", "Пауза_сек", "Быстрая_смена",
        "Позиция_в_цепочке", "Длина_цепочки", "Очередь_флаг", "Слот_15мин_ключ", "Час"
    ]
    for c, h in enumerate(headers, start=1):
        ws.cell(1, c, h)
    _style_header(ws, 1, len(headers))

    for idx, row in enumerate(df_sorted.itertuples(index=False), start=2):
        ws.cell(idx, 1, int(row.checks_number))
        ws.cell(idx, 2, int(row.store_id))
        ws.cell(idx, 3, int(row.employees_id))
        ws.cell(idx, 4, int(row.quantity))
        ws.cell(idx, 5, int(row.selling_price))
        ws.cell(idx, 6, int(row.checkout_id))

        c_st = ws.cell(idx, 7, row.start_dt.to_pydatetime())
        c_en = ws.cell(idx, 8, row.end_dt.to_pydatetime())
        c_st.number_format = "dd.mm.yyyy hh:mm:ss"
        c_en.number_format = "dd.mm.yyyy hh:mm:ss"

        ws.cell(idx, 9, f"=ROUND((H{idx}-G{idx})*86400, 0)")
        ws.cell(idx, 10, f'=IF(F{idx}>=16, "КСО", "Касса")')

        if idx == 2:
            ws.cell(idx, 11, "")
            ws.cell(idx, 12, 0)
            ws.cell(idx, 13, 1)
        else:
            ws.cell(idx, 11, f'=IF(AND(B{idx}=B{idx-1}, F{idx}=F{idx-1}), ROUND((G{idx}-H{idx-1})*86400, 0), "")')
            ws.cell(idx, 12, f"=IF(AND(ISNUMBER(K{idx}), INT(G{idx})=INT(H{idx-1}), K{idx}<=Описание_и_логика!$C$5), 1, 0)")
            ws.cell(idx, 13, f"=IF(L{idx}=1, M{idx-1}+1, 1)")

        if idx < last_data_row:
            ws.cell(idx, 14, f"=IF(L{idx+1}=1, N{idx+1}, M{idx})")
        else:
            ws.cell(idx, 14, f"=M{idx}")

        ws.cell(idx, 15, f"=IF(N{idx}>=Описание_и_логика!$C$6, 1, 0)")
        ws.cell(idx, 16, f"=INT((G{idx}+1E-9)*96)")
        ws.cell(idx, 17, f"=HOUR(G{idx})")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:Q{last_data_row}"
    widths = [14, 12, 13, 10, 14, 12, 20, 20, 17, 11, 12, 14, 18, 15, 13, 16, 8]
    for c, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(c)].width = w
