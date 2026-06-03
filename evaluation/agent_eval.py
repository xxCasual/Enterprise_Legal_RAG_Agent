"""Backward-compatible Agent Eval entrypoint.

New code should import from ``evaluation.agent`` or run
``python -m evaluation.agent.cli``. This module remains so older docs, tests,
and scripts that import ``evaluation.agent_eval`` continue to work.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.agent import core as _core
from evaluation.agent.core import *  # noqa: F401,F403
from evaluation.agent.core import main

_PRIVATE_COMPAT_NAMES = (
    "_cache_key",
    "_csv_value",
    "_default_agent_runner",
    "_default_contract_reviewer",
    "_empty_to_none",
    "_extract_refused",
    "_extract_risk_level",
    "_looks_like_refusal",
    "_normalize_tools",
    "_safe_float",
    "_task_type_for_sample",
    "_tools_match",
    "_validate_sample",
)

for _name in _PRIVATE_COMPAT_NAMES:
    globals()[_name] = getattr(_core, _name)


if __name__ == "__main__":
    main()
