from __future__ import annotations

from datetime import date, datetime, time
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd

from ..utils.table_utils import build_display_cache, sanitize_visible_cols
from ..utils.time_utils import parse_iso_date, us_open_berlin


class BaseSheet(ttk.Frame):
    sheet_id: str = "base"
    sheet_title: str = "Base"

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        pass


class InstrumentDaySheet(BaseSheet):
    sheet_id = "instday"
    sheet_title = "Instrument • Day"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._df_all: Optional[pd.DataFrame] = None
        self._df_base: Optional[pd.DataFrame] = None

        self.instrument_var = tk.StringVar()
        self.date_var = tk.StringVar()

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))
        ttk.Label(top, text="Instrument • Day", style="Title.TLabel").pack(side="left")

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=14, pady=(0, 10))

        ttk.Label(controls, text="Instrument", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        self.instrument_cb = ttk.Combobox(
            controls, textvariable=self.instrument_var, state="readonly", width=18
        )
        self.instrument_cb.grid(row=1, column=0, sticky="w", padx=(0, 14))

        ttk.Label(controls, text="Date (YYYY-MM-DD)", style="Muted.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 8)
        )
        self.date_entry = ttk.Entry(controls, textvariable=self.date_var, width=12)
        self.date_entry.grid(row=1, column=1, sticky="w", padx=(0, 14))

        self.apply_btn = ttk.Button(
            controls, text="Apply", style="Accent.TButton", command=self._apply_base_filter
        )
        self.apply_btn.grid(row=1, column=2, sticky="w")

        self.info_var = tk.StringVar(value="Load data to begin.")
        ttk.Label(controls, textvariable=self.info_var, style="Muted.TLabel").grid(
            row=1, column=3, sticky="w", padx=(14, 0)
        )
        controls.columnconfigure(3, weight=1)

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.nb = ttk.Notebook(inner)
        self.nb.pack(fill="both", expand=True)

        self.sub_data = InstDayDataSubsheet(self.nb)
        self.sub_plot = InstDayPlotSubsheet(self.nb)

        self.nb.add(self.sub_data, text="Data")
        self.nb.add(self.sub_plot, text="Plot")

        # Apply only when pressing Apply (or Enter on date)
        self.date_entry.bind("<Return>", lambda e: self._apply_base_filter())
        self.instrument_cb.bind("<<ComboboxSelected>>", lambda e: None)

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        self._df_all = df

        inst = sorted([x for x in df["instrument"].dropna().astype("string").unique().tolist() if x])
        if not inst:
            inst = ["(none)"]
        self.instrument_cb["values"] = inst
        if not self.instrument_var.get() or self.instrument_var.get() not in inst:
            self.instrument_var.set(inst[0])

        if len(df) > 0 and not self.date_var.get():
            self.date_var.set(pd.Timestamp(df["tradeTime"].iloc[0]).date().isoformat())

        self._apply_base_filter()

    def _apply_base_filter(self) -> None:
        df = self._df_all
        if df is None or df.empty:
            self.info_var.set("No data loaded.")
            self.sub_data.set_df(None)
            self.sub_plot.set_df(None)
            return

        inst = self.instrument_var.get().strip()
        try:
            d = parse_iso_date(self.date_var.get())
        except ValueError:
            self.info_var.set("Invalid date format. Use YYYY-MM-DD.")
            return

        base = df[df["instrument"].astype("string") == inst].copy()
        base = base[base["tradeTime"].dt.date == d].copy()
        base.sort_values("tradeTime", inplace=True, kind="mergesort")
        base.reset_index(drop=True, inplace=True)

        self._df_base = base
        self.info_var.set(f"{inst} • {d.isoformat()} • {len(base):,} rows")

        self.sub_data.set_df(base)
        self.sub_plot.set_df(base, day=d)


class InstDayDataSubsheet(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._sort_col: Optional[str] = None
        self._sort_asc: bool = True

        self._df_base: Optional[pd.DataFrame] = None
        self._df_view: Optional[pd.DataFrame] = None

        self._visible_cols: Optional[List[str]] = None
        self._rendered_cols: List[str] = []

        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self.bool_vars: Dict[str, tk.StringVar] = {}
        self._bool_widgets: List[ttk.Combobox] = []

        self._resize_after_id: Optional[str] = None
        self._build()

    def _build(self) -> None:
        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=10, pady=(10, 8))

        self.columns_btn = ttk.Button(controls, text="Columns", command=self._open_columns_dialog_fast)
        self.columns_btn.pack(side="left")

        self.apply_filters_btn = ttk.Button(
            controls, text="Apply filters", style="Accent.TButton", command=self._apply_filters
        )
        self.apply_filters_btn.pack(side="left", padx=8)

        self.info_var = tk.StringVar(value="No data.")
        ttk.Label(controls, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        # Filters card (ONLY booleans)
        fcard = ttk.Frame(self, style="Card.TFrame")
        fcard.pack(fill="x", padx=10, pady=(0, 10))
        fpad = ttk.Frame(fcard, style="Card.TFrame")
        fpad.pack(fill="x", padx=10, pady=10)

        ttk.Label(fpad, text="Filters", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        self.bool_frame = ttk.Frame(fpad, style="Card.TFrame")
        self.bool_frame.grid(row=1, column=0, sticky="w")
        ttk.Label(self.bool_frame, text="Booleans", style="CardBody.TLabel").grid(
            row=0, column=0, columnspan=10, sticky="w", pady=(0, 4)
        )

        # Table card
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
        self._df_base = df
        self._df_view = df
        self._sort_col = None
        self._sort_asc = True

        if df is None or df.empty:
            self.info_var.set("No rows.")
            self._clear_tree()
            self._build_bool_filters([])
            self._visible_cols = None
            self._cache.clear()
            self._cache_len = 0
            return

        bool_cols = [c for c in df.columns if c.startswith("flag_")]
        self._build_bool_filters(bool_cols)

        if self._visible_cols is None:
            self._visible_cols = list(df.columns)

        self._apply_filters()

    def _build_bool_filters(self, bool_cols: List[str]) -> None:
        for w in self._bool_widgets:
            w.destroy()
        self._bool_widgets.clear()
        self.bool_vars.clear()

        options = ["All", "True", "False"]
        per_row = 5

        for i, col in enumerate(bool_cols):
            r = 1 + (i // per_row) * 2
            c = (i % per_row) * 2

            ttk.Label(self.bool_frame, text=col, style="CardBody.TLabel").grid(
                row=r, column=c, sticky="w", padx=(0, 6)
            )
            v = tk.StringVar(value="All")
            self.bool_vars[col] = v
            cb = ttk.Combobox(
                self.bool_frame, textvariable=v, values=options, state="readonly", width=6
            )
            cb.grid(row=r, column=c + 1, sticky="w", padx=(0, 10), pady=(0, 4))
            self._bool_widgets.append(cb)

    def _apply_filters(self) -> None:
        df = self._df_base
        if df is None or df.empty:
            self._df_view = df
            self._clear_tree()
            self.info_var.set("No rows.")
            return

        view = df
        for col, v in self.bool_vars.items():
            if v.get() == "True":
                view = view[view[col] == True]  # noqa: E712
            elif v.get() == "False":
                view = view[view[col] == False]  # noqa: E712

        self._df_view = view.reset_index(drop=True)
        self.info_var.set(f"Showing {len(self._df_view):,} rows (after filters).")

        self._cache, self._cache_len = build_display_cache(self._df_view)
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
        df = self._df_view
        if df is None or df.empty:
            return

        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = True

        try:
            self._df_view = df.sort_values(by=col, ascending=self._sort_asc, kind="mergesort").reset_index(drop=True)
        except Exception:
            self._df_view = (
                df.assign(_tmp=df[col].astype("string"))
                .sort_values(by="_tmp", ascending=self._sort_asc, kind="mergesort")
                .drop(columns="_tmp")
                .reset_index(drop=True)
            )

        self._cache, self._cache_len = build_display_cache(self._df_view)
        self._render_from_cache()

    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []

    def _on_tree_configure(self, _event) -> None:
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
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

        try:
            available = max(500, self.tree.winfo_width() - 20)
        except Exception:
            available = 900

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

        total = sum(widths.values())
        if total > available * 1.2:
            for c in self._rendered_cols:
                if c.startswith("flag_"):
                    widths[c] = max(hard_min, min(widths[c], 80))

        for c in self._rendered_cols:
            self.tree.column(c, width=widths[c], stretch=True)

    def _open_columns_dialog_fast(self) -> None:
        df = self._df_view
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
            self._render_from_cache()
            win.destroy()

        ttk.Button(footer, text="Cancel", command=win.destroy).pack(side="right")
        ttk.Button(footer, text="Apply", style="Accent.TButton", command=apply_and_close).pack(side="right", padx=8)

        q_entry.focus_set()


class InstDayPlotSubsheet(ttk.Frame):
    """
    Simple, fast plotting:
    - left sidebar for selection + legend
    - select all / none for PnL & Delta
    - simple zoom: drag horizontally in main plot; double-click resets
    - minimal debounce on resize to avoid stutter
    """

    PNL_CANDIDATES = [
        "Total",
        "PremiaCum",
        "SpreadsCapture",
        "FullSpreadCapture",
        "PnlVonDeltaCum",
        "feesCum",
        "AufgeldCum",
    ]

    DELTA_CANDIDATES = [
        "CumDelta",
        "CumDelta_stock",
        "CumDelta_certificates_abandon",
        "CumDelta_our_abandon",
        "CumDelta_external_abandon",
        "CumDelta_our_scheine",
        "CumDelta_external_scheine",
    ]

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._df: Optional[pd.DataFrame] = None
        self._day: Optional[date] = None

        # zoom window (absolute timestamps). None => full 08:00-22:00
        self._zoom: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None

        # drag state (zoom)
        self._dragging = False
        self._drag_x0: Optional[int] = None
        self._drag_rect_main: Optional[int] = None

        # debounce redraw for resize
        self._redraw_after_id: Optional[str] = None

        self._last_legend_items: List[Tuple[str, str, str]] = []
        self._build()

    def _build(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=10, pady=10)

        self.left = ttk.Frame(root, style="Card.TFrame")
        self.left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self.left.configure(width=320)
        self.left.grid_propagate(False)

        self.right = ttk.Frame(root, style="Card.TFrame")
        self.right.grid(row=0, column=1, sticky="nsew")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        pad = ttk.Frame(self.left, style="Card.TFrame")
        pad.pack(fill="both", expand=True, padx=12, pady=12)

        # PnL block + buttons
        pnl_header = ttk.Frame(pad, style="Card.TFrame")
        pnl_header.pack(fill="x")
        ttk.Label(pnl_header, text="PnL lines", style="Muted.TLabel").pack(side="left")
        ttk.Button(pnl_header, text="All", width=6, command=self._pnl_select_all).pack(side="right")
        ttk.Button(pnl_header, text="None", width=6, command=self._pnl_select_none).pack(side="right", padx=(0, 6))

        self.pnl_lb = tk.Listbox(
            pad, selectmode="extended", activestyle="none", exportselection=False, height=8
        )
        self.pnl_lb.pack(fill="x", pady=(6, 12))

        # Delta block + buttons
        d_header = ttk.Frame(pad, style="Card.TFrame")
        d_header.pack(fill="x")
        ttk.Label(d_header, text="Delta lines", style="Muted.TLabel").pack(side="left")
        ttk.Button(d_header, text="All", width=6, command=self._delta_select_all).pack(side="right")
        ttk.Button(d_header, text="None", width=6, command=self._delta_select_none).pack(side="right", padx=(0, 6))

        self.delta_lb = tk.Listbox(
            pad, selectmode="extended", activestyle="none", exportselection=False, height=8
        )
        self.delta_lb.pack(fill="x", pady=(6, 12))

        btn_row = ttk.Frame(pad, style="Card.TFrame")
        btn_row.pack(fill="x", pady=(4, 10))

        ttk.Button(btn_row, text="Reset zoom", command=self._reset_zoom).pack(side="left")
        self.redraw_btn = ttk.Button(btn_row, text="Redraw", style="Accent.TButton", command=self.redraw)
        self.redraw_btn.pack(side="left", padx=(8, 0))

        ttk.Separator(pad, orient="horizontal").pack(fill="x", pady=(10, 10))
        ttk.Label(pad, text="Legend", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 6))

        self.legend = tk.Canvas(pad, highlightthickness=0, bg="#FFFFFF")
        self.legend.pack(fill="both", expand=True)

        # Right plots
        self.right.rowconfigure(0, weight=2)
        self.right.rowconfigure(1, weight=5)
        self.right.columnconfigure(0, weight=1)

        spot_wrap = ttk.Frame(self.right, style="Card.TFrame")
        spot_wrap.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        self.canvas_spot = tk.Canvas(spot_wrap, highlightthickness=0, bg="#FFFFFF")
        self.canvas_spot.pack(fill="both", expand=True)

        main_wrap = ttk.Frame(self.right, style="Card.TFrame")
        main_wrap.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.canvas_main = tk.Canvas(main_wrap, highlightthickness=0, bg="#FFFFFF")
        self.canvas_main.pack(fill="both", expand=True)

        # debounced redraw on resize
        self.canvas_spot.bind("<Configure>", lambda e: self._schedule_redraw(120))
        self.canvas_main.bind("<Configure>", lambda e: self._schedule_redraw(120))
        self.legend.bind("<Configure>", lambda e: self._schedule_redraw(160))

        # simple zoom: drag on main plot only
        self.canvas_main.bind("<ButtonPress-1>", self._zoom_drag_start)
        self.canvas_main.bind("<B1-Motion>", self._zoom_drag_move)
        self.canvas_main.bind("<ButtonRelease-1>", self._zoom_drag_end)
        self.canvas_main.bind("<Double-Button-1>", lambda e: self._reset_zoom())

    # ---------- listbox helpers ----------
    def _pnl_select_all(self) -> None:
        self.pnl_lb.selection_set(0, "end")

    def _pnl_select_none(self) -> None:
        self.pnl_lb.selection_clear(0, "end")

    def _delta_select_all(self) -> None:
        self.delta_lb.selection_set(0, "end")

    def _delta_select_none(self) -> None:
        self.delta_lb.selection_clear(0, "end")

    # ---------- debounce ----------
    def _schedule_redraw(self, delay_ms: int = 120) -> None:
        if self._redraw_after_id is not None:
            try:
                self.after_cancel(self._redraw_after_id)
            except Exception:
                pass
        self._redraw_after_id = self.after(delay_ms, self._do_redraw)

    def _do_redraw(self) -> None:
        self._redraw_after_id = None
        self.redraw()

    # ---------- zoom ----------
    def _reset_zoom(self) -> None:
        self._zoom = None
        self._clear_zoom_rect()
        self.redraw()

    def _clear_zoom_rect(self) -> None:
        if self._drag_rect_main is not None:
            try:
                self.canvas_main.delete(self._drag_rect_main)
            except Exception:
                pass
        self._drag_rect_main = None

    def _zoom_drag_start(self, event) -> None:
        self._dragging = True
        self._drag_x0 = int(event.x)
        self._clear_zoom_rect()
        self._drag_rect_main = self.canvas_main.create_rectangle(
            event.x, 0, event.x, self.canvas_main.winfo_height(),
            outline="#2E7BFF", width=1, fill="#2E7BFF", stipple="gray12"
        )

    def _zoom_drag_move(self, event) -> None:
        if not self._dragging or self._drag_x0 is None or self._drag_rect_main is None:
            return
        self.canvas_main.coords(
            self._drag_rect_main,
            self._drag_x0, 0, int(event.x), self.canvas_main.winfo_height()
        )

    def _zoom_drag_end(self, event) -> None:
        if not self._dragging or self._drag_x0 is None:
            self._clear_zoom_rect()
            return

        self._dragging = False
        x0 = self._drag_x0
        x1 = int(event.x)
        self._drag_x0 = None

        if abs(x1 - x0) < 12:
            self._clear_zoom_rect()
            return

        df = self._df
        day = self._day
        if df is None or df.empty or day is None:
            self._clear_zoom_rect()
            return

        # plot geometry must match _draw_main_plot()
        w = max(520, self.canvas_main.winfo_width())
        left, right = 70, 70
        px0 = left
        px1 = w - right
        if px1 <= px0 + 5:
            self._clear_zoom_rect()
            return

        a = max(px0, min(px1, min(x0, x1)))
        b = max(px0, min(px1, max(x0, x1)))
        if b <= a:
            self._clear_zoom_rect()
            return

        start_dt_full = datetime.combine(day, time(8, 0, 0))
        end_dt_full = datetime.combine(day, time(22, 0, 0))
        total_sec = (end_dt_full - start_dt_full).total_seconds()

        s0 = (a - px0) / (px1 - px0) * total_sec
        s1 = (b - px0) / (px1 - px0) * total_sec
        if s1 - s0 < 60:
            self._clear_zoom_rect()
            return

        z0 = pd.Timestamp(start_dt_full) + pd.Timedelta(seconds=s0)
        z1 = pd.Timestamp(start_dt_full) + pd.Timedelta(seconds=s1)
        self._zoom = (z0, z1)

        self._clear_zoom_rect()
        self.redraw()

    # ---------- data ----------
    def set_df(self, df: Optional[pd.DataFrame], day: Optional[date] = None) -> None:
        self._df = df
        self._day = day
        self._zoom = None

        self.pnl_lb.delete(0, "end")
        self.delta_lb.delete(0, "end")

        pnl_series = [c for c in self.PNL_CANDIDATES if df is not None and c in df.columns]
        delta_series = [c for c in self.DELTA_CANDIDATES if df is not None and c in df.columns]

        for s in pnl_series:
            self.pnl_lb.insert("end", s)
        for s in delta_series:
            self.delta_lb.insert("end", s)

        # default select first (light)
        if pnl_series:
            self.pnl_lb.selection_set(0)
        if delta_series:
            self.delta_lb.selection_set(0)

        self.redraw()

    # ---------- render ----------
    def redraw(self) -> None:
        self.canvas_spot.delete("all")
        self.canvas_main.delete("all")
        self.legend.delete("all")
        self._last_legend_items = []

        df = self._df
        day = self._day
        if df is None or df.empty or day is None:
            self._draw_empty(self.canvas_spot, "No data to plot.")
            self._draw_empty(self.canvas_main, "No data to plot.")
            return

        pnl_cols = [self.pnl_lb.get(i) for i in self.pnl_lb.curselection()]
        delta_cols = [self.delta_lb.get(i) for i in self.delta_lb.curselection()]

        self._draw_spot_plot(df, day)

        if not pnl_cols and not delta_cols:
            self._draw_empty(self.canvas_main, "Select at least one line.")
            return

        legend_items = self._draw_main_plot(df, day, pnl_cols, delta_cols)
        self._last_legend_items = legend_items
        self._draw_legend_sidebar(legend_items)

    # ---------- helpers ----------
    def _draw_empty(self, canvas: tk.Canvas, msg: str) -> None:
        w = max(300, canvas.winfo_width())
        h = max(200, canvas.winfo_height())
        canvas.create_text(w / 2, h / 2, text=msg, fill="#5E6B85", font=("Segoe UI", 11))

    def _draw_legend_sidebar(self, legend_items: List[Tuple[str, str, str]]) -> None:
        c = self.legend
        c.delete("all")
        w = max(260, c.winfo_width())
        h = max(160, c.winfo_height())

        if not legend_items:
            c.create_text(12, 18, text="(No lines)", anchor="w", fill="#5E6B85", font=("Segoe UI", 10))
            return

        box_h = min(h - 12, 16 + 20 * len(legend_items))
        c.create_rectangle(6, 6, w - 6, 6 + box_h, outline="#D8E1F0", fill="#FFFFFF")

        y = 18
        for col, label, grp in legend_items:
            c.create_line(16, y, 44, y, fill=col, width=3)
            c.create_text(54, y, text=f"{label} ({grp})", anchor="w", fill="#0B1220", font=("Segoe UI", 10))
            y += 20

    def _get_window(self, day: date) -> Tuple[pd.Timestamp, pd.Timestamp]:
        full_start = pd.Timestamp(datetime.combine(day, time(8, 0, 0)))
        full_end = pd.Timestamp(datetime.combine(day, time(22, 0, 0)))
        if self._zoom is None:
            return full_start, full_end
        z0, z1 = self._zoom
        # clamp to full window
        z0 = max(full_start, min(full_end, z0))
        z1 = max(full_start, min(full_end, z1))
        if z1 <= z0:
            return full_start, full_end
        return z0, z1

    def _draw_spot_plot(self, df: pd.DataFrame, day: date) -> None:
        c = self.canvas_spot
        w = max(420, c.winfo_width())
        h = max(120, c.winfo_height())

        left, right, top, bottom = 70, 20, 22, 40
        x0, y0 = left, top
        x1, y1 = w - right, h - bottom

        start_dt, end_dt = self._get_window(day)
        total_sec = (end_dt - start_dt).total_seconds()
        if total_sec <= 0:
            self._draw_empty(c, "Bad zoom window.")
            return

        if "tradeUnderlyingSpotRef" not in df.columns:
            self._draw_empty(c, "Missing tradeUnderlyingSpotRef.")
            return

        t = df["tradeTime"]
        mask = (t >= start_dt) & (t <= end_dt)
        sub = df.loc[mask, ["tradeTime", "tradeUnderlyingSpotRef"]].copy()
        if sub.empty:
            self._draw_empty(c, "No trades in window.")
            return

        sub.sort_values("tradeTime", inplace=True, kind="mergesort")
        secs = (sub["tradeTime"] - start_dt).dt.total_seconds().astype("float64")
        yvals = pd.to_numeric(sub["tradeUnderlyingSpotRef"], errors="coerce").astype("float64")
        yclean = yvals.dropna()
        if yclean.empty:
            self._draw_empty(c, "No spot data.")
            return

        ymin, ymax = float(yclean.min()), float(yclean.max())
        if ymin == ymax:
            ymin -= 1.0
            ymax += 1.0
        pad = 0.06 * (ymax - ymin)
        ymin -= pad
        ymax += pad
        
        # y-axis labels (left)
        for i in range(5):
            frac = i / 4
            yy = y1 - frac * (y1 - y0)
            v = ymin + frac * (ymax - ymin)
            c.create_text(
                x0 - 8,
                yy,
                text=f"{v:,.2f}",
                anchor="e",
                fill="#5E6B85",
                font=("Segoe UI", 9),
            )


        def x_map(s: float) -> float:
            return x0 + (s / total_sec) * (x1 - x0)

        def y_map(v: float) -> float:
            return y1 - ((v - ymin) / (ymax - ymin)) * (y1 - y0)

        c.create_rectangle(x0, y0, x1, y1, outline="#D8E1F0", width=1)

        # light grid: 6 vertical divisions
        for i in range(7):
            xx = x0 + i * (x1 - x0) / 6
            c.create_line(xx, y0, xx, y1, fill="#EEF3FF")
        # x-axis labels (08:00 to 22:00, or zoomed window)
        # Put labels under the plot frame
        n_ticks = 6  # same as grid divisions
        for i in range(n_ticks + 1):
            xx = x0 + i * (x1 - x0) / n_ticks
            frac = i / n_ticks
            t_tick = start_dt + pd.Timedelta(seconds=frac * total_sec)
            c.create_text(
                xx,
                y1 + 16,
                text=t_tick.strftime("%H:%M"),
                fill="#5E6B85",
                font=("Segoe UI", 9),
                anchor="n",
            )
            
        for i in range(4):
            yy = y0 + i * (y1 - y0) / 3
            c.create_line(x0, yy, x1, yy, fill="#F3F6FF")

        vals = pd.to_numeric(sub["tradeUnderlyingSpotRef"], errors="coerce").ffill().bfill()
        pts: List[float] = []
        for ss, vv in zip(secs.tolist(), vals.tolist()):
            pts.extend([x_map(float(ss)), y_map(float(vv))])
        if len(pts) >= 4:
            c.create_line(*pts, fill="#2E7BFF", width=2)

        c.create_text(
            x0,
            y0 - 10,
            text="Underlying Spot Ref",
            anchor="w",
            fill="#0B1220",
            font=("Segoe UI Semibold", 10),
        )

    def _draw_main_plot(
        self,
        df: pd.DataFrame,
        day: date,
        pnl_cols: List[str],
        delta_cols: List[str],
    ) -> List[Tuple[str, str, str]]:
        c = self.canvas_main
        w = max(520, c.winfo_width())
        h = max(280, c.winfo_height())

        left, right, top, bottom = 70, 70, 30, 50
        x0, y0 = left, top
        x1, y1 = w - right, h - bottom

        start_dt, end_dt = self._get_window(day)
        total_sec = (end_dt - start_dt).total_seconds()
        if total_sec <= 0:
            self._draw_empty(c, "Bad zoom window.")
            return []

        t = df["tradeTime"]
        mask = (t >= start_dt) & (t <= end_dt)
        needed = ["tradeTime"] + list(set(pnl_cols + delta_cols))
        sub = df.loc[mask, [col for col in needed if col in df.columns]].copy()
        if sub.empty:
            self._draw_empty(c, "No trades in window.")
            return []

        sub.sort_values("tradeTime", inplace=True, kind="mergesort")
        secs = (sub["tradeTime"] - start_dt).dt.total_seconds().astype("float64")

        def series_range(cols: List[str]) -> Optional[Tuple[float, float]]:
            if not cols:
                return None
            vals = []
            for col in cols:
                if col in sub.columns:
                    vals.append(pd.to_numeric(sub[col], errors="coerce").astype("float64"))
            if not vals:
                return None
            s_all = pd.concat(vals, axis=0).dropna()
            if s_all.empty:
                return None
            return float(s_all.min()), float(s_all.max())

        def pad_range(r: Tuple[float, float]) -> Tuple[float, float]:
            a, b = r
            if a == b:
                return a - 1.0, b + 1.0
            span = b - a
            return a - 0.08 * span, b + 0.08 * span

        pnl_rng = series_range(pnl_cols) or (-1.0, 1.0)
        d_rng = series_range(delta_cols) or (-1.0, 1.0)
        pnl_min, pnl_max = pad_range(pnl_rng)
        d_min, d_max = pad_range(d_rng)

        def x_map(s: float) -> float:
            return x0 + (s / total_sec) * (x1 - x0)

        def y_map_left(v: float) -> float:
            return y1 - ((v - pnl_min) / (pnl_max - pnl_min)) * (y1 - y0)

        def y_map_right(v: float) -> float:
            return y1 - ((v - d_min) / (d_max - d_min)) * (y1 - y0)

        c.create_rectangle(x0, y0, x1, y1, outline="#D8E1F0", width=1)

        # grid: 10 vertical + 5 horizontal
        for i in range(11):
            xx = x0 + i * (x1 - x0) / 10
            c.create_line(xx, y0, xx, y1, fill="#EEF3FF")
        for i in range(5):
            yy = y0 + i * (y1 - y0) / 4
            c.create_line(x0, yy, x1, yy, fill="#F3F6FF")

        # axes labels
        for i in range(5):
            frac = i / 4
            yy = y1 - frac * (y1 - y0)
            vL = pnl_min + frac * (pnl_max - pnl_min)
            vR = d_min + frac * (d_max - d_min)
            c.create_text(x0 - 8, yy, text=f"{vL:,.0f}", anchor="e", fill="#5E6B85", font=("Segoe UI", 9))
            c.create_text(x1 + 8, yy, text=f"{vR:,.2f}", anchor="w", fill="#5E6B85", font=("Segoe UI", 9))

        # markers (relative to full day, show if within zoom)
        full_start = pd.Timestamp(datetime.combine(day, time(8, 0, 0)))
        full_end = pd.Timestamp(datetime.combine(day, time(22, 0, 0)))
        self._draw_marker_windowed(c, day, full_start, full_end, start_dt, end_dt, total_sec, x_map, y0, y1)

        # titles: left + right on top of corresponding axes
        c.create_text(x0, y0 - 14, text="PnL", anchor="w", fill="#0B1220", font=("Segoe UI Semibold", 10))
        c.create_text(x1, y0 - 14, text="Δ (right)", anchor="e", fill="#0B1220", font=("Segoe UI Semibold", 10))

        palette = ["#2E7BFF", "#00B6D6", "#7C3AED", "#16A34A", "#F97316", "#EF4444", "#0EA5E9", "#A855F7"]
        legend_items: List[Tuple[str, str, str]] = []

        for k, colname in enumerate(pnl_cols):
            if colname not in sub.columns:
                continue
            color = palette[k % len(palette)]
            svals = pd.to_numeric(sub[colname], errors="coerce").fillna(0.0).astype("float64").tolist()
            pts: List[float] = []
            for ss, vv in zip(secs.tolist(), svals):
                pts.extend([x_map(float(ss)), y_map_left(float(vv))])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=2)
                legend_items.append((color, colname, "PnL"))

        offset = len(pnl_cols)
        for k, colname in enumerate(delta_cols):
            if colname not in sub.columns:
                continue
            color = palette[(offset + k) % len(palette)]
            svals = pd.to_numeric(sub[colname], errors="coerce").fillna(0.0).astype("float64").tolist()
            pts: List[float] = []
            for ss, vv in zip(secs.tolist(), svals):
                pts.extend([x_map(float(ss)), y_map_right(float(vv))])
            if len(pts) >= 4:
                c.create_line(*pts, fill=color, width=2)
                legend_items.append((color, colname, "Δ"))

        return legend_items

    def _draw_marker_windowed(
        self,
        canvas: tk.Canvas,
        day: date,
        full_start: pd.Timestamp,
        full_end: pd.Timestamp,
        start_dt: pd.Timestamp,
        end_dt: pd.Timestamp,
        total_sec: float,
        x_map,
        y0: int,
        y1: int,
    ) -> None:
        # 09:00
        t1 = pd.Timestamp(datetime.combine(day, time(9, 0)))
        # US open Berlin
        uo = us_open_berlin(day)
        t2 = pd.Timestamp(datetime.combine(day, uo))

        for tmark, label in [(t1, "09:00"), (t2, f"US open {uo.strftime('%H:%M')}")]:
            if not (start_dt <= tmark <= end_dt):
                continue
            s = (tmark - start_dt).total_seconds()
            xx = x_map(s)
            canvas.create_line(xx, y0, xx, y1, fill="#D1E2FF", width=2)
            canvas.create_text(xx, y0 - 6, text=label, fill="#2667D6", font=("Segoe UI Semibold", 9), anchor="s")
