"""Backward-compatible Agent Eval suite entrypoint.

New code should run ``python -m evaluation.agent.suite``. This wrapper keeps
the historical ``evaluation/run_agent_eval_suite.py`` command and imports
working.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.agent.suite import *  # noqa: F401,F403
from evaluation.agent.suite import main


if __name__ == "__main__":
    main()
