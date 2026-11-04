"""What flows through the triage graph: the state each node reads and writes, and the run context.

Parallel nodes write different state keys, except `asked` and `ai_failures`, which write_notes
and judge_rules both write and a reducer joins. Add a reducer before letting two parallel nodes
write any other key, or LangGraph rejects the run.
"""

import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from herald_core.history import History
from herald_core.schema import (
    AiFailure,
    Decision,
    Email,
    Notes,
    RiskFlag,
    RuleVerdict,
    WorkspaceConfig,
)
from herald_core.tools import Toolbox


@dataclass
class TriageContext:
    """Per-run objects that are not state: the toolbox is bound to one workspace by the server."""

    tools: Toolbox


class TriageState(TypedDict, total=False):
    email: Email
    config: WorkspaceConfig
    business_name: str
    word_flags: set[RiskFlag]
    history: History
    # The model tools the AI chose to call, as "node:tool". Each model node returns only its own
    # calls and the reducer appends them, so neither node overwrites the other's.
    asked: Annotated[list[str], operator.add]
    notes: Notes | None
    # None when the rules call failed, so a failure never reads as "no rule matched".
    verdicts: list[RuleVerdict] | None
    # One entry per model call that gave no answer. Each node returns only its own.
    ai_failures: Annotated[list[AiFailure], operator.add]
    decision: Decision
