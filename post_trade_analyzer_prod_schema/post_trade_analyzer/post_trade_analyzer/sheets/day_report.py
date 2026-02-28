from __future__ import annotations

from dataclasses import dataclass
from datetime import date as DateType
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, filedialog
import html as _html

import pandas as pd

from ..utils.table_utils import build_display_cache


# ============================================================
# Simple autocomplete combobox (fast + robust)
# ============================================================
class AutocompleteCombobox(ttk.Combobox):
    def __init__(self, master, *, values: List[str], **kwargs):
        super().__init__(master, values=values, **kwargs)
        self._all_values = list(values)
        self.bind("<KeyRelease>", self._on_keyrelease)

    def set_values(self, values: List[str]) -> None:
        self._all_values = list(values)
        self["values"] = self._all_values

    def _on_keyrelease(self, event) -> None:
        if event.keysym in ("Up", "Down", "Left", "Right", "Return", "Escape", "Tab"):
            return
        text = self.get().strip().lower()
        if not text:
            self["values"] = self._all_values
            return
        filtered = [v for v in self._all_values if text in v.lower()]
        self["values"] = filtered if filtered else self._all_values


def _parse_iso_date(s: str) -> Optional[DateType]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return pd.Timestamp(s).date()
    except Exception:
        return None


# ============================================================
# Day - Report sheet
# ============================================================
@dataclass(frozen=True)
class _SortState:
    col: str = ""
    asc: bool = True


