import html
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd


class QuantityBucketMatrixSheet(ttk.Frame):
    """
    Quantity Bucket x Counterparty analytics matrix.

    Rows:
      - manual buckets of abs(quantity)

    Dynamic display:
      - Premia
      - fees
      - optional normalization by number of trades

    Stable columns on the right:
      - ALL Selected
      - ALL Premia
      - ALL fees
      - ALL Trades
    """

    sheet_id = "quantity_bucket_matrix"
    title = "Quantity Bucket Matrix"
    sheet_title = "Quantity Bucket Matrix"
    nav_title = "Quantity Bucket Matrix"

    COUNTERPARTY_COL = "counterparty"
    QUANTITY_COL = "quantity"
    PREMIA_COL = "Premia"
    FEES_COL = "fees"

    BUCKET_COL = "Quantity Bucket"

    TOTAL_COL = "ALL Selected"
    TOTAL_PREMIA_COL = "ALL Premia"
    TOTAL_FEES_COL = "ALL fees"
    TOTAL_TRADES_COL = "ALL Trades"
    GRAND_TOTAL_LABEL = "ALL"

    EXPORT_BUTTON_BG = "#d8b4fe"   # lilac
    EXPORT_BUTTON_FG = "#1f102f"
    SELECTED_LILAC = "#eadcff"

    POSITIVE_TAG = "positive_row"
    NEGATIVE_TAG = "negative_row"
    NEUTRAL_TAG = "neutral_row"
    GRAND_TOTAL_TAG = "grand_total_row"

    # ------------------------------------------------------------
    # MANUAL BUCKETS: edit these later in production as you wish
    # Format: (label, low_inclusive, high_exclusive)
    # Use None for open end.
    # ------------------------------------------------------------
    QUANTITY_BUCKETS = [
        ("< 50", None, 50),
        ("50 - 100", 50, 100),
        ("100 - 250", 100, 250),
        ("250 - 500", 250, 500),
        (">= 500", 500, None),
    ]

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self._raw_df = pd.DataFrame()
        self._table_df = pd.DataFrame()
        self._bucket_df = pd.DataFrame()
        self._row_totals_df = pd.DataFrame()
        self._sort_state = {}

        self._show_premia = tk.BooleanVar(value=True)
        self._show_fees = tk.BooleanVar(value=False)
        self._normalize_by_trades = tk.BooleanVar(value=False)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        controls = ttk.Frame(self)
        controls.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
        controls.grid_columnconfigure(99, weight=1)

        ttk.Label(controls, text="Display:").grid(row=0, column=0, sticky="w", padx=(0, 8))

        ttk.Checkbutton(
            controls,
            text="Premia",
            variable=self._show_premia,
            command=self._rebuild_from_cache,
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))

        ttk.Checkbutton(
            controls,
            text="fees",
            variable=self._show_fees,
            command=self._rebuild_from_cache,
        ).grid(row=0, column=2, sticky="w", padx=(0, 16))

        ttk.Checkbutton(
            controls,
            text="Normalize / trades",
            variable=self._normalize_by_trades,
            command=self._rebuild_from_cache,
        ).grid(row=0, column=3, sticky="w", padx=(0, 16))

        ttk.Button(
            controls,
            text="Refresh",
            command=lambda: self._rebuild_from_cache(default_sort=False),
        ).grid(row=0, column=4, sticky="w", padx=(0, 10))

        export_btn = tk.Button(
            controls,
            text="Export HTML",
            bg=self.EXPORT_BUTTON_BG,
            fg=self.EXPORT_BUTTON_FG,
            activebackground=self.EXPORT_BUTTON_BG,
            activeforeground=self.EXPORT_BUTTON_FG,
            relief="flat",
            padx=12,
            pady=4,
            command=self._export_html,
        )
        export_btn.grid(row=0, column=5, sticky="w", padx=(0, 12))

        self._info_label = ttk.Label(controls, text="")
        self._info_label.grid(row=0, column=99, sticky="e")

        container = ttk.Frame(self)
        container.grid(row=1, column=0, sticky="nsew")
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(container, show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")

        hsb = ttk.Scrollbar(container, orient="horizontal", command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        style = ttk.Style()
        try:
            style.configure("Treeview.Heading", font=("Arial", 10, "bold"))
            style.configure("Treeview", rowheight=24)
            style.map(
                "Treeview",
                background=[("selected", self.SELECTED_LILAC)],
                foreground=[("selected", "black")],
            )
        except Exception:
            pass

        self.tree.tag_configure(self.POSITIVE_TAG, background="#eaf7ea")
        self.tree.tag_configure(self.NEGATIVE_TAG, background="#fdeaea")
        self.tree.tag_configure(self.NEUTRAL_TAG, background="#f6f6f6")
        self.tree.tag_configure(self.GRAND_TOTAL_TAG, background="#e8eefc")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def on_df_loaded(self, df: pd.DataFrame):
        self.update_data(df)

    def update_data(self, df: pd.DataFrame):
        self._raw_df = df.copy()
        self._build_caches(df)
        self._rebuild_from_cache(default_sort=True)

    def clear(self):
        self._raw_df = pd.DataFrame()
        self._bucket_df = pd.DataFrame()
        self._row_totals_df = pd.DataFrame()
        self._table_df = pd.DataFrame()
        self._sort_state = {}
        self._info_label.configure(text="")
        self._clear_tree()

    # ------------------------------------------------------------------
    # Bucket logic
    # ------------------------------------------------------------------
    @classmethod
    def _assign_quantity_bucket(cls, q):
        try:
            q_abs = abs(float(q))
        except Exception:
            return "UNKNOWN"

        for label, low, high in cls.QUANTITY_BUCKETS:
            if low is None and high is not None and q_abs < high:
                return label
            if high is None and low is not None and q_abs >= low:
                return label
            if low is not None and high is not None and low <= q_abs < high:
                return label

        return "UNKNOWN"

    @classmethod
    def _bucket_order_map(cls):
        order = {label: i for i, (label, _, _) in enumerate(cls.QUANTITY_BUCKETS)}
        order["UNKNOWN"] = len(order)
        order[cls.GRAND_TOTAL_LABEL] = len(order) + 1
        return order

    # ------------------------------------------------------------------
    # Data prep / cache
    # ------------------------------------------------------------------
    def _build_caches(self, df: pd.DataFrame):
        required = [
            self.COUNTERPARTY_COL,
            self.QUANTITY_COL,
            self.PREMIA_COL,
            self.FEES_COL,
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise KeyError(f"Missing columns for QuantityBucketMatrixSheet: {missing}")

        work = df[required].copy()

        work[self.COUNTERPARTY_COL] = (
            work[self.COUNTERPARTY_COL].fillna("UNKNOWN").astype(str).str.strip()
        )
        work.loc[work[self.COUNTERPARTY_COL] == "", self.COUNTERPARTY_COL] = "UNKNOWN"

        work[self.QUANTITY_COL] = pd.to_numeric(work[self.QUANTITY_COL], errors="coerce").fillna(0.0)
        work[self.PREMIA_COL] = pd.to_numeric(work[self.PREMIA_COL], errors="coerce").fillna(0.0)
        work[self.FEES_COL] = pd.to_numeric(work[self.FEES_COL], errors="coerce").fillna(0.0)

        work[self.BUCKET_COL] = work[self.QUANTITY_COL].map(self._assign_quantity_bucket)
        work["trade_count"] = 1.0

        self._bucket_df = (
            work.groupby(
                [self.BUCKET_COL, self.COUNTERPARTY_COL],
                observed=True,
                sort=False,
            )
            .agg(
                Premia_sum=(self.PREMIA_COL, "sum"),
                fees_sum=(self.FEES_COL, "sum"),
                trade_count=("trade_count", "sum"),
            )
            .reset_index()
        )

        self._row_totals_df = (
            work.groupby(self.BUCKET_COL, observed=True, sort=False)
            .agg(
                **{
                    self.TOTAL_PREMIA_COL: (self.PREMIA_COL, "sum"),
                    self.TOTAL_FEES_COL: (self.FEES_COL, "sum"),
                    self.TOTAL_TRADES_COL: ("trade_count", "sum"),
                }
            )
            .reset_index()
        )

    # ------------------------------------------------------------------
    # Build displayed table from cache
    # ------------------------------------------------------------------
    def _selected_metric_name(self) -> str:
        parts = []
        if self._show_premia.get():
            parts.append("Premia")
        if self._show_fees.get():
            parts.append("fees")
        if not parts:
            parts.append("None")

        label = " + ".join(parts)
        if self._normalize_by_trades.get():
            label += " / trades"
        return label

    def _rebuild_from_cache(self, default_sort: bool = False):
        if self._bucket_df.empty:
            self._table_df = pd.DataFrame()
            self._info_label.configure(text="No data")
            self._clear_tree()
            return

        bucket = self._bucket_df.copy()
        bucket["selected_sum"] = 0.0

        if self._show_premia.get():
            bucket["selected_sum"] += bucket["Premia_sum"]
        if self._show_fees.get():
            bucket["selected_sum"] += bucket["fees_sum"]

        if self._normalize_by_trades.get():
            denom = bucket["trade_count"].where(bucket["trade_count"] != 0, 1.0)
            bucket["selected_value"] = bucket["selected_sum"] / denom
        else:
            bucket["selected_value"] = bucket["selected_sum"]

        pivot = bucket.pivot(
            index=self.BUCKET_COL,
            columns=self.COUNTERPARTY_COL,
            values="selected_value",
        ).fillna(0.0)

        # keep manual bucket order
        order_map = self._bucket_order_map()
        pivot = pivot.reindex(
            sorted(pivot.index, key=lambda x: order_map.get(x, 10_000))
        )
        pivot = pivot.sort_index(axis=1)

        row_selected_sum = (
            bucket.groupby(self.BUCKET_COL, observed=True, sort=False)["selected_sum"].sum()
        )
        row_trade_sum = (
            bucket.groupby(self.BUCKET_COL, observed=True, sort=False)["trade_count"].sum()
        )

        if self._normalize_by_trades.get():
            selected_all = row_selected_sum / row_trade_sum.where(row_trade_sum != 0, 1.0)
        else:
            selected_all = row_selected_sum

        pivot[self.TOTAL_COL] = selected_all.reindex(pivot.index).fillna(0.0)

        result = pivot.reset_index()
        result = result.merge(self._row_totals_df, on=self.BUCKET_COL, how="left")

        info_cols = [
            self.TOTAL_COL,
            self.TOTAL_PREMIA_COL,
            self.TOTAL_FEES_COL,
            self.TOTAL_TRADES_COL,
        ]
        cp_cols = [c for c in result.columns if c not in [self.BUCKET_COL] + info_cols]

        result = result[[self.BUCKET_COL] + cp_cols + info_cols]

        total_row = {self.BUCKET_COL: self.GRAND_TOTAL_LABEL}
        for col in cp_cols:
            total_row[col] = float(result[col].sum()) if col in result.columns else 0.0
        total_row[self.TOTAL_COL] = float(result[self.TOTAL_COL].sum()) if self.TOTAL_COL in result.columns else 0.0
        total_row[self.TOTAL_PREMIA_COL] = float(self._row_totals_df[self.TOTAL_PREMIA_COL].sum())
        total_row[self.TOTAL_FEES_COL] = float(self._row_totals_df[self.TOTAL_FEES_COL].sum())
        total_row[self.TOTAL_TRADES_COL] = float(self._row_totals_df[self.TOTAL_TRADES_COL].sum())

        result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

        if default_sort and self.TOTAL_COL in result.columns:
            all_mask = result[self.BUCKET_COL].astype(str) == self.GRAND_TOTAL_LABEL
            df_main = result.loc[~all_mask].copy()
            df_all = result.loc[all_mask].copy()
            df_main = df_main.sort_values(by=self.TOTAL_COL, ascending=False, kind="mergesort")
            result = pd.concat([df_main, df_all], ignore_index=True)
            self._sort_state[self.TOTAL_COL] = True

        bucket_count = max(len(result) - 1, 0)
        cp_count = len(cp_cols)
        self._table_df = result
        self._info_label.configure(
            text=f"Buckets: {bucket_count} | Counterparties: {cp_count} | Metric: {self._selected_metric_name()}"
        )
        self._render_table(result)

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def _render_table(self, df: pd.DataFrame):
        self._clear_tree()
        if df.empty:
            return

        columns = list(df.columns)
        self.tree["columns"] = columns

        info_cols = {
            self.TOTAL_COL,
            self.TOTAL_PREMIA_COL,
            self.TOTAL_FEES_COL,
            self.TOTAL_TRADES_COL,
        }

        for col in columns:
            if col == self.BUCKET_COL:
                anchor = "w"
                width = 170
            elif col in info_cols:
                anchor = "e"
                width = 130 if col != self.TOTAL_TRADES_COL else 105
            else:
                anchor = "e"
                width = 105

            self.tree.heading(col, text=col, command=lambda c=col: self._sort_by_column(c))
            self.tree.column(col, width=width, minwidth=80, stretch=False, anchor=anchor)

        for row in df.itertuples(index=False, name=None):
            row_map = dict(zip(columns, row))
            values = [self._format_cell(col, val) for col, val in zip(columns, row)]
            tag = self._row_tag(row_map)
            self.tree.insert("", "end", values=values, tags=(tag,))

    def _row_tag(self, row_map):
        name = str(row_map.get(self.BUCKET_COL, ""))
        if name == self.GRAND_TOTAL_LABEL:
            return self.GRAND_TOTAL_TAG

        val = row_map.get(self.TOTAL_COL, 0.0)
        try:
            num = float(val)
        except Exception:
            num = 0.0

        if num > 0:
            return self.POSITIVE_TAG
        if num < 0:
            return self.NEGATIVE_TAG
        return self.NEUTRAL_TAG

    def _clear_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = ()

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------
    def _sort_by_column(self, col: str):
        if self._table_df.empty or col not in self._table_df.columns:
            return

        ascending = self._sort_state.get(col, True)
        df = self._table_df.copy()

        all_mask = df[self.BUCKET_COL].astype(str) == self.GRAND_TOTAL_LABEL
        df_main = df.loc[~all_mask].copy()
        df_all = df.loc[all_mask].copy()

        if col == self.BUCKET_COL:
            order_map = self._bucket_order_map()
            df_main["_sort_key"] = df_main[col].map(lambda x: order_map.get(x, 10_000))
            df_main = df_main.sort_values(
                by="_sort_key",
                ascending=ascending,
                kind="mergesort",
            ).drop(columns="_sort_key")
        else:
            df_main = df_main.sort_values(
                by=col,
                ascending=ascending,
                kind="mergesort",
            )

        df_sorted = pd.concat([df_main, df_all], ignore_index=True)
        self._sort_state[col] = not ascending
        self._table_df = df_sorted
        self._render_table(df_sorted)

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------
    def _format_cell(self, col_name, value):
        if col_name == self.BUCKET_COL:
            return "" if pd.isna(value) else str(value)

        if pd.isna(value):
            return "0"

        if col_name == self.TOTAL_TRADES_COL:
            try:
                return f"{int(round(float(value))):,}"
            except Exception:
                return str(value)

        try:
            num = float(value)
            return f"{num:,.2f}"
        except Exception:
            return str(value)

    # ------------------------------------------------------------------
    # HTML export
    # ------------------------------------------------------------------
    @staticmethod
    def _cell_bg_for_html(val):
        try:
            x = float(str(val).replace(",", ""))
        except Exception:
            return "white"

        if x > 0:
            return "#dff3df"
        if x < 0:
            return "#f8dede"
        return "white"

    def _export_html(self):
        if self._table_df.empty:
            messagebox.showinfo("Export HTML", "No data to export.")
            return

        path = filedialog.asksaveasfilename(
            title="Save HTML report",
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            initialfile="quantity_bucket_matrix.html",
        )
        if not path:
            return

        try:
            html_text = self._build_html_document()
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_text)

            self.clipboard_clear()
            self.clipboard_append(path)
            self.update()

            messagebox.showinfo(
                "Export HTML",
                f"HTML saved successfully.\n\nPath copied to clipboard:\n{path}"
            )
        except Exception as e:
            messagebox.showerror("Export HTML failed", f"{type(e).__name__}: {e}")

    def _build_html_document(self):
        df = self._table_df.copy()
        columns = list(df.columns)

        first_col = self.BUCKET_COL
        sticky_bottom_label = self.GRAND_TOTAL_LABEL

        head_html = []
        for col in columns:
            head_html.append(f"<th>{html.escape(str(col))}</th>")

        body_html = []
        for _, row in df.iterrows():
            is_total = str(row[first_col]) == sticky_bottom_label
            tr_class = "grand-total-row" if is_total else ""

            tds = []
            for col in columns:
                raw_val = row[col]
                display_val = self._format_cell(col, raw_val)

                if col == first_col:
                    td_class = "sticky-first label-cell"
                    style = ""
                else:
                    td_class = "numeric-cell"
                    bg = self._cell_bg_for_html(display_val)
                    style = f' style="background:{bg};"'

                tds.append(
                    f'<td class="{td_class}"{style}>{html.escape(str(display_val))}</td>'
                )

            body_html.append(f'<tr class="{tr_class}">{"".join(tds)}</tr>')

        metric_label = html.escape(self._selected_metric_name())

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quantity Bucket Matrix</title>
<style>
    :root {{
        --bg: #f5f7fb;
        --card: #ffffff;
        --text: #1f2937;
        --muted: #6b7280;
        --border: #d8deea;
        --header: #eef2ff;
        --sticky: #f8fafc;
        --grand: #dbe7ff;
        --lilac: #b58cff;
    }}

    body {{
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font-family: Arial, Helvetica, sans-serif;
    }}

    .page {{
        padding: 20px;
    }}

    .card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 16px;
        box-shadow: 0 8px 24px rgba(31, 41, 55, 0.08);
        overflow: hidden;
    }}

    .topbar {{
        padding: 16px 18px 10px 18px;
        border-bottom: 1px solid var(--border);
        background: linear-gradient(to right, #faf5ff, #ffffff);
    }}

    .title {{
        font-size: 22px;
        font-weight: 700;
        margin: 0 0 6px 0;
    }}

    .subtitle {{
        font-size: 13px;
        color: var(--muted);
        margin: 0;
    }}

    .table-wrap {{
        height: calc(100vh - 150px);
        overflow: auto;
    }}

    table {{
        border-collapse: separate;
        border-spacing: 0;
        min-width: 100%;
        width: max-content;
        font-size: 13px;
    }}

    thead th {{
        position: sticky;
        top: 0;
        z-index: 5;
        background: var(--header);
        cursor: pointer;
        user-select: none;
    }}

    th, td {{
        border-right: 1px solid var(--border);
        border-bottom: 1px solid var(--border);
        padding: 8px 10px;
        white-space: nowrap;
    }}

    th:first-child, td:first-child {{
        border-left: 1px solid var(--border);
    }}

    thead tr:first-child th {{
        border-top: 1px solid var(--border);
    }}

    .sticky-first {{
        position: sticky;
        left: 0;
        z-index: 4;
        background: var(--sticky);
    }}

    thead .sticky-first {{
        z-index: 6;
        background: var(--header);
    }}

    .label-cell {{
        font-weight: 600;
    }}

    .numeric-cell {{
        text-align: right;
    }}

    tbody tr:hover td {{
        filter: brightness(0.985);
    }}

    tbody tr.selected-row td {{
        box-shadow: inset 0 0 0 2px var(--lilac);
    }}

    tbody tr.grand-total-row td {{
        position: sticky;
        bottom: 0;
        z-index: 3;
        font-weight: 700;
    }}

    tbody tr.grand-total-row td.sticky-first {{
        z-index: 4;
    }}
</style>
</head>
<body>
<div class="page">
    <div class="card">
        <div class="topbar">
            <h1 class="title">Quantity Bucket Matrix</h1>
            <p class="subtitle">Metric: {metric_label}</p>
        </div>

        <div class="table-wrap">
            <table id="matrixTable">
                <thead>
                    <tr>
                        {''.join(
                            f'<th class="sticky-first">{html.escape(str(c))}</th>' if i == 0
                            else f'<th>{html.escape(str(c))}</th>'
                            for i, c in enumerate(columns)
                        )}
                    </tr>
                </thead>
                <tbody>
                    {''.join(body_html)}
                </tbody>
            </table>
        </div>
    </div>
</div>

<script>
function parseCellValue(text) {{
    const normalized = String(text).replace(/,/g, "").trim();
    const n = Number(normalized);
    if (!Number.isNaN(n)) return n;
    return text.toLowerCase();
}}

function sortTableByColumn(table, columnIndex, ascending) {{
    const tbody = table.querySelector("tbody");
    const rows = Array.from(tbody.querySelectorAll("tr:not(.grand-total-row)"));

    rows.sort((a, b) => {{
        const aText = a.children[columnIndex].innerText;
        const bText = b.children[columnIndex].innerText;

        const aVal = parseCellValue(aText);
        const bVal = parseCellValue(bText);

        if (typeof aVal === "number" && typeof bVal === "number") {{
            return ascending ? aVal - bVal : bVal - aVal;
        }}

        return ascending
            ? String(aVal).localeCompare(String(bVal))
            : String(bVal).localeCompare(String(aVal));
    }});

    rows.forEach(row => tbody.appendChild(row));

    const totalRow = tbody.querySelector("tr.grand-total-row");
    if (totalRow) tbody.appendChild(totalRow);

    enableRowSelection();
}}

function makeTableSortable() {{
    const table = document.getElementById("matrixTable");
    const headers = table.querySelectorAll("thead th");

    headers.forEach((header, index) => {{
        let ascending = true;
        header.addEventListener("click", () => {{
            sortTableByColumn(table, index, ascending);
            ascending = !ascending;
        }});
    }});
}}

function enableRowSelection() {{
    const tbodyRows = document.querySelectorAll("tbody tr");

    tbodyRows.forEach(row => {{
        row.onclick = () => {{
            tbodyRows.forEach(r => r.classList.remove("selected-row"));
            row.classList.add("selected-row");
        }};
    }});
}}

makeTableSortable();
enableRowSelection();
</script>
</body>
</html>
"""
