from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date
from typing import Optional
import pandas as pd

class HeaderBar(ttk.Frame):
    def __init__(self, master: tk.Misc, on_load) -> None:
        super().__init__(master, style="Header.TFrame")
        self.on_load = on_load

        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready.")
        self.rows_var = tk.StringVar(value="No data loaded.")

        self._build()

    def _build(self) -> None:
        self.pack(fill="x", padx=12, pady=10)
        row = ttk.Frame(self, style="HeaderCard.TFrame")
        row.pack(fill="x")

        title = ttk.Label(row, text="Post-Trade Analyzer", style="Title.TLabel")
        title.grid(row=0, column=0, rowspan=2, sticky="w", padx=(6, 14))

        ttk.Label(row, text="From", style="Muted.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 6))
        self.from_entry = ttk.Entry(row, textvariable=self.from_var, width=12)
        self.from_entry.grid(row=1, column=1, sticky="w", padx=(0, 12))

        ttk.Label(row, text="To", style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.to_entry = ttk.Entry(row, textvariable=self.to_var, width=12)
        self.to_entry.grid(row=1, column=2, sticky="w", padx=(0, 12))

        self.load_btn = ttk.Button(row, text="Load trades", style="Accent.TButton", command=self._handle_load)
        self.load_btn.grid(row=1, column=3, sticky="w", padx=(0, 14))

        right = ttk.Frame(row, style="HeaderCard.TFrame")
        right.grid(row=0, column=4, rowspan=2, sticky="e")

        self.progress = ttk.Progressbar(right, mode="indeterminate", length=180)
        self.progress.grid(row=0, column=0, sticky="e", pady=(2, 6))

        status_line = ttk.Frame(right, style="HeaderCard.TFrame")
        status_line.grid(row=1, column=0, sticky="e")
        ttk.Label(status_line, textvariable=self.status_var).pack(side="left")
        ttk.Label(status_line, text="  •  ", style="Muted.TLabel").pack(side="left")
        ttk.Label(status_line, textvariable=self.rows_var, style="Muted.TLabel").pack(side="left")

        today = date.today().isoformat()
        self.from_var.set(today)
        self.to_var.set(today)

        self.from_entry.bind("<Return>", lambda e: self._handle_load())
        self.to_entry.bind("<Return>", lambda e: self._handle_load())

        row.columnconfigure(4, weight=1)

        sep = ttk.Separator(self.master, orient="horizontal", style="HeaderLine.TSeparator")
        sep.pack(fill="x", padx=12, pady=(0, 6))

    def _handle_load(self) -> None:
        self.on_load(self.from_var.get().strip(), self.to_var.get().strip())

    def set_loading(self, loading: bool) -> None:
        if loading:
            self.load_btn.configure(state="disabled")
            self.progress.start(12)
        else:
            self.load_btn.configure(state="normal")
            self.progress.stop()

    def set_status(self, msg: str) -> None:
        self.status_var.set(msg)

    def set_rows_info(self, df: Optional[pd.DataFrame]) -> None:
        if df is None:
            self.rows_var.set("No data loaded.")
        else:
            self.rows_var.set(f"{len(df):,} rows × {df.shape[1]} cols")

    def show_error(self, title: str, msg: str) -> None:
        messagebox.showerror(title, msg)
