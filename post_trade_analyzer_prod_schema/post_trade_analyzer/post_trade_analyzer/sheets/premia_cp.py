from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional, List

import numpy as np
import pandas as pd

from .raw_data import BaseSheet


def _fmt_int(x) -> str:
    try:
        return f"{int(round(float(x))):,}"
    except Exception:
        return "0"


def _fmt_float(x, digits: int = 2) -> str:
    try:
        return f"{float(x):,.{digits}f}"
    except Exception:
        return "0.00"


class PremiaCPSheet(BaseSheet):
    sheet_id = "premia_cp"
    sheet_title = "Premia CP"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: Optional[pd.DataFrame] = None
        self._filtered_df: Optional[pd.DataFrame] = None
        self._table_df: Optional[pd.DataFrame] = None

        self._sort_col: str = "PnL"
        self._sort_desc: bool = True

        self._cp_values: List[str] = ["ALL"]

        self.cp_var = tk.StringVar(value="ALL")

        self.kpi_total_pnl = tk.StringVar(value="0.00")
        self.kpi_trades = tk.StringVar(value="0")
        self.kpi_pnl_trade = tk.StringVar(value="0.00")
        self.kpi_best_ul = tk.StringVar(value="-")
        self.kpi_worst_ul = tk.StringVar(value="-")
        self.kpi_active_uls = tk.StringVar(value="0")
        self.kpi_total_premia = tk.StringVar(value="0.00")
        self.kpi_total_fees = tk.StringVar(value="0.00")

        self._tooltip: Optional[tk.Toplevel] = None
        self._tooltip_label: Optional[tk.Label] = None

        self._build()

    # =========================
    # UI
    # =========================
    def _build(self) -> None:
        outer = ttk.Frame(self)
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        title_row = ttk.Frame(outer)
        title_row.pack(fill="x", pady=(0, 10))
        ttk.Label(title_row, text="Premia CP", style="Title.TLabel").pack(side="left")

        filter_card = ttk.Frame(outer, style="Card.TFrame")
        filter_card.pack(fill="x", pady=(0, 10))

        filter_inner = ttk.Frame(filter_card, style="Card.TFrame")
        filter_inner.pack(fill="x", padx=12, pady=12)

        ttk.Label(filter_inner, text="Counterparty", style="Muted.TLabel").pack(side="left", padx=(0, 8))

        self.cp_combo = ttk.Combobox(
            filter_inner,
            textvariable=self.cp_var,
            state="readonly",
            width=28,
            values=self._cp_values,
        )
        self.cp_combo.pack(side="left")
        self.cp_combo.bind("<<ComboboxSelected>>", self._on_filter_changed)

        kpi_wrap = ttk.Frame(outer)
        kpi_wrap.pack(fill="x", pady=(0, 10))

        self._create_kpi_card(kpi_wrap, "Total PnL", self.kpi_total_pnl).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "Total Premia", self.kpi_total_premia).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "Total Fees", self.kpi_total_fees).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "Trades", self.kpi_trades).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "PnL / Trade", self.kpi_pnl_trade).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "Best Underlying", self.kpi_best_ul).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "Worst Underlying", self.kpi_worst_ul).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._create_kpi_card(kpi_wrap, "Active Underlyings", self.kpi_active_uls).pack(side="left", fill="x", expand=True)

        bottom = ttk.Frame(outer)
        bottom.pack(fill="both", expand=True)

        chart_card = ttk.Frame(bottom, style="Card.TFrame")
        chart_card.pack(side="left", fill="both", expand=True, padx=(0, 8))

        chart_inner = ttk.Frame(chart_card, style="Card.TFrame")
        chart_inner.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(chart_inner, text="Cumulative evolution", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 8))

        self.chart = tk.Canvas(chart_inner, bg="#FFFFFF", highlightthickness=0)
        self.chart.pack(fill="both", expand=True)

        table_card = ttk.Frame(bottom, style="Card.TFrame")
        table_card.pack(side="left", fill="both", expand=False)
        table_card.configure(width=470)

        table_inner = ttk.Frame(table_card, style="Card.TFrame")
        table_inner.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(table_inner, text="Underlying summary", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 8))

        tree_wrap = ttk.Frame(table_inner)
        tree_wrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_wrap,
            style="Futur.Treeview",
            show="headings",
            selectmode="browse",
            columns=("underlyingName", "PnL", "Fees", "Trades", "PnL_per_trade"),
        )
        self.tree.heading("underlyingName", text="underlyingName", command=lambda: self._sort_table("underlyingName"))
        self.tree.heading("PnL", text="PnL", command=lambda: self._sort_table("PnL"))
        self.tree.heading("Trades", text="Trades", command=lambda: self._sort_table("Trades"))
        self.tree.heading("PnL_per_trade", text="PnL/Trade", command=lambda: self._sort_table("PnL_per_trade"))
        self.tree.heading("Fees", text="Fees", command=lambda: self._sort_table("Fees"))

        self.tree.column("underlyingName", width=170, minwidth=120, anchor="w", stretch=True)
        self.tree.column("PnL", width=95, minwidth=80, anchor="e", stretch=False)
        self.tree.column("Fees", width=95, minwidth=80, anchor="e", stretch=False)
        self.tree.column("Trades", width=80, minwidth=70, anchor="e", stretch=False)
        self.tree.column("PnL_per_trade", width=95, minwidth=80, anchor="e", stretch=False)
        

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)

        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#F8FAFF")

        self.chart.bind("<Configure>", self._on_chart_resize)
        self.chart.bind("<Motion>", self._on_chart_motion)
        self.chart.bind("<Leave>", self._on_chart_leave)

    def _create_kpi_card(self, parent: tk.Misc, title: str, value_var: tk.StringVar) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame")

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        ttk.Label(inner, text=title, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(inner, textvariable=value_var, style="Title.TLabel").pack(anchor="w", pady=(4, 0))

        return card

    # =========================
    # Public API
    # =========================
    def on_df_loaded(self, df: pd.DataFrame) -> None:
        self._df = df

        if df is None or df.empty:
            self._cp_values = ["ALL"]
            self.cp_combo["values"] = self._cp_values
            self.cp_var.set("ALL")
            self._set_empty_state()
            return

        cp_series = df["counterparty"].fillna("").astype(str).str.strip()
        cp_values = sorted(v for v in cp_series.unique().tolist() if v)
        self._cp_values = ["ALL"] + cp_values
        self.cp_combo["values"] = self._cp_values

        current = self.cp_var.get()
        if current not in self._cp_values:
            self.cp_var.set("ALL")

        self._apply_filter_and_render()

    # =========================
    # Events
    # =========================
    def _on_filter_changed(self, _event=None) -> None:
        self._apply_filter_and_render()

    def _on_chart_resize(self, _event=None) -> None:
        self._render_chart()

    def _on_chart_motion(self, event) -> None:
        if self._filtered_df is None or self._filtered_df.empty:
            self._hide_tooltip()
            return

        w = max(self.chart.winfo_width(), 10)
        h = max(self.chart.winfo_height(), 10)

        left = 58
        right = 18
        top = 18
        bottom = 42

        plot_w = max(w - left - right, 10)
        plot_h = max(h - top - bottom, 10)

        x = event.x
        y = event.y

        if x < left or x > left + plot_w or y < top or y > top + plot_h:
            self._hide_tooltip()
            return

        df = self._filtered_df
        n = len(df)
        if n == 0:
            self._hide_tooltip()
            return

        if n == 1:
            idx = 0
        else:
            frac = (x - left) / plot_w
            idx = int(round(frac * (n - 1)))
            idx = max(0, min(n - 1, idx))

        row = df.iloc[idx]

        ts = pd.to_datetime(row["tradeTime"], errors="coerce")
        ts_txt = ts.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(ts) else "-"

        text = (
            f"{ts_txt}\n"
            f"PnL cumulative: {_fmt_float(row['cum_pnl'])}\n"
            f"Trades cumulative: {_fmt_int(row['cum_trades'])}\n"
            f"PnL / Trade: {_fmt_float(row['pnl_per_trade'])}"
        )

        self._show_tooltip(event.x_root + 14, event.y_root + 14, text)

    def _on_chart_leave(self, _event=None) -> None:
        self._hide_tooltip()

    # =========================
    # Core logic
    # =========================
    def _apply_filter_and_render(self) -> None:
        if self._df is None or self._df.empty:
            self._set_empty_state()
            return

        df = self._df

        selected_cp = self.cp_var.get()
        if selected_cp != "ALL":
            df = df[df["counterparty"].fillna("").astype(str) == selected_cp]

        if df.empty:
            self._filtered_df = df.copy()
            self._table_df = pd.DataFrame(columns=["underlyingName", "PnL", "Premia", "Fees", "Trades", "PnL_per_trade"])
            self._update_kpis_empty()
            self._render_table()
            self._render_chart()
            return

        work = df.copy()

        work["tradeTime"] = pd.to_datetime(work["tradeTime"], errors="coerce")
        work["Premia"] = pd.to_numeric(work["Premia"], errors="coerce").fillna(0.0)
        work["fees"] = pd.to_numeric(work["fees"], errors="coerce").fillna(0.0)
        work["underlyingName"] = work["underlyingName"].fillna("").astype(str)

        work["pnl"] = work["Premia"] + work["fees"]
        work = work.sort_values("tradeTime", kind="mergesort").reset_index(drop=True)

        work["cum_pnl"] = work["pnl"].cumsum()
        work["cum_trades"] = np.arange(1, len(work) + 1, dtype=np.int64)
        work["pnl_per_trade"] = work["cum_pnl"] / work["cum_trades"]

        table = (
            work.groupby("underlyingName", dropna=False)
            .agg(
                PnL=("pnl", "sum"),
                Premia=("Premia", "sum"),
                Fees=("fees", "sum"),
                Trades=("pnl", "size"),
            )
            .reset_index()
        )

        table["PnL_per_trade"] = np.where(
            table["Trades"] != 0,
            table["PnL"] / table["Trades"],
            0.0,
        )

        self._filtered_df = work
        self._table_df = table

        self._update_kpis()
        self._render_table()
        self._render_chart()

    def _update_kpis(self) -> None:
        if self._filtered_df is None or self._filtered_df.empty or self._table_df is None or self._table_df.empty:
            self._update_kpis_empty()
            return

        df = self._filtered_df
        table = self._table_df

        total_pnl = float(df["pnl"].sum())
        total_premia = float(df["Premia"].sum())
        total_fees = float(df["fees"].sum())
        trades = int(len(df))
        pnl_trade = total_pnl / trades if trades else 0.0
        active_uls = int(df["underlyingName"].nunique())

        sorted_table = table.sort_values("PnL", ascending=False, kind="mergesort").reset_index(drop=True)
        best_ul = str(sorted_table.iloc[0]["underlyingName"]) if len(sorted_table) else "-"
        worst_ul = str(sorted_table.iloc[-1]["underlyingName"]) if len(sorted_table) else "-"

        self.kpi_total_pnl.set(_fmt_float(total_pnl))
        self.kpi_total_premia.set(_fmt_float(total_premia))
        self.kpi_total_fees.set(_fmt_float(total_fees))
        self.kpi_trades.set(_fmt_int(trades))
        self.kpi_pnl_trade.set(_fmt_float(pnl_trade))
        self.kpi_best_ul.set(best_ul if best_ul else "-")
        self.kpi_worst_ul.set(worst_ul if worst_ul else "-")
        self.kpi_active_uls.set(_fmt_int(active_uls))

    def _update_kpis_empty(self) -> None:
        self.kpi_total_pnl.set("0.00")
        self.kpi_total_premia.set("0.00")
        self.kpi_total_fees.set("0.00")
        self.kpi_trades.set("0")
        self.kpi_pnl_trade.set("0.00")
        self.kpi_best_ul.set("-")
        self.kpi_worst_ul.set("-")
        self.kpi_active_uls.set("0")

    def _set_empty_state(self) -> None:
        self._filtered_df = None
        self._table_df = pd.DataFrame(columns=["underlyingName", "PnL", "Premia", "Fees", "Trades", "PnL_per_trade"])
        self._update_kpis_empty()
        self._render_table()
        self._render_chart()
        self._hide_tooltip()

    # =========================
    # Table
    # =========================
    def _sort_table(self, col: str) -> None:
        if self._table_df is None or self._table_df.empty:
            return

        if self._sort_col == col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = col
            self._sort_desc = col != "underlyingName"

        self._render_table()

    def _render_table(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

        if self._table_df is None or self._table_df.empty:
            return

        table = self._table_df.copy()
        ascending = not self._sort_desc
        table = table.sort_values(self._sort_col, ascending=ascending, kind="mergesort").reset_index(drop=True)

        for i, row in table.iterrows():
            tag = "even" if i % 2 == 0 else "odd"
            self.tree.insert(
                "",
                "end",
                values=(
                    row["underlyingName"],
                    _fmt_float(row["PnL"]),
                    _fmt_float(row["Fees"]),
                    _fmt_int(row["Trades"]),
                    _fmt_float(row["PnL_per_trade"]),
                ),
                tags=(tag,),
            )

    # =========================
    # Chart
    # =========================
    def _render_chart(self) -> None:
        self.chart.delete("all")

        w = max(self.chart.winfo_width(), 10)
        h = max(self.chart.winfo_height(), 10)

        left = 58
        right = 18
        top = 18
        bottom = 42

        plot_w = max(w - left - right, 10)
        plot_h = max(h - top - bottom, 10)

        if self._filtered_df is None or self._filtered_df.empty:
            self.chart.create_text(
                w / 2,
                h / 2,
                text="No data",
                fill="#7A7A7A",
                font=("Segoe UI", 11),
            )
            return

        df = self._filtered_df

        x = np.arange(len(df), dtype=float)
        y1 = df["cum_pnl"].to_numpy(dtype=float)
        y2 = df["cum_trades"].to_numpy(dtype=float)
        y3 = df["pnl_per_trade"].to_numpy(dtype=float)

        def norm(arr: np.ndarray) -> np.ndarray:
            if len(arr) == 0:
                return np.array([], dtype=float)
            finite = arr[np.isfinite(arr)]
            if len(finite) == 0:
                return np.zeros_like(arr, dtype=float)
            amin = finite.min()
            amax = finite.max()
            if abs(amax - amin) < 1e-12:
                return np.full_like(arr, 0.5, dtype=float)
            return (arr - amin) / (amax - amin)

        xn = norm(x)
        y1n = norm(y1)
        y2n = norm(y2)
        y3n = norm(y3)

        def to_coords(xn_arr: np.ndarray, yn_arr: np.ndarray):
            pts = []
            for xx, yy in zip(xn_arr, yn_arr):
                px = left + xx * plot_w
                py = top + (1.0 - yy) * plot_h
                pts.extend([px, py])
            return pts

        self.chart.create_line(left, top, left, top + plot_h, fill="#C9D2E3", width=1)
        self.chart.create_line(left, top + plot_h, left + plot_w, top + plot_h, fill="#C9D2E3", width=1)

        for frac in (0.25, 0.50, 0.75):
            yy = top + frac * plot_h
            self.chart.create_line(left, yy, left + plot_w, yy, fill="#EEF2F8", width=1)

        pnl_vals = df["cum_pnl"].to_numpy(dtype=float)
        finite = pnl_vals[np.isfinite(pnl_vals)]
        if len(finite) > 0:
            ymin = finite.min()
            ymax = finite.max()
            if ymin < 0 < ymax and abs(ymax - ymin) > 1e-12:
                zero_norm = (0.0 - ymin) / (ymax - ymin)
                y_zero = top + (1.0 - zero_norm) * plot_h
                self.chart.create_line(
                    left,
                    y_zero,
                    left + plot_w,
                    y_zero,
                    fill="#DC2626",
                    width=2,
                    dash=(4, 2),
                )

        p1 = to_coords(xn, y1n)
        p2 = to_coords(xn, y2n)
        p3 = to_coords(xn, y3n)

        if len(p1) >= 4:
            self.chart.create_line(*p1, fill="#2563EB", width=2, smooth=False)
        if len(p2) >= 4:
            self.chart.create_line(*p2, fill="#10B981", width=2, smooth=False)
        if len(p3) >= 4:
            self.chart.create_line(*p3, fill="#F59E0B", width=2, smooth=False)

        self.chart.create_text(left, top - 8, text="Normalized", anchor="w", fill="#7A7A7A", font=("Segoe UI", 9))

        lx = left + 8
        ly = top + 8
        self._legend_item(lx, ly, "#2563EB", "PnL cumulative")
        self._legend_item(lx + 140, ly, "#10B981", "Trades cumulative")
        self._legend_item(lx + 295, ly, "#F59E0B", "PnL / Trades")
        self._legend_item(lx + 430, ly, "#DC2626", "PnL = 0")

        try:
            times = pd.to_datetime(df["tradeTime"], errors="coerce")
            valid_idx = np.where(times.notna().to_numpy())[0]

            if len(valid_idx) > 0:
                n_ticks = 4 if len(valid_idx) >= 4 else len(valid_idx)
                if n_ticks > 0:
                    pos = np.linspace(valid_idx[0], valid_idx[-1], n_ticks).astype(int)

                    used = set()
                    for i in pos:
                        i = max(0, min(len(times) - 1, i))
                        ts = times.iloc[i]
                        if pd.isna(ts):
                            continue

                        label = ts.strftime("%Y-%m-%d")
                        if label in used and len(valid_idx) > n_ticks:
                            continue
                        used.add(label)

                        x_norm = i / (len(times) - 1) if len(times) > 1 else 0.5
                        x_pos = left + x_norm * plot_w

                        self.chart.create_line(
                            x_pos,
                            top + plot_h,
                            x_pos,
                            top + plot_h + 5,
                            fill="#9CA3AF",
                            width=1,
                        )

                        self.chart.create_text(
                            x_pos,
                            top + plot_h + 16,
                            text=label,
                            anchor="n",
                            fill="#7A7A7A",
                            font=("Segoe UI", 9),
                        )
        except Exception:
            pass

    def _legend_item(self, x: float, y: float, color: str, text: str) -> None:
        self.chart.create_line(x, y, x + 18, y, fill=color, width=3)
        self.chart.create_text(x + 24, y, text=text, anchor="w", fill="#4B5563", font=("Segoe UI", 9))

    # =========================
    # Tooltip
    # =========================
    def _show_tooltip(self, x_root: int, y_root: int, text: str) -> None:
        if self._tooltip is None or not self._tooltip.winfo_exists():
            self._tooltip = tk.Toplevel(self)
            self._tooltip.wm_overrideredirect(True)
            self._tooltip.attributes("-topmost", True)

            self._tooltip_label = tk.Label(
                self._tooltip,
                text=text,
                justify="left",
                bg="#111827",
                fg="#F9FAFB",
                bd=1,
                relief="solid",
                padx=8,
                pady=6,
                font=("Segoe UI", 9),
            )
            self._tooltip_label.pack()
        else:
            if self._tooltip_label is not None:
                self._tooltip_label.config(text=text)

        self._tooltip.geometry(f"+{x_root}+{y_root}")
        self._tooltip.deiconify()

    def _hide_tooltip(self) -> None:
        if self._tooltip is not None and self._tooltip.winfo_exists():
            self._tooltip.withdraw()