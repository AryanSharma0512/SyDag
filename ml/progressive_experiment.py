"""
Progressive early-signal experiments: records only vs + imagery through TP1 ... TP6.

    cd ml
    uv run --project ../backend --group ml python progressive_experiment.py --help

Same as `python -m soilsignal_ml progressive ...`. See AGENT3_HANDOFF.md at the repo root.
"""

import sys

from soilsignal_ml.progressive.cli import main

if __name__ == "__main__":
    sys.exit(main())
