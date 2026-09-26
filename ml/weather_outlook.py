"""
Historical weather outlook: weather history, backtest, single outlooks, yield coupling.

    cd ml
    uv run --project ../backend --group ml python weather_outlook.py --help

Same as `python -m soilsignal_ml.weather_outlook ...`. Method and results:
research/weather_outlook.md.
"""

import sys

from soilsignal_ml.weather_outlook.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
