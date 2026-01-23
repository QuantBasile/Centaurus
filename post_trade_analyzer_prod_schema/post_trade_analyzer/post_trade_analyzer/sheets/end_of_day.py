from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd

from ..utils.table_utils import build_display_cache, sanitize_visible_cols


# ----------------------------
# EndOfDay Sheet
# ----------------------------

class EndOfDaySheet(ttk.Frame):
    sheet_id = "eod"
    sheet_title = "EndOfDay"

    # Ajusta aquí si quieres limitar/ordenar columnas candidatas
    PNL_CANDIDATES = [
        "Total",
        "PremiaCum",
        "SpreadsCapture",
        "FullSpreadCapture",
        "PnlVonDeltaCum",
        "feesCum",
        "AufgeldCum",
    ]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df_all: Optional[pd.DataFrame] = None
        self._df_eod: Optional[pd.DataFrame] = None

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="EndOfDay", style="Title.TLabel").pack(side="left")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.nb = ttk.Notebook(inner)
        self.nb.pack(fill="both", expand=True)

        self.sub_data = EODDataSubsheet(self.nb)
        self.sub_plot = EODPlotSubsheet(self.nb, pnl_candidates=self.PNL_CANDIDATES)

        self.nb.add(self.sub_data, text="Data")
        self.nb.add(self.sub_plot, text="Plot")

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        """
        Called by app when main df is loaded.
        Builds end-of-day df: last row per (instrument, day).
        """
        self._df_all = df
        self._df_eod = self._build_eod_df(df)

        self.sub_data.set_df(self._df_eod)
        self.sub_plot.set_df(self._df_eod)

    @staticmethod
    def _build_eod_df(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        if "instrument" not in df.columns or "tradeTime" not in df.columns:
            return None

        tmp = df.copy()
        # day column (date)
        tmp["_day"] = tmp["tradeTime"].dt.date
        # sort so "last row" is last by tradeTime
        tmp.sort_values(["instrument", "_day", "tradeTime"], inplace=True, kind="mergesort")
        # last row per instrument/day
        eod = tmp.groupby(["instrument", "_day"], sort=False, as_index=False).tail(1).copy()
        # for nicer usage in plot and table
        eod.rename(columns={"_day": "day"}, inplace=True)
        eod.reset_index(drop=True, inplace=True)
        return eod


# ----------------------------
# Data subsheet: table + columns + sorting
# ----------------------------

class EODDataSubsheet(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: Optional[pd.DataFrame] = None
        self._df_view: Optional[pd.DataFrame] = None

        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

        self._visible_cols: Optional[List[str]] = None
        self._rendered_cols: List[str] = []

        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._resize_after_id: Optional[str] = None

        self._build()

    def _build(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=10, pady=(10, 8))

        ttk.Button(controls, text="Columns", command=self._open_columns_dialog_fast).pack(side="left")

        self.info_var = tk.StringVar(value="No data.")
        ttk.Label(controls, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        tcard = ttk.Frame(self, style="Card.TFrame")
        tcard.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        inner = ttk.Frame(tcard, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=10, pady=10)

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

        self.tree.bind("<Configure>", self._on_tree_configure)

    def set_df(self, df: Optional[pd.DataFrame]) -> None:
        self._df = df
        self._df_view = df
        self._sort_col = None
        self._sort_asc = True

        if df is None or df.empty:
            self.info_var.set("No rows.")
            self._clear_tree()
            self._visible_cols = None
            self._cache.clear()
            self._cache_len = 0
            return

        self.info_var.set(f"{len(df):,} end-of-day rows")

        if self._visible_cols is None:
            self._visible_cols = list(df.columns)

        self._cache, self._cache_len = build_display_cache(df)
        self._render_from_cache()

    def _render_from_cache(self) -> None:
        df = self._df_view
        if df is None or df.empty:
            self._clear_tree()
            return

        cols = sanitize_visible_cols(list(df.columns), self._visible_cols)
        self._rendered_cols = cols

        self._clear_tree()

        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c, command=lambda col=c: self._sort_by(col))
            self.tree.column(c, width=110, minwidth=80, anchor="w", stretch=True)

        cache = self._cache
        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]
            tag = "even" if (i % 2 == 0) else "odd"
            self.tree.insert("", "end", values=values, tags=(tag,))

        self._autofit_from_cache(sample_rows=min(200, self._cache_len))

    def _sort_by(self, col: str) -> None:
        df = self._df
        if df is None or df.empty:
            return

        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        view = df
        try:
            view = df.sort_values(by=col, ascending=self._sort_asc, kind="mergesort")
        except Exception:
            view = (
                df.assign(_tmp=df[col].astype("string"))
                .sort_values(by="_tmp", ascending=self._sort_asc, kind="mergesort")
                .drop(columns="_tmp")
            )

        view = view.reset_index(drop=True)
        self._df_view = view

        self._cache, self._cache_len = build_display_cache(view)
        self._render_from_cache()

    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []

    def _on_tree_configure(self, _event) -> None:
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass
        self._resize_after_id = self.after(180, lambda: self._autofit_from_cache(sample_rows=140))

    def _autofit_from_cache(self, sample_rows: int = 140) -> None:
        if not self._rendered_cols or self._cache_len == 0:
            return

        import tkinter.font as tkfont

        body_font = tkfont.nametofont("TkDefaultFont")
        heading_font = tkfont.Font(
            family=body_font.actual("family"),
            size=body_font.actual("size"),
            weight="bold",
        )

        pad = 34
        n = min(sample_rows, self._cache_len)
        cache = self._cache

        max_px: Dict[str, int] = {}
        for c in self._rendered_cols:
            max_px[c] = heading_font.measure(c) + pad

        for c in self._rendered_cols:
            col_vals = cache.get(c, [])
            for i in range(n):
                w = body_font.measure(col_vals[i]) + pad
                if w > max_px[c]:
                    max_px[c] = w

        hard_min, hard_max = 80, 520
        widths = {c: max(hard_min, min(hard_max, max_px[c])) for c in self._rendered_cols}
        for c in self._rendered_cols:
            self.tree.column(c, width=widths[c], stretch=True)

    def _open_columns_dialog_fast(self) -> None:
        df = self._df
        if df is None or df.empty:
            messagebox.showinfo("Columns", "No data to show.")
            return

        all_cols = list(df.columns)
        visible_set = set(self._visible_cols or all_cols)

        win = tk.Toplevel(self)
        win.title("Select columns")
        win.geometry("420x520")
        win.configure(bg="#F5F7FB")
        win.transient(self.winfo_toplevel())
        win.grab_set()

        header = ttk.Frame(win)
        header.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Label(header, text="Columns", style="Title.TLabel").pack(side="left")

        search_frame = ttk.Frame(win)
        search_frame.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(search_frame, text="Search", style="Muted.TLabel").pack(side="left")
        q_var = tk.StringVar()
        q_entry = ttk.Entry(search_frame, textvariable=q_var)
        q_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=12, pady=(0, 8))

        outer = ttk.Frame(win)
        outer.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        lb = tk.Listbox(outer, selectmode="extended", activestyle="none", exportselection=False, height=20)
        sb = ttk.Scrollbar(outer, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        filtered_cols: List[str] = []

        def repopulate() -> None:
            nonlocal filtered_cols
            q = q_var.get().strip().lower()
            filtered_cols = [c for c in all_cols if (q in c.lower())] if q else all_cols[:]
            lb.delete(0, "end")
            for c in filtered_cols:
                lb.insert("end", c)
            for i, c in enumerate(filtered_cols):
                if c in visible_set:
                    lb.selection_set(i)

        def select_all() -> None:
            for i in range(len(filtered_cols)):
                lb.selection_set(i)

        def select_none() -> None:
            lb.selection_clear(0, "end")

        ttk.Button(btns, text="Select all (filtered)", command=select_all).pack(side="left")
        ttk.Button(btns, text="Select none (filtered)", command=select_none).pack(side="left", padx=8)

        q_var.trace_add("write", lambda *_: repopulate())
        repopulate()

        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=12, pady=(0, 12))

        def apply_and_close() -> None:
            sel = set(filtered_cols[i] for i in lb.curselection())
            q = q_var.get().strip().lower()
            if q:
                for c in filtered_cols:
                    visible_set.discard(c)
                visible_set.update(sel)
            else:
                visible_set.clear()
                visible_set.update(sel)

            if not visible_set:
                messagebox.showwarning("Columns", "Select at least one column.")
                return

            self._visible_cols = [c for c in all_cols if c in visible_set]
            self._df_view = self._df  # reset view
            self._cache, self._cache_len = build_display_cache(self._df_view)
            self._render_from_cache()
            win.destroy()

        ttk.Button(footer, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(footer, text="Apply", style="Accent.TButton", command=apply_and_close).pack(side="right", padx=8)

        q_entry.focus_set()


# ----------------------------
# Plot subsheet: separated histogram + cumulative
# ----------------------------
class EODPlotSubsheet(ttk.Frame):
    def __init__(self, master: tk.Misc, pnl_candidates: List[str]) -> None:
        super().__init__(master)

        self._df: Optional[pd.DataFrame] = None
        self._df_inst: Optional[pd.DataFrame] = None

        self.pnl_candidates = pnl_candidates

        self.instrument_var = tk.StringVar()
        self.bar_var = tk.StringVar()
        self.normalize_var = tk.BooleanVar(value=False)

        self._redraw_after_id: Optional[str] = None

        # tooltip state (hist)
        self._hist_geom = None  # (x0, x1, y0, y1, slot)
        self._hist_days = None
        self._hist_vals = None

        self._build()

    # ------------------------------------------------------------
    # UI
    # ------------------------------------------------------------

    def _build(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        left = ttk.Frame(root, style="Card.TFrame")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        left.configure(width=340)
        left.grid_propagate(False)

        right = ttk.Frame(root, style="Card.TFrame")
        right.grid(row=0, column=1, sticky="nsew")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        pad = ttk.Frame(left, style="Card.TFrame")
        pad.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(pad, text="Instrument", style="Muted.TLabel").pack(anchor="w")
        self.instrument_cb = ttk.Combobox(pad, textvariable=self.instrument_var, state="readonly")
        self.instrument_cb.pack(fill="x", pady=(6, 12))
        self.instrument_cb.bind("<<ComboboxSelected>>", lambda e: self._apply_instrument())

        ttk.Label(pad, text="Histogram variable", style="Muted.TLabel").pack(anchor="w")
        self.bar_cb = ttk.Combobox(pad, textvariable=self.bar_var, state="readonly")
        self.bar_cb.pack(fill="x", pady=(6, 12))
        self.bar_cb.bind("<<ComboboxSelected>>", lambda e: self._schedule_redraw(1))

        ttk.Checkbutton(
            pad, text="Normalize cumulative", variable=self.normalize_var,
            command=lambda: self._schedule_redraw(1)
        ).pack(anchor="w", pady=(4, 12))

        ttk.Label(pad, text="Cumulative lines", style="Muted.TLabel").pack(anchor="w")
        self.lines_lb = tk.Listbox(
            pad, selectmode="extended", activestyle="none", exportselection=False, height=10
        )
        self.lines_lb.pack(fill="x", pady=(6, 12))

        ttk.Button(pad, text="Redraw", style="Accent.TButton", command=self.redraw).pack(anchor="w")

        # Legend under Redraw
        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=(12, 8))
        ttk.Label(pad, text="Cumulative legend", style="Muted.TLabel").pack(anchor="w", pady=(0, 4))
        self.legend_frame = ttk.Frame(pad)
        self.legend_frame.pack(fill="x")

        # Plots
        right.rowconfigure(0, weight=2)  # histogram
        right.rowconfigure(1, weight=3)  # cumulative
        right.columnconfigure(0, weight=1)

        self.canvas_hist = tk.Canvas(right, bg="#FFFFFF", highlightthickness=0)
        self.canvas_hist.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))

        self.canvas_cum = tk.Canvas(right, bg="#FFFFFF", highlightthickness=0)
        self.canvas_cum.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        # Tooltip (single lightweight label)
        self.tooltip = ttk.Label(
            self.canvas_hist,
            background="#0F172A",
            foreground="white",
            padding=(6, 3),
            font=("Segoe UI", 9),
        )
        self.tooltip.place_forget()

        self.canvas_hist.bind("<Motion>", self._on_hist_motion)
        self.canvas_hist.bind("<Leave>", lambda e: self.tooltip.place_forget())

        self.canvas_hist.bind("<Configure>", lambda e: self._schedule_redraw(120))
        self.canvas_cum.bind("<Configure>", lambda e: self._schedule_redraw(120))

    # ------------------------------------------------------------
    # Data
    # ------------------------------------------------------------

    def set_df(self, df: Optional[pd.DataFrame]) -> None:
        self._df = df
        if df is None or df.empty:
            return

        inst = sorted([x for x in df["instrument"].dropna().astype("string").unique().tolist() if x])
        self.instrument_cb["values"] = inst
        self.instrument_var.set(inst[0] if inst else "")

        bars = [c for c in self.pnl_candidates if c in df.columns]
        if not bars:
            bars = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])][:10]

        self.bar_cb["values"] = bars
        self.bar_var.set(bars[0] if bars else "")

        self.lines_lb.delete(0, "end")
        for c in bars:
            self.lines_lb.insert("end", c)
        if bars:
            self.lines_lb.selection_set(0)

        self._apply_instrument()

    def _apply_instrument(self) -> None:
        df = self._df
        if df is None or df.empty:
            self._df_inst = None
            self.redraw()
            return

        inst = self.instrument_var.get().strip()
        sub = df[df["instrument"].astype("string") == inst].copy()
        sub.sort_values("day", inplace=True, kind="mergesort")
        self._df_inst = sub.reset_index(drop=True)
        self.redraw()

    # ------------------------------------------------------------
    # Redraw (debounced)
    # ------------------------------------------------------------

    def _schedule_redraw(self, delay_ms: int) -> None:
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except Exception:
                pass
        self._redraw_after_id = self.after(delay_ms, self.redraw)

    def redraw(self) -> None:
        self._redraw_after_id = None
        self.canvas_hist.delete("all")
        self.canvas_cum.delete("all")
        for w in self.legend_frame.winfo_children():
            w.destroy()

        df = self._df_inst
        if df is None or df.empty:
            self._draw_empty(self.canvas_hist, "No data.")
            self._draw_empty(self.canvas_cum, "No data.")
            return

        days = df["day"].tolist()
        bar_col = self.bar_var.get().strip()
        if bar_col not in df.columns:
            self._draw_empty(self.canvas_hist, "Missing histogram column.")
            self._draw_empty(self.canvas_cum, "Select cumulative lines.")
            return

        bars = pd.to_numeric(df[bar_col], errors="coerce").fillna(0.0)

        self._draw_histogram(days, bars, title=f"Daily {bar_col}")

        sel = [self.lines_lb.get(i) for i in self.lines_lb.curselection()]
        sel = [c for c in sel if c in df.columns]
        self._draw_cumulative(days, df, sel)

    # ------------------------------------------------------------
    # Drawing utilities
    # ------------------------------------------------------------

    def _draw_empty(self, canvas: tk.Canvas, msg: str) -> None:
        W = max(300, canvas.winfo_width())
        H = max(200, canvas.winfo_height())
        canvas.create_text(W / 2, H / 2, text=msg, fill="#5E6B85", font=("Segoe UI", 11))

    def _draw_x_labels(self, canvas: tk.Canvas, days, x0, x1, y1) -> None:
        n = len(days)
        if n <= 1:
            return
        step = max(1, n // 8)  # max ~9 labels
        for i in range(0, n, step):
            xx = x0 + (i + 0.5) * (x1 - x0) / n
            canvas.create_text(xx, y1 + 18, text=str(days[i]), fill="#64748B", anchor="n", font=("Segoe UI", 9))

    def _nice_ticks(self, ymin: float, ymax: float, n: int = 5) -> List[float]:
        if ymin == ymax:
            return [ymin + i for i in range(n)]
        return [ymin + (ymax - ymin) * (i / (n - 1)) for i in range(n)]

    # ------------------------------------------------------------
    # Histogram (with grid, axes, best/worst + tooltip support)
    # ------------------------------------------------------------

    def _draw_histogram(self, days, vals: pd.Series, title: str) -> None:
        c = self.canvas_hist
        W, H = max(600, c.winfo_width()), max(220, c.winfo_height())
        left, right, top, bottom = 80, 20, 30, 55
        x0, y0, x1, y1 = left, top, W - right, H - bottom

        vmin = float(vals.min())
        vmax = float(vals.max())
        pad = 0.15 * max(1.0, vmax - vmin)
        ymin = vmin - pad
        ymax = vmax + pad

        def y(v: float) -> float:
            return y1 - (v - ymin) / (ymax - ymin) * (y1 - y0)

        c.create_rectangle(x0, y0, x1, y1, outline="#D8E1F0")

        # grid + y ticks
        ticks = self._nice_ticks(ymin, ymax, 5)
        for t in ticks:
            yy = y(float(t))
            c.create_line(x0, yy, x1, yy, fill="#F3F6FF")
            c.create_text(x0 - 8, yy, text=f"{t:,.0f}", anchor="e", fill="#64748B", font=("Segoe UI", 9))

        # zero line
        if ymin < 0 < ymax:
            c.create_line(x0, y(0.0), x1, y(0.0), fill="#CBD5F5", width=2)

        n = len(vals)
        slot = (x1 - x0) / max(1, n)
        bw = slot * 0.62

        # bars
        for i, v in enumerate(vals.tolist()):
            xc = x0 + (i + 0.5) * slot
            if v >= 0:
                c.create_rectangle(xc - bw/2, y(v), xc + bw/2, y(0.0), fill="#22C55E", outline="")
            else:
                c.create_rectangle(xc - bw/2, y(0.0), xc + bw/2, y(v), fill="#EF4444", outline="")

        # best / worst annotations
        best_i = int(vals.idxmax())
        worst_i = int(vals.idxmin())
        best_v = float(vals.iloc[best_i])
        worst_v = float(vals.iloc[worst_i])

        def x_center(i: int) -> float:
            return x0 + (i + 0.5) * slot

        c.create_text(
            x_center(best_i), y(best_v) - 10,
            text=f"Best: {best_v:,.0f}",
            fill="#15803D", font=("Segoe UI Semibold", 9), anchor="s"
        )
        c.create_text(
            x_center(worst_i), y(worst_v) + 10,
            text=f"Worst: {worst_v:,.0f}",
            fill="#B91C1C", font=("Segoe UI Semibold", 9), anchor="n"
        )

        # x labels (days)
        self._draw_x_labels(c, days, x0, x1, y1)

        # title
        c.create_text(x0, y0 - 10, text=title, anchor="w", fill="#0B1220", font=("Segoe UI Semibold", 10))

        # store geometry for tooltip
        self._hist_geom = (x0, x1, y0, y1, slot)
        self._hist_days = days
        self._hist_vals = vals

    def _on_hist_motion(self, event) -> None:
        if not self._hist_geom or self._hist_days is None or self._hist_vals is None:
            return

        x0, x1, y0, y1, slot = self._hist_geom
        if not (x0 <= event.x <= x1 and y0 <= event.y <= y1):
            self.tooltip.place_forget()
            return

        idx = int((event.x - x0) // slot)
        if idx < 0 or idx >= len(self._hist_days):
            self.tooltip.place_forget()
            return

        d = self._hist_days[idx]
        v = float(self._hist_vals.iloc[idx])
        self.tooltip.config(text=f"{d}\nPnL: {v:,.0f}")
        self.tooltip.place(x=event.x + 12, y=event.y - 28)

    # ------------------------------------------------------------
    # Cumulative (grid, axes, weekly separators, drawdown shading, legend)
    # ------------------------------------------------------------

    def _draw_cumulative(self, days, df: pd.DataFrame, cols: List[str]) -> None:
        c = self.canvas_cum
        if not cols:
            self._draw_empty(c, "Select at least one line.")
            return

        W, H = max(600, c.winfo_width()), max(260, c.winfo_height())
        left, right, top, bottom = 80, 20, 30, 55
        x0, y0, x1, y1 = left, top, W - right, H - bottom

        palette = ["#2563EB", "#7C3AED", "#0891B2", "#EA580C", "#0EA5E9", "#A855F7"]

        series = []
        for col in cols:
            s = pd.to_numeric(df[col], errors="coerce").fillna(0.0).cumsum()
            if self.normalize_var.get():
                base = float(abs(s.iloc[0])) if len(s) else 1.0
                if base == 0.0:
                    base = 1.0
                s = s / base
            series.append((col, s))

        allv = pd.concat([s for _, s in series], axis=0)
        vmin = float(allv.min())
        vmax = float(allv.max())
        pad = 0.15 * max(1.0, vmax - vmin)
        ymin = vmin - pad
        ymax = vmax + pad

        def y(v: float) -> float:
            return y1 - (v - ymin) / (ymax - ymin) * (y1 - y0)

        n = len(days)
        if n <= 0:
            self._draw_empty(c, "No days.")
            return

        def x_center(i: int) -> float:
            return x0 + (i + 0.5) * (x1 - x0) / n

        c.create_rectangle(x0, y0, x1, y1, outline="#D8E1F0")

        # grid + y ticks
        ticks = self._nice_ticks(ymin, ymax, 5)
        for t in ticks:
            yy = y(float(t))
            c.create_line(x0, yy, x1, yy, fill="#F3F6FF")
            c.create_text(x0 - 8, yy, text=f"{t:,.2f}", anchor="e", fill="#64748B", font=("Segoe UI", 9))

        # zero line
        if ymin < 0 < ymax:
            c.create_line(x0, y(0.0), x1, y(0.0), fill="#CBD5F5", width=2)

        # weekly separators (Mondays)
        for i, d in enumerate(days):
            if isinstance(d, date) and d.weekday() == 0:
                xx = x_center(i)
                c.create_line(xx, y0, xx, y1, fill="#E5E7EB")

        # drawdown shading for first selected series (cheap + useful)
        base_name, base_s = series[0]
        run_max = base_s.cummax()
        pts = []
        for i in range(n):
            pts.append((x_center(i), y(float(run_max.iloc[i]))))
        for i in reversed(range(n)):
            pts.append((x_center(i), y(float(base_s.iloc[i]))))
        flat = [p for xy in pts for p in xy]
        if len(flat) >= 6:
            c.create_polygon(*flat, fill="#FEE2E2", outline="", stipple="gray12")

        # draw lines + max/min annotation per first line
        for k, (name, s) in enumerate(series):
            col = palette[k % len(palette)]
            pts = []
            for i in range(n):
                pts.extend([x_center(i), y(float(s.iloc[i]))])
            if len(pts) >= 4:
                c.create_line(*pts, fill=col, width=2)

            # legend row (left column)
            row = ttk.Frame(self.legend_frame)
            row.pack(anchor="w", pady=2)
            sw = tk.Canvas(row, width=16, height=10, highlightthickness=0)
            sw.create_line(0, 5, 16, 5, fill=col, width=3)
            sw.pack(side="left", padx=(0, 6))
            ttk.Label(row, text=name).pack(side="left")

        # annotate max/min for first line (clean)
        max_i = int(base_s.idxmax())
        min_i = int(base_s.idxmin())
        max_v = float(base_s.iloc[max_i])
        min_v = float(base_s.iloc[min_i])
        c.create_text(
            x_center(max_i), y(max_v) - 10,
            text=f"Max: {max_v:,.2f}",
            fill="#1D4ED8", font=("Segoe UI Semibold", 9), anchor="s"
        )
        c.create_text(
            x_center(min_i), y(min_v) + 10,
            text=f"Min: {min_v:,.2f}",
            fill="#7C3AED", font=("Segoe UI Semibold", 9), anchor="n"
        )

        # x labels (days)
        self._draw_x_labels(c, days, x0, x1, y1)

        # title
        c.create_text(x0, y0 - 10, text="Cumulative PnL", anchor="w", fill="#0B1220",
                      font=("Segoe UI Semibold", 10))
