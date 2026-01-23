# Post-Trade Analyzer (Tkinter + pandas, Python 3.12)

A modular, trader-friendly post-trade analysis desktop app built with **Tkinter** and **pandas** only (no external UI libs).

## Run
```bash
python -m post_trade_analyzer.main
```

## Project structure
```
post_trade_analyzer/
  main.py
  app.py
  theme.py
  data_provider.py
  ui_header.py
  ui_nav.py
  utils/
    schema.py
    table_utils.py
    time_utils.py
  sheets/
    __init__.py
    raw_data.py
    instrument_day.py
```

## Schema
The app expects **64 columns** total:
- 21 production columns
- the remaining 43 are booleans: `flag_00`..`flag_42`

Production columns:
```
tradeNr, instrument, tradeTime, tradeUnderlyingSpotRef, portfolio, counterparty, underlying,
CumDelta, CumDelta_stock, CumDelta_certificates_abandon, CumDelta_our_abandon, CumDelta_external_abandon,
CumDelta_our_scheine, CumDelta_external_scheine, PremiaCum, SpreadsCapture, FullSpreadCapture, Total,
PnlVonDeltaCum, feesCum, AufgeldCum
```



run -m post_trade_analyzer.main
