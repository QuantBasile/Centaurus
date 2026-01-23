from __future__ import annotations

from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox

import pandas as pd

from ..utils.table_utils import build_display_cache, sanitize_visible_cols

class BaseSheet(ttk.Frame):
    sheet_id: str = "base"
    sheet_title: str = "Base"
    def on_df_loaded(self, df: pd.DataFrame) -> None:
        pass

class RawDataSheet(BaseSheet):
    sheet_id = "raw"
    sheet_title = "Raw Data"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._df: Optional[pd.DataFrame] = None

        self._visible_cols: Optional[List[str]] = None
        self._rendered_cols: List[str] = []

        self._preview_n = 500
        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0

        self._resize_after_id: Optional[str] = None
        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))

        ttk.Label(top, text="Raw Data", style="Title.TLabel").pack(side="left")

        self.info_var = tk.StringVar(value="No data loaded.")
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=14, pady=(0, 10))
        self.columns_btn = ttk.Button(actions, text="Columns", command=self._open_columns_dialog_fast)
        self.columns_btn.pack(side="left")

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

        self.tree.bind("<Configure>", self._on_tree_configure)

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        self._df = df
        if self._visible_cols is None:
            self._visible_cols = list(df.columns)

        head = df.iloc[: min(self._preview_n, len(df))]
        self._cache, self._cache_len = build_display_cache(head)
        self._render_from_cache()

    def _render_from_cache(self) -> None:
        df = self._df
        if df is None or df.empty:
            self._clear_tree()
            self.info_var.set("No data to show.")
            return

        cols = sanitize_visible_cols(list(df.columns), self._visible_cols)
        self._rendered_cols = cols

        n_show = self._cache_len
        self.info_var.set(f"Showing first {n_show:,} rows of {len(df):,}.")

        self._clear_tree()

        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=90, minwidth=60, anchor="w", stretch=True)

        cache = self._cache
        for i in range(n_show):
            values = [cache[c][i] for c in cols]
            tag = "even" if (i % 2 == 0) else "odd"
            self.tree.insert("", "end", values=values, tags=(tag,))

        self._autofit_from_cache(sample_rows=min(150, n_show))

    def _clear_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.tree["columns"] = []

    def _on_tree_configure(self, _event) -> None:
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(180, lambda: self._autofit_from_cache(sample_rows=120))

    def _autofit_from_cache(self, sample_rows: int = 120) -> None:
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

        pad = 24
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

        hard_min, hard_max = 70, 360
        widths = {c: max(hard_min, min(hard_max, max_px[c])) for c in self._rendered_cols}

        total = sum(widths.values())
        if total > available * 1.2:
            for c in self._rendered_cols:
                if c.startswith("flag_"):
                    widths[c] = max(hard_min, min(widths[c], 70))

        for c in self._rendered_cols:
            self.tree.column(c, width=widths[c], stretch=True)

    def _open_columns_dialog_fast(self) -> None:
        df = self._df
        if df is None:
            messagebox.showinfo("Columns", "Load data first.")
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
