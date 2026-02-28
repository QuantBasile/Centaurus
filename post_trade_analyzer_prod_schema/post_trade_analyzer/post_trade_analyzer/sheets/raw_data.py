from __future__ import annotations

from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..utils.table_utils import build_display_cache


class BaseSheet(ttk.Frame):
    sheet_id: str = "base"
    sheet_title: str = "Base"

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        pass


class RawDataSheet(BaseSheet):
    """
    Performance-first "sample preview" of raw data.

    Design goals:
    - Render only once after load.
    - Never do expensive work on resize (no <Configure> binding, no autofit).
    - Keep it visually clean/proper.
    - After it is rendered once, it should not impact app responsiveness.
    """
    sheet_id = "raw"
    sheet_title = "Raw Data"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: Optional[pd.DataFrame] = None

        # Small preview: enough to show structure, not enough to slow UI.
        self._preview_n = 120

        # Cache of strings for the preview slice only
        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0
        self._cols: List[str] = []

        # Render only once (per load). Prevent rerenders on tab switches etc.
        self._rendered_once_for_df_id: Optional[int] = None

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))

        ttk.Label(top, text="Raw Data (preview)", style="Title.TLabel").pack(side="left")

        self.info_var = tk.StringVar(value="No data loaded.")
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        # Treeview
        self.tree = ttk.Treeview(inner, style="Futur.Treeview", show="headings", selectmode="browse")
        self.vsb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.hsb = ttk.Scrollbar(inner, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")

        inner.rowconfigure(0, weight=1)
        inner.columnconfigure(0, weight=1)

        # Light striping, cheap
        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background="#F8FAFF")

        # IMPORTANT:
        # - No <Configure> binding
        # - No autofit calls
        # This keeps resize super smooth.

    def on_df_loaded(self, df: pd.DataFrame) -> None:
        self._df = df

        # Guard: if someone calls on_df_loaded again with the same df object,
        # do nothing (keeps app snappy on tab switches).
        df_id = id(df)
        if self._rendered_once_for_df_id == df_id:
            return
        self._rendered_once_for_df_id = df_id

        if df is None or df.empty:
            self._clear_tree()
            self.info_var.set("No data to show.")
            return

        head = df.iloc[: min(self._preview_n, len(df))]
        self._cols = list(head.columns)
        self._cache, self._cache_len = build_display_cache(head)

        self._render_preview()

    def _render_preview(self) -> None:
        df = self._df
        if df is None or df.empty:
            self._clear_tree()
            self.info_var.set("No data to show.")
            return

        cols = self._cols
        n_show = self._cache_len

        self.info_var.set(f"Preview: first {n_show:,} rows of {len(df):,} (static).")

        self._clear_tree()

        self.tree["columns"] = cols

        # Performance rules:
        # - stretch=False avoids expensive relayout work during window resizing
        # - fixed width keeps it stable; horizontal scrollbar handles overflow
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=110, minwidth=80, anchor="c", stretch=False)

        cache = self._cache
        # Insert only preview rows (bounded cost)
        for i in range(n_show):
            values = [cache[c][i] for c in cols]
            tag = "even" if (i % 2 == 0) else "odd"
            self.tree.insert("", "end", values=values, tags=(tag,))

    def _clear_tree(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.tree["columns"] = []