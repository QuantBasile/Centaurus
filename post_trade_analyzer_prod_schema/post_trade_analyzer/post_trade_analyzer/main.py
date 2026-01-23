from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from .app import PostTradeApp
from .data_provider import FakeTradeDataProvider, FakeDataConfig

def main() -> None:
    provider = FakeTradeDataProvider(FakeDataConfig(n_rows=200_000))
    app = PostTradeApp(provider=provider)
    app.mainloop()

if __name__ == "__main__":
    main()
