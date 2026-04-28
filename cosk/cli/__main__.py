from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from .main import main  # noqa: E402

if __name__ == "__main__":
    main()