class DayReportSheet(ttk.Frame):
    """
    Day - Report (MULTI-DAY):
      - Select multiple days (available days list) + filter entry
      - Table has ONE ROW per (date, underlyingName), using EOD last trade per (date, underlying)
      - Columns:
          date, underlyingName, feesCum, PnLVonDeltaCum, PremiaCum, Total, Anpassung, trades, portfolio
      - Sortable by clicking headers
      - Bottom row: ALL (sum) - always stays at bottom even after sort
      - Export HTML:
          * sticky header
          * scroll inside panel
          * sticky ALL row (tfoot)
          * right-aligned integer numbers
          * click header to sort (JS)
          * click row to highlight (JS)
          * after saving: path copied to clipboard + toast in app
    """

    sheet_id = "day_report"
    sheet_title = "Day - Report"

    REPORT_COLS = [
        "date",
        "underlyingName",
        "feesCum",
        "PnLVonDeltaCum",
        "PremiaCum",
        "Total",
        "Anpassung",
        "trades",
        "portfolio",
    ]

    NUMERIC_COLS = ["feesCum", "PnLVonDeltaCum", "PremiaCum", "Total", "Anpassung", "trades"]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._trades: Optional[pd.DataFrame] = None
        self._adj: Optional[pd.DataFrame] = None

        self._master: pd.DataFrame = pd.DataFrame()   # precomputed (date, underlying)
        self._available_dates: List[str] = []         # ISO strings

        self._df_day: pd.DataFrame = pd.DataFrame()   # selected days view (incl ALL)
        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._sort = _SortState()

        self.day_filter_var = tk.StringVar()
        self.info_var = tk.StringVar(value="Load data to begin.")
        self.summary_var = tk.StringVar(value="")
        self.toast_var = tk.StringVar(value="")
        self._toast_after_id: Optional[str] = None

        self._build()

    # -------------------------
    # UI
    # -------------------------
    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="Day - Report", style="Title.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=14, pady=(0, 10))

        # Days selector (filter + listbox)
        ttk.Label(controls, text="Days (filter)", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.day_filter_var, width=16).grid(
            row=1, column=0, sticky="w", padx=(0, 10)
        )
        self.day_filter_var.trace_add("write", lambda *_: self._refresh_days_listbox())

        self.days_lb = tk.Listbox(controls, selectmode="extended", height=6, exportselection=False)
        self.days_lb.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(6, 0))

        btns = ttk.Frame(controls)
        btns.grid(row=2, column=1, sticky="nw", pady=(6, 0))

        ttk.Button(btns, text="All", width=7, command=self._days_select_all).pack(fill="x")
        ttk.Button(btns, text="None", width=7, command=self._days_select_none).pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="Apply", style="Accent.TButton", width=7, command=self._apply_days).pack(
            fill="x", pady=(12, 0)
        )
        ttk.Button(btns, text="Clear", style="Pink.TButton", width=7, command=self._clear_days).pack(fill="x", pady=(6, 0))

        self.export_btn = ttk.Button(
            controls, text="Export HTML", style="Purple.TButton", command=self._export_html, state="disabled"
        )
        self.export_btn.grid(row=1, column=2, sticky="w", padx=(14, 0))

        # Small toast label (auto hides)
        ttk.Label(controls, textvariable=self.toast_var, style="Muted.TLabel").grid(
            row=1, column=3, sticky="w", padx=(14, 0)
        )

        controls.columnconfigure(4, weight=1)

        # Summary line under controls (uses ALL row)
        summ = ttk.Frame(self)
        summ.pack(fill="x", padx=14, pady=(0, 8))
        ttk.Label(summ, textvariable=self.summary_var, style="Muted.TLabel").pack(side="left")

        # Table
        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.tree = ttk.Treeview(inner, style="Futur.Treeview", show="headings")
        self.vsb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(inner, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")

        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)

        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#F8FAFF")
        self.tree.tag_configure("allrow", background="#EEF2FF")  # ALL row

        self._init_columns()
        # Local button styles (fast, no global theme refactor)
        style = ttk.Style()
        
        # Purple export
        style.configure("Purple.TButton", padding=(10, 6))
        style.map(
            "Purple.TButton",
            background=[("!disabled", "#7C3AED"), ("active", "#6D28D9"), ("disabled", "#E5E7EB")],
            foreground=[("!disabled", "white"), ("disabled", "#9CA3AF")],
        )
        
        # Light pink clear
        style.configure("Pink.TButton", padding=(10, 6))
        style.map(
            "Pink.TButton",
            background=[("!disabled", "#FCE7F3"), ("active", "#FBCFE8"), ("disabled", "#F3F4F6")],
            foreground=[("!disabled", "#9D174D"), ("disabled", "#9CA3AF")],
        )

    def _init_columns(self) -> None:
        cols = self.REPORT_COLS
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
            if c == "date":
                w, anchor = 120, "w"
            elif c == "underlyingName":
                w, anchor = 190, "w"
            elif c == "portfolio":
                w, anchor = 150, "w"
            else:
                w = 120
                anchor = "e" if c in self.NUMERIC_COLS else "w"
            self.tree.column(c, width=w, minwidth=90, anchor=anchor, stretch=False)

    # -------------------------
    # Toast helper
    # -------------------------
    def _toast(self, msg: str, ms: int = 2000) -> None:
        self.toast_var.set(msg)
        if self._toast_after_id is not None:
            try:
                self.after_cancel(self._toast_after_id)
            except Exception:
                pass
        self._toast_after_id = self.after(ms, lambda: self.toast_var.set(""))

    # -------------------------
    # Days listbox helpers
    # -------------------------
    def _refresh_days_listbox(self) -> None:
        q = (self.day_filter_var.get() or "").strip()
        self.days_lb.delete(0, "end")
        vals = self._available_dates
        if q:
            vals = [d for d in vals if q in d]
        for d in vals:
            self.days_lb.insert("end", d)

    def _days_select_all(self) -> None:
        self.days_lb.selection_set(0, "end")

    def _days_select_none(self) -> None:
        self.days_lb.selection_clear(0, "end")

    def _selected_days(self) -> List[DateType]:
        # listbox contains the filtered list; read strings from listbox itself
        out: List[DateType] = []
        for i in self.days_lb.curselection():
            s = self.days_lb.get(i)
            d = _parse_iso_date(s)
            if d is not None:
                out.append(d)
        return out

    def _clear_days(self) -> None:
        self.day_filter_var.set("")
        self._refresh_days_listbox()
        self._days_select_none()
        self._set_day_df(pd.DataFrame())
        self.summary_var.set("")
        self.info_var.set("Select one or more days.")
        self.export_btn.configure(state="disabled")

    # -------------------------
    # API from app
    # -------------------------
    def on_df_loaded(self, trades: pd.DataFrame) -> None:
        self._trades = trades
        self._rebuild_master_if_ready()

    def on_adjustment_loaded(self, adj: pd.DataFrame) -> None:
        self._adj = adj
        self._rebuild_master_if_ready()

    # -------------------------
    # Precompute master table once per load
    # -------------------------
    def _rebuild_master_if_ready(self) -> None:
        if self._trades is None:
            return

        df = self._trades
        if df is None or df.empty:
            self._master = pd.DataFrame()
            self._available_dates = []
            self._refresh_days_listbox()
            self.info_var.set("No trades loaded.")
            self._set_day_df(pd.DataFrame())
            self.summary_var.set("")
            self.export_btn.configure(state="disabled")
            return

        need = ["date", "underlyingName", "tradeTime", "portfolio", "feesCum", "PnLVonDeltaCum", "PremiaCum", "Total"]
        for c in need:
            if c not in df.columns:
                self.info_var.set(f"Missing column: {c}")
                return

        # trades count per (date, underlying)
        cnt = (
            df.groupby(["date", "underlyingName"], sort=False)
            .size()
            .rename("trades")
            .reset_index()
        )

        # last trade per (date, underlying)
        tt = pd.to_datetime(df["tradeTime"], errors="coerce")
        helper = pd.DataFrame(
            {"date": df["date"], "underlyingName": df["underlyingName"], "_tt": tt}
        ).dropna(subset=["date", "underlyingName", "_tt"])
        if helper.empty:
            self._master = pd.DataFrame()
            self._available_dates = []
            self._refresh_days_listbox()
            self.info_var.set("No valid tradeTime values.")
            self._set_day_df(pd.DataFrame())
            self.summary_var.set("")
            self.export_btn.configure(state="disabled")
            return

        idx = helper.groupby(["date", "underlyingName"], sort=False)["_tt"].idxmax()
        last = df.loc[idx, ["date", "underlyingName", "portfolio", "feesCum", "PnLVonDeltaCum", "PremiaCum", "Total"]].copy()
        last.reset_index(drop=True, inplace=True)

        out = last.merge(cnt, on=["date", "underlyingName"], how="left")
        out["trades"] = pd.to_numeric(out["trades"], errors="coerce").fillna(0).astype(int)

        # merge adjustments (Anpassung)
        adj = self._adj
        if adj is not None and not adj.empty and "date" in adj.columns and "underlyingName" in adj.columns:
            a = adj.copy()
            if "Anpassung" not in a.columns:
                a["Anpassung"] = 0.0
            a["Anpassung"] = pd.to_numeric(a["Anpassung"], errors="coerce").fillna(0.0)
            a = a.groupby(["date", "underlyingName"], sort=False, as_index=False)[["Anpassung"]].sum()
            out = out.merge(a, on=["date", "underlyingName"], how="left")
            out["Anpassung"] = out["Anpassung"].fillna(0.0)
        else:
            out["Anpassung"] = 0.0

        # enforce numeric
        for c in ["feesCum", "PnLVonDeltaCum", "PremiaCum", "Total", "Anpassung"]:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)

        out = out.sort_values(["date", "underlyingName"], kind="mergesort").reset_index(drop=True)

        self._master = out

        dates = sorted(out["date"].dropna().unique().tolist())
        self._available_dates = [d.isoformat() if hasattr(d, "isoformat") else str(d) for d in dates]
        self._refresh_days_listbox()

        # Preselect last day by default
        if self._available_dates:
            self.days_lb.selection_clear(0, "end")
            self.days_lb.selection_set(len(self._available_dates) - 1)

        self._apply_days()

    # -------------------------
    # Apply selected days
    # -------------------------
    def _apply_days(self) -> None:
        sel_days = self._selected_days()
        if not sel_days:
            self.info_var.set("Select at least one day.")
            self.export_btn.configure(state="disabled")
            self._set_day_df(pd.DataFrame())
            self.summary_var.set("")
            return

        base = self._master
        if base is None or base.empty:
            self._set_day_df(pd.DataFrame())
            self.summary_var.set("")
            self.info_var.set("No data.")
            self.export_btn.configure(state="disabled")
            return

        view = base[base["date"].isin(sel_days)].copy()
        if view.empty:
            self._set_day_df(pd.DataFrame())
            self.summary_var.set("")
            self.info_var.set("No rows for selected days.")
            self.export_btn.configure(state="disabled")
            return

        # Add ALL row at bottom (sum over all selected days + all underlyings)
        all_row = self._build_all_row(view)
        view = pd.concat([view, all_row], ignore_index=True)

        self._sort = _SortState()
        self._set_day_df(view)

        # Summary (PnL = Total + Anpassung)
        r = all_row.iloc[0]
        trades = int(r.get("trades", 0))
        total = float(r.get("Total", 0.0))
        adj = float(r.get("Anpassung", 0.0))
        fees = float(r.get("feesCum", 0.0))
        pnl = total + adj
        self.summary_var.set(f"ALL  |  Trades: {trades:,}  |  PnL: {pnl:,.0f}  |  Fees: {fees:,.0f}")

        self.info_var.set(f"Days: {len(sel_days)} | rows: {len(view)-1:,} (+ALL)")
        self.export_btn.configure(state="normal")

    def _build_all_row(self, df: pd.DataFrame) -> pd.DataFrame:
        sums = {c: float(pd.to_numeric(df[c], errors="coerce").fillna(0.0).sum()) for c in self.NUMERIC_COLS if c in df.columns}
        if "trades" in sums:
            sums["trades"] = int(round(sums["trades"]))

        row = {
            "date": "",
            "underlyingName": "ALL",
            "feesCum": sums.get("feesCum", 0.0),
            "PnLVonDeltaCum": sums.get("PnLVonDeltaCum", 0.0),
            "PremiaCum": sums.get("PremiaCum", 0.0),
            "Total": sums.get("Total", 0.0),
            "Anpassung": sums.get("Anpassung", 0.0),
            "trades": sums.get("trades", 0),
            "portfolio": "",
        }
        return pd.DataFrame([row], columns=self.REPORT_COLS)

    # -------------------------
    # Table render + sort
    # -------------------------
    def _set_day_df(self, df: pd.DataFrame) -> None:
        self._df_day = df if df is not None else pd.DataFrame()
        self._cache, self._cache_len = build_display_cache(self._df_day)
        self._render()

    def _render(self) -> None:
        self.tree.delete(*self.tree.get_children())
        df = self._df_day
        if df is None or df.empty:
            return

        cols = self.REPORT_COLS
        cache = self._cache

        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]
            is_all = (str(df.iloc[i]["underlyingName"]) == "ALL") if "underlyingName" in df.columns else False
            if is_all:
                self.tree.insert("", "end", values=values, tags=("allrow",))
            else:
                tag = "even" if (i % 2 == 0) else "odd"
                self.tree.insert("", "end", values=values, tags=(tag,))

    def _sort_by(self, col: str) -> None:
        df = self._df_day
        if df is None or df.empty or col not in df.columns:
            return

        # keep ALL at bottom always
        has_all = ("underlyingName" in df.columns) and (df["underlyingName"].astype(str) == "ALL").any()
        if has_all:
            df_main = df[df["underlyingName"].astype(str) != "ALL"].copy()
            df_all = df[df["underlyingName"].astype(str) == "ALL"].copy()
        else:
            df_main = df.copy()
            df_all = pd.DataFrame(columns=df.columns)

        if self._sort.col == col:
            asc = not self._sort.asc
        else:
            asc = True

        try:
            df_main = df_main.sort_values(by=col, ascending=asc, kind="mergesort")
        except Exception:
            df_main = (
                df_main.assign(_tmp=df_main[col].astype(str))
                .sort_values(by="_tmp", ascending=asc, kind="mergesort")
                .drop(columns="_tmp")
            )

        out = pd.concat([df_main, df_all], ignore_index=True) if not df_all.empty else df_main.reset_index(drop=True)
        self._sort = _SortState(col=col, asc=asc)
        self._set_day_df(out)

    # -------------------------
    # Export HTML
    # -------------------------
    def _export_html(self) -> None:
        df = self._df_day
        if df is None or df.empty:
            self.info_var.set("Nothing to export.")
            return

        # Separate ALL row -> sticky footer
        main = df[df["underlyingName"].astype(str) != "ALL"].copy() if "underlyingName" in df.columns else df.copy()
        all_row = df[df["underlyingName"].astype(str) == "ALL"].copy() if "underlyingName" in df.columns else pd.DataFrame(columns=df.columns)

        num_cols = [c for c in self.NUMERIC_COLS if c in df.columns]
        cols = self.REPORT_COLS[:]

        def fmt_int(x) -> str:
            try:
                v = float(x)
            except Exception:
                return ""
            return f"{int(round(v)):,}"

        def td(val: str, cls: str = "") -> str:
            cls_attr = f' class="{cls}"' if cls else ""
            return f"<td{cls_attr}>{val}</td>"

        def tr(row_cells: List[str], extra_cls: str = "") -> str:
            cls_attr = f' class="{extra_cls}"' if extra_cls else ""
            return f"<tr{cls_attr}>" + "".join(row_cells) + "</tr>"

        # THEAD with data-type for sorting
        thead_cells = []
        for c in cols:
            dtype = "num" if c in num_cols else "txt"
            thead_cells.append(f'<th data-type="{dtype}">{_html.escape(c)}</th>')
        thead = "<thead><tr>" + "".join(thead_cells) + "</tr></thead>"

        # TBODY rows
        body_rows = []
        for _, r in main.iterrows():
            cells = []
            for c in cols:
                v = r.get(c, "")
                if c in num_cols:
                    cells.append(td(fmt_int(v), "num"))
                else:
                    cells.append(td(_html.escape("" if pd.isna(v) else str(v)), "txt"))
            body_rows.append(tr(cells))
        tbody = "<tbody>" + "".join(body_rows) + "</tbody>"

        # TFOOT ALL row sticky
        tfoot = ""
        if not all_row.empty:
            r = all_row.iloc[0]
            cells = []
            for c in cols:
                v = r.get(c, "")
                if c in num_cols:
                    cells.append(td(fmt_int(v), "num"))
                else:
                    cells.append(td(_html.escape("" if pd.isna(v) else str(v)), "txt"))
            tfoot = "<tfoot>" + tr(cells, "allrow") + "</tfoot>"

        # KPI strip (from ALL)
        kpi_html = ""
        if not all_row.empty:
            r = all_row.iloc[0]
            trades = int(round(float(r.get("trades", 0) or 0)))
            total = float(r.get("Total", 0.0) or 0.0)
            adj = float(r.get("Anpassung", 0.0) or 0.0)
            fees = float(r.get("feesCum", 0.0) or 0.0)
            pnl = total + adj
            kpi_html = f"""
              <div class="kpis">
                <div class="kpi"><div class="kpiLabel">PnL</div><div class="kpiVal">{pnl:,.0f}</div></div>
                <div class="kpi"><div class="kpiLabel">Fees</div><div class="kpiVal">{fees:,.0f}</div></div>
                <div class="kpi"><div class="kpiLabel">Trades</div><div class="kpiVal">{trades:,}</div></div>
              </div>
            """

        # Title label: show selected days compactly
        sel_days = [self.days_lb.get(i) for i in self.days_lb.curselection()]
        if len(sel_days) == 1:
            title_label = sel_days[0]
        elif len(sel_days) <= 4:
            title_label = " + ".join(sel_days)
        else:
            title_label = f"{sel_days[0]} .. {sel_days[-1]} ({len(sel_days)} days)"

        html_doc = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Day Report { _html.escape(title_label) }</title>
