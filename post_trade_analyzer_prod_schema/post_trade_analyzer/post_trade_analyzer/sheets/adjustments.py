from __future__ import annotations

from typing import Dict, List, Optional
import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..utils.table_utils import build_display_cache


class AdjustmentsSheet(ttk.Frame):
    sheet_id = "adj"
    sheet_title = "Adjustments"

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)

        self._df: Optional[pd.DataFrame] = None
        self._cache: Dict[str, List[str]] = {}
        self._cache_len: int = 0
        self._cols: List[str] = ["underlyingName", "date", "Anpassung"]
        self._rendered_once_for_df_id: Optional[int] = None

        self._build()

    def _build(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=(14, 10))

        ttk.Label(top, text="Adjustments (Anpassung)", style="Title.TLabel").pack(side="left")

        self.info_var = tk.StringVar(value="No adjustments loaded.")
        ttk.Label(top, textvariable=self.info_var, style="Muted.TLabel").pack(side="right")

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        self.tree = ttk.Treeview(inner, style="Futur.Treeview", show="headings", selectmode="browse")
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

    def on_adjustment_loaded(self, df_adj: pd.DataFrame) -> None:
        self._df = df_adj
        df_id = id(df_adj)
        if self._rendered_once_for_df_id == df_id:
            return
        self._rendered_once_for_df_id = df_id

        if df_adj is None or df_adj.empty:
            self._clear_tree()
            self.info_var.set("No adjustments to show.")
            return

        cols = [c for c in self._cols if c in df_adj.columns] + [c for c in df_adj.columns if c not in self._cols]
        view = df_adj.loc[:, cols]

        self._cache, self._cache_len = build_display_cache(view)
        self._render(cols)

    def _render(self, cols: List[str]) -> None:
        self._clear_tree()
        self.tree["columns"] = cols

        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=150 if c != "Anpassung" else 120, minwidth=80, anchor="c", stretch=False)

        cache = self._cache
        for i in range(self._cache_len):
            values = [cache[c][i] for c in cols]
            tag = "even" if (i % 2 == 0) else "odd"
            self.tree.insert("", "end", values=values, tags=(tag,))

        self.info_var.set(f"Rows: {self._cache_len:,}")

    def _clear_tree(self) -> None:
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.tree["columns"] = []