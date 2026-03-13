import html
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd


class PremiaMatrixSheet(ttk.Frame):
    """
    Underlying x Counterparty analytics matrix.

    Dynamic matrix display:
      - Premia
      - fees
      - optional normalization by number of trades

    Stable informative columns on the right (independent of current selection):
      - ALL Selected
      - ALL Premia
      - ALL fees
      - ALL PnLVonDelta
      - ALL Trades
    """

    sheet_id = "premia_matrix"
    title = "Premia Matrix"
    sheet_title = "Premia Matrix"
    nav_title = "Premia Matrix"

    UNDERLYING_COL = "underlyingName"
    COUNTERPARTY_COL = "counterparty"
    PREMIA_COL = "Premia"
    FEES_COL = "fees"
    PNL_DELTA_COL = "PnLVonDelta"

    TOTAL_COL = "ALL Selected"
    TOTAL_PREMIA_COL = "ALL Premia"
    TOTAL_FEES_COL = "ALL fees"
    TOTAL_PNL_DELTA_COL = "ALL PnLVonDelta"
    TOTAL_TRADES_COL = "ALL Trades"
    GRAND_TOTAL_LABEL = "ALL"

    LILAC = "#b58cff"
    LILAC_LIGHT = "#efe4ff"
    LILAC_BUTTON = "#b58cff"
    LILAC_BUTTON_ACTIVE = "#a16fff"

    POSITIVE_TAG = "positive_row"
    NEGATIVE_TAG = "negative_row"
    NEUTRAL_TAG = "neutral_row"
    GRAND_TOTAL_TAG = "grand_total_row"

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self._raw_df = pd.DataFrame()
        self._table_df = pd.DataFrame()
        self._bucket_df = pd.DataFrame()
        self._underlying_totals_df = pd.DataFrame()
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
        ).grid(row=0, column=4, sticky="w", padx=(0, 8))

        self._export_btn = tk.Button(
            controls,
            text="Export HTML",
            bg=self.LILAC_BUTTON,
            activebackground=self.LILAC_BUTTON_ACTIVE,
            fg="white",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=12,
            pady=4,
            cursor="hand2",
            command=self._export_html,
        )
        self._export_btn.grid(row=0, column=5, sticky="w", padx=(0, 12))

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
                background=[("selected", self.LILAC_LIGHT)],
                foreground=[("selected", "black")],
            )
        except Exception:
            pass

        self.tree.tag_configure(self.POSITIVE_TAG, background="#eaf7ea")
        self.tree.tag_configure(self.NEGATIVE_TAG, background="#fdeaea")
        self.tree.tag_configure(self.NEUTRAL_TAG, background="#f8f8f8")
        self.tree.tag_configure(self.GRAND_TOTAL_TAG, background="#eef1fb")

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
        self._underlying_totals_df = pd.DataFrame()
        self._table_df = pd.DataFrame()
        self._sort_state = {}
        self._info_label.configure(text="")
        self._clear_tree()

    # ------------------------------------------------------------------
    # Data prep / cache
    # ------------------------------------------------------------------
    def _build_caches(self, df: pd.DataFrame):
        required = [
            self.UNDERLYING_COL,
            self.COUNTERPARTY_COL,
            self.PREMIA_COL,
            self.FEES_COL,
            self.PNL_DELTA_COL,
        ]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise KeyError(f"Missing columns for PremiaMatrixSheet: {missing}")

        work = df[required].copy()

        work[self.UNDERLYING_COL] = (
            work[self.UNDERLYING_COL].fillna("UNKNOWN").astype(str).str.strip()
        )
        work[self.COUNTERPARTY_COL] = (
            work[self.COUNTERPARTY_COL].fillna("UNKNOWN").astype(str).str.strip()
        )

        work.loc[work[self.UNDERLYING_COL] == "", self.UNDERLYING_COL] = "UNKNOWN"
        work.loc[work[self.COUNTERPARTY_COL] == "", self.COUNTERPARTY_COL] = "UNKNOWN"

        for col in [self.PREMIA_COL, self.FEES_COL, self.PNL_DELTA_COL]:
            work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0.0)

        work["trade_count"] = 1.0

        self._bucket_df = (
            work.groupby(
                [self.UNDERLYING_COL, self.COUNTERPARTY_COL],
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

        self._underlying_totals_df = (
            work.groupby(self.UNDERLYING_COL, observed=True, sort=False)
            .agg(
                **{
                    self.TOTAL_PREMIA_COL: (self.PREMIA_COL, "sum"),
                    self.TOTAL_FEES_COL: (self.FEES_COL, "sum"),
                    self.TOTAL_PNL_DELTA_COL: (self.PNL_DELTA_COL, "sum"),
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
            index=self.UNDERLYING_COL,
            columns=self.COUNTERPARTY_COL,
            values="selected_value",
        ).fillna(0.0)

        pivot = pivot.sort_index(axis=0).sort_index(axis=1)

        row_selected_sum = (
            bucket.groupby(self.UNDERLYING_COL, observed=True, sort=False)["selected_sum"].sum()
        )
        row_trade_sum = (
            bucket.groupby(self.UNDERLYING_COL, observed=True, sort=False)["trade_count"].sum()
        )

        if self._normalize_by_trades.get():
            selected_all = row_selected_sum / row_trade_sum.where(row_trade_sum != 0, 1.0)
        else:
            selected_all = row_selected_sum

        pivot[self.TOTAL_COL] = selected_all.reindex(pivot.index).fillna(0.0)

        result = pivot.reset_index()
        result = result.merge(self._underlying_totals_df, on=self.UNDERLYING_COL, how="left")

        info_cols = [
            self.TOTAL_COL,
            self.TOTAL_PREMIA_COL,
            self.TOTAL_FEES_COL,
            self.TOTAL_PNL_DELTA_COL,
            self.TOTAL_TRADES_COL,
        ]
        cp_cols = [c for c in result.columns if c not in [self.UNDERLYING_COL] + info_cols]

        result = result[[self.UNDERLYING_COL] + cp_cols + info_cols]

        total_row = {self.UNDERLYING_COL: self.GRAND_TOTAL_LABEL}
        if self._normalize_by_trades.get():
            for col in cp_cols:
                mask = bucket[self.COUNTERPARTY_COL] == col
                pnl = bucket.loc[mask, "selected_sum"].sum()
                trades = bucket.loc[mask, "trade_count"].sum()
                total_row[col] = pnl / trades if trades != 0 else 0.0
        else:
            for col in cp_cols:
                total_row[col] = float(result[col].sum()) if col in result.columns else 0.0
            
            
        total_row[self.TOTAL_COL] = float(result[self.TOTAL_COL].sum()) if self.TOTAL_COL in result.columns else 0.0
        total_row[self.TOTAL_PREMIA_COL] = float(self._underlying_totals_df[self.TOTAL_PREMIA_COL].sum())
        total_row[self.TOTAL_FEES_COL] = float(self._underlying_totals_df[self.TOTAL_FEES_COL].sum())
        total_row[self.TOTAL_PNL_DELTA_COL] = float(self._underlying_totals_df[self.TOTAL_PNL_DELTA_COL].sum())
        total_row[self.TOTAL_TRADES_COL] = float(self._underlying_totals_df[self.TOTAL_TRADES_COL].sum())

        result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

        if default_sort and self.TOTAL_COL in result.columns:
            all_mask = result[self.UNDERLYING_COL].astype(str) == self.GRAND_TOTAL_LABEL
            df_main = result.loc[~all_mask].copy()
            df_all = result.loc[all_mask].copy()
            df_main = df_main.sort_values(by=self.TOTAL_COL, ascending=False, kind="mergesort")
            result = pd.concat([df_main, df_all], ignore_index=True)
            self._sort_state[self.TOTAL_COL] = True

        underlying_count = max(len(result) - 1, 0)
        cp_count = len(cp_cols)
        self._table_df = result
        self._info_label.configure(
            text=f"Underlyings: {underlying_count} | Counterparties: {cp_count} | Metric: {self._selected_metric_name()}"
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
            self.TOTAL_PNL_DELTA_COL,
            self.TOTAL_TRADES_COL,
        }

        for col in columns:
            if col == self.UNDERLYING_COL:
                anchor = "w"
                width = 220
            elif col in info_cols:
                anchor = "e"
                width = 132 if col != self.TOTAL_TRADES_COL else 105
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
        name = str(row_map.get(self.UNDERLYING_COL, ""))
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

        all_mask = df[self.UNDERLYING_COL].astype(str) == self.GRAND_TOTAL_LABEL
        df_main = df.loc[~all_mask].copy()
        df_all = df.loc[all_mask].copy()

        if col == self.UNDERLYING_COL:
            df_main = df_main.sort_values(
                by=col,
                ascending=ascending,
                kind="mergesort",
                key=lambda s: s.astype(str).str.lower(),
            )
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
        if col_name == self.UNDERLYING_COL:
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
    def _export_html(self):
        if self._table_df.empty:
            messagebox.showinfo("Export HTML", "No data to export.")
            return

        default_name = self._default_export_filename()
        filepath = filedialog.asksaveasfilename(
            title="Save HTML report",
            defaultextension=".html",
            initialfile=default_name,
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
        )
        if not filepath:
            return

        html_text = self._build_html_report(self._table_df)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_text)

        try:
            self.clipboard_clear()
            self.clipboard_append(filepath)
            self.update()
        except Exception:
            pass

        messagebox.showinfo(
            "Export HTML",
            f"HTML exported successfully.\n\nPath copied to clipboard:\n{filepath}",
        )

    def _default_export_filename(self) -> str:
        metric = self._selected_metric_name().replace(" + ", "_").replace(" / ", "_per_")
        metric = metric.replace(" ", "_")
        return f"premia_matrix_{metric}.html"

    def _build_html_report(self, df: pd.DataFrame) -> str:
        columns = list(df.columns)
        first_col = self.UNDERLYING_COL
        sticky_bottom_index = len(df) - 1
        info_cols = {
            self.TOTAL_COL,
            self.TOTAL_PREMIA_COL,
            self.TOTAL_FEES_COL,
            self.TOTAL_PNL_DELTA_COL,
            self.TOTAL_TRADES_COL,
        }

        def is_numeric_col(col_name: str) -> bool:
            return col_name != first_col

        def parse_float(value):
            try:
                return float(value)
            except Exception:
                return None

        def cell_sign_class(col_name: str, value) -> str:
            if not is_numeric_col(col_name):
                return "label-cell"
            num = parse_float(value)
            if num is None:
                return "num-zero"
            if abs(num) < 1e-12:
                return "num-zero"
            if num > 0:
                return "num-pos"
            return "num-neg"

        def format_html_value(col_name: str, value) -> str:
            return html.escape(str(self._format_cell(col_name, value)))

        thead_html = "".join(
            f'<th class="{("sticky-col" if c == first_col else "") + (" info-col" if c in info_cols else "")}" '
            f'onclick="sortTable({idx})">{html.escape(str(c))}</th>'
            for idx, c in enumerate(columns)
        )

        body_rows = []
        for ridx, row in enumerate(df.itertuples(index=False, name=None)):
            row_map = dict(zip(columns, row))
            is_total_row = str(row_map.get(first_col, "")) == self.GRAND_TOTAL_LABEL
            tr_classes = []
            if is_total_row:
                tr_classes.append("grand-total-row")
            tr_class_attr = f' class="{" ".join(tr_classes)}"' if tr_classes else ""

            cells = []
            for cidx, (col, val) in enumerate(zip(columns, row)):
                classes = [cell_sign_class(col, val)]
                if col == first_col:
                    classes.append("sticky-col")
                if col in info_cols:
                    classes.append("info-col")
                if is_total_row:
                    classes.append("sticky-bottom")
                class_attr = " ".join(classes)
                cells.append(f'<td class="{class_attr}">{format_html_value(col, val)}</td>')

            body_rows.append(f"<tr{tr_class_attr}>" + "".join(cells) + "</tr>")

        body_html = "\n".join(body_rows)
        metric_label = html.escape(self._selected_metric_name())
        underlying_count = html.escape(str(max(len(df) - 1, 0)))
        cp_count = html.escape(str(max(len(columns) - 1 - len(info_cols), 0)))
        title = "Premia Matrix"

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
    :root {{
        --bg: #f4f6fb;
        --card: #ffffff;
        --border: #dde3f0;
        --header: #ece8ff;
        --header-text: #2b2250;
        --sticky-col: #fafbfe;
        --info-col: #f4f0ff;
        --grand-total: #eef1fb;
        --text: #1e2430;
        --muted: #5f6878;
        --green: #dff3df;
        --red: #f8dddd;
        --white: #ffffff;
        --lilac-outline: #b58cff;
        --shadow: 0 10px 30px rgba(34, 46, 80, 0.10);
    }}

    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
        margin: 0;
        background: linear-gradient(180deg, #f7f8fc 0%, #eef2f9 100%);
        color: var(--text);
        font-family: Arial, Helvetica, sans-serif;
    }}

    .page {{
        padding: 20px;
        height: 100%;
    }}

    .card {{
        background: var(--card);
        border: 1px solid var(--border);
        border-radius: 18px;
        box-shadow: var(--shadow);
        overflow: hidden;
        display: flex;
        flex-direction: column;
        height: calc(100vh - 40px);
    }}

    .topbar {{
        padding: 18px 20px 10px 20px;
        border-bottom: 1px solid var(--border);
        background: linear-gradient(180deg, #ffffff 0%, #fbfbff 100%);
    }}

    .title {{
        margin: 0 0 8px 0;
        font-size: 22px;
        font-weight: 700;
        color: #241b47;
    }}

    .meta {{
        color: var(--muted);
        font-size: 13px;
    }}

    .table-wrap {{
        overflow: auto;
        flex: 1 1 auto;
        position: relative;
    }}

    table {{
        border-collapse: separate;
        border-spacing: 0;
        min-width: 100%;
        width: max-content;
    }}

    thead th {{
        position: sticky;
        top: 0;
        z-index: 5;
        background: var(--header);
        color: var(--header-text);
        font-weight: 700;
        cursor: pointer;
        user-select: none;
        box-shadow: inset 0 -1px 0 var(--border);
    }}

    th, td {{
        padding: 10px 12px;
        border-right: 1px solid var(--border);
        border-bottom: 1px solid var(--border);
        white-space: nowrap;
        font-size: 13px;
    }}

    th:first-child, td:first-child {{
        border-left: 1px solid var(--border);
    }}

    .sticky-col {{
        position: sticky;
        left: 0;
        z-index: 4;
        background: var(--sticky-col);
    }}

    thead .sticky-col {{
        z-index: 6;
        background: #e7e1ff;
    }}

    .info-col {{
        font-weight: 600;
    }}

    tbody tr:hover td {{
        filter: brightness(0.985);
    }}

    tbody tr.selected-row td {{
        box-shadow: inset 0 0 0 2px var(--lilac-outline);
    }}

    .num-pos {{
        background: var(--green);
        text-align: right;
    }}

    .num-neg {{
        background: var(--red);
        text-align: right;
    }}

    .num-zero {{
        background: var(--white);
        text-align: right;
    }}

    .label-cell {{
        background: var(--sticky-col);
        text-align: left;
        font-weight: 600;
    }}

    .grand-total-row td {{
        position: sticky;
        bottom: 0;
        z-index: 3;
        font-weight: 700;
        box-shadow: inset 0 1px 0 var(--border), inset 0 -1px 0 var(--border);
    }}

    .grand-total-row .sticky-col {{
        z-index: 4;
    }}

    .grand-total-row .label-cell {{
        background: var(--grand-total);
    }}

    .grand-total-row .num-pos {{
        background: color-mix(in srgb, var(--green) 78%, var(--grand-total));
    }}

    .grand-total-row .num-neg {{
        background: color-mix(in srgb, var(--red) 78%, var(--grand-total));
    }}

    .grand-total-row .num-zero {{
        background: var(--grand-total);
    }}
</style>
</head>
<body>
<div class="page">
  <div class="card">
    <div class="topbar">
      <h1 class="title">{title}</h1>
      <div class="meta">Metric: {metric_label} &nbsp;|&nbsp; Underlyings: {underlying_count} &nbsp;|&nbsp; Counterparties: {cp_count}</div>
    </div>
    <div class="table-wrap">
      <table id="matrixTable">
        <thead>
          <tr>{thead_html}</tr>
        </thead>
        <tbody>
{body_html}
        </tbody>
      </table>
    </div>
  </div>
</div>
<script>
function parseCellValue(text) {{
    const cleaned = String(text).replace(/,/g, '').trim();
    const n = Number(cleaned);
    return Number.isNaN(n) ? null : n;
}}

function sortTable(colIndex) {{
    const table = document.getElementById('matrixTable');
    const tbody = table.querySelector('tbody');
    const allRows = Array.from(tbody.querySelectorAll('tr'));
    if (allRows.length <= 1) return;

    const totalRow = allRows[allRows.length - 1];
    const rows = allRows.slice(0, -1);
    const current = table.getAttribute('data-sort-col');
    const currentDir = table.getAttribute('data-sort-dir') || 'asc';
    const nextDir = (String(current) === String(colIndex) && currentDir === 'asc') ? 'desc' : 'asc';

    rows.sort((a, b) => {{
        const aText = a.children[colIndex].innerText;
        const bText = b.children[colIndex].innerText;
        const aNum = parseCellValue(aText);
        const bNum = parseCellValue(bText);

        let cmp;
        if (aNum !== null && bNum !== null) {{
            cmp = aNum - bNum;
        }} else {{
            cmp = String(aText).localeCompare(String(bText));
        }}
        return nextDir === 'asc' ? cmp : -cmp;
    }});

    rows.forEach(row => tbody.appendChild(row));
    tbody.appendChild(totalRow);

    table.setAttribute('data-sort-col', colIndex);
    table.setAttribute('data-sort-dir', nextDir);
    enableRowSelection();
}}

function enableRowSelection() {{
    const tbodyRows = document.querySelectorAll('#matrixTable tbody tr');
    tbodyRows.forEach(row => {{
        row.onclick = () => {{
            tbodyRows.forEach(r => r.classList.remove('selected-row'));
            row.classList.add('selected-row');
        }};
    }});
}}

enableRowSelection();
</script>
</body>
</html>
"""