<style>
  :root {{
    --panel: #ffffff;
    --grid: #e5e7eb;
    --head: #111827;
    --muted: #6b7280;
    --rowHover: #f3f6ff;
    --rowSelect: #dbeafe;
    --allBg: #eef2ff;
  }}

  body {{
    margin: 0;
    font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial;
    background: #f6f8ff;
    color: var(--head);
  }}

  .wrap {{
    padding: 16px;
  }}

  .titlebar {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 10px;
    gap: 12px;
  }}
  .titlebar h1 {{
    font-size: 18px;
    margin: 0;
  }}
  .titlebar .meta {{
    color: var(--muted);
    font-size: 12px;
    text-align: right;
    white-space: nowrap;
  }}

  .kpis {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 10px;
  }}
  .kpi {{
    background: var(--panel);
    border: 1px solid var(--grid);
    border-radius: 14px;
    padding: 10px 12px;
  }}
  .kpiLabel {{
    font-size: 11px;
    color: var(--muted);
  }}
  .kpiVal {{
    font-size: 18px;
    font-weight: 800;
    margin-top: 2px;
    font-variant-numeric: tabular-nums;
  }}

  .panel {{
    background: var(--panel);
    border: 1px solid var(--grid);
    border-radius: 14px;
    overflow: hidden;
  }}

  /* scroll inside the panel */
  .table-scroll {{
    max-height: calc(100vh - 190px);
    overflow: auto;
  }}

  table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 12px;
  }}

  thead th {{
    position: sticky;
    top: 0;
    z-index: 4;
    background: #ffffff;
    border-bottom: 1px solid var(--grid);
    padding: 10px 10px;
    text-align: left;
    white-space: nowrap;
    user-select: none;
  }}

  thead th[data-dir="asc"]::after {{
    content: " ▲";
    color: #2563eb;
    font-size: 10px;
  }}
  thead th[data-dir="desc"]::after {{
    content: " ▼";
    color: #2563eb;
    font-size: 10px;
  }}

  tbody td, tfoot td {{
    border-bottom: 1px solid #f0f2f7;
    padding: 8px 10px;
    white-space: nowrap;
  }}

  tbody tr:hover {{
    background: var(--rowHover);
    cursor: pointer;
  }}

  tbody tr.selected {{
    background: var(--rowSelect);
  }}

  td.num {{
    text-align: right;
    font-variant-numeric: tabular-nums;
  }}

  td.txt {{
    text-align: left;
  }}

  /* Sticky ALL row at bottom */
  tfoot td {{
    position: sticky;
    bottom: 0;
    z-index: 3;
    background: var(--allBg);
    border-top: 2px solid #c7d2fe;
    font-weight: 800;
  }}

