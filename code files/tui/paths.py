"""Shared paths for the Pine Harvester TUI.

Puts the harvester's ``code files`` tree on ``sys.path`` (exactly like every
harvester script does via ``bootstrap``) and resolves the data-folder config
through ``tv_config`` so the TUI always agrees with the CLI.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODE = HERE.parent                      # code files/
ROOT = CODE.parent                      # repository root

sys.path.insert(0, str(CODE))
import bootstrap  # noqa: F401,E402  (adds core/harvest/organize/tools to sys.path)

from tv_config import OUT, LOGS  # noqa: E402
from job import find_job_python  # noqa: E402

#: Interpreter used for harvester jobs. The TUI runs on the Textual venv, which
#: does not necessarily have ``requests``; jobs therefore run on a Python that
#: does (system python by default).
JOB_PY = find_job_python()