</style>
</head>
<body>
  <div class="wrap">
    <div class="titlebar">
      <h1>Day - Report</h1>
      <div class="meta">Days: { _html.escape(title_label) } &nbsp; | &nbsp; Generated from app</div>
    </div>

    {kpi_html}

    <div class="panel">
      <div class="table-scroll">
        <table id="reportTable">
          {thead}
          {tbody}
          {tfoot}
        </table>
      </div>
    </div>
  </div>

<script>
  const table = document.getElementById("reportTable");
  const tbody = table.querySelector("tbody");
  const headers = Array.from(table.querySelectorAll("thead th"));

  // Row selection highlight
  let selected = null;
  table.addEventListener("click", (e) => {{
    const tr = e.target.closest("tbody tr");
    if (!tr) return;
    if (selected) selected.classList.remove("selected");
    tr.classList.add("selected");
    selected = tr;
  }});

  // Sorting (tbody only, footer stays sticky)
  const sortState = {{ idx: -1, asc: true }};

  function getCellValue(tr, idx, type) {{
    const td = tr.children[idx];
    if (!td) return "";
    const text = (td.textContent || "").trim();
    if (type === "num") {{
      const v = text.replace(/,/g, "");
      const n = Number(v);
      return Number.isFinite(n) ? n : 0;
    }}
    return text.toLowerCase();
  }}

  function sortByColumn(idx, type) {{
    const rows = Array.from(tbody.querySelectorAll("tr"));

    if (sortState.idx === idx) sortState.asc = !sortState.asc;
    else {{ sortState.idx = idx; sortState.asc = true; }}

    rows.sort((a, b) => {{
      const va = getCellValue(a, idx, type);
      const vb = getCellValue(b, idx, type);
      if (va < vb) return sortState.asc ? -1 : 1;
      if (va > vb) return sortState.asc ? 1 : -1;
      return 0;
    }});

    const frag = document.createDocumentFragment();
    for (const r of rows) frag.appendChild(r);
    tbody.appendChild(frag);

    headers.forEach(h => h.dataset.dir = "");
    headers[idx].dataset.dir = sortState.asc ? "asc" : "desc";
  }}

  headers.forEach((th, idx) => {{
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {{
      const type = th.dataset.type || "txt";
      sortByColumn(idx, type);
    }});
  }});
</script>
</body>
</html>
"""

        default_name = "day_report.html"
        if len(sel_days) == 1:
            default_name = f"day_report_{sel_days[0]}.html"
        elif len(sel_days) > 1:
            default_name = f"day_report_{sel_days[0]}_to_{sel_days[-1]}.html"
        default_name = default_name.replace(":", "-").replace("/", "-").replace(" ", "_")

        path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML file", "*.html")],
            initialfile=default_name,
            title="Save Day Report HTML",
        )
        if not path:
            return

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_doc)

            # Copy path to clipboard for instant Ctrl+V in browser
            try:
                self.clipboard_clear()
                self.clipboard_append(path)
                self.update()
            except Exception:
                pass

            self.info_var.set(f"Exported HTML (path copied): {path}")
            self._toast("✅ Exported + path copied (Ctrl+V in browser)", ms=2500)
        except Exception as e:
            self.info_var.set(f"Export failed: {e}")
            self._toast(f"❌ Export failed: {e}", ms=3000)