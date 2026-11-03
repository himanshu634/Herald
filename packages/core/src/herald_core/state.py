"""What flows through the triage graph: the state each node reads and writes, and the run context.

Parallel nodes write different state keys, so no key needs a reducer. Add one before letting two
parallel nodes write the same key, or LangGraph rejects the run.
"""

from dataclasses import dataclass
from typing import TypedDict

from herald_core.history import History
from herald_core.schema import Decision, Email, Notes, RiskFlag, RuleVerdict, WorkspaceConfig
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
    notes: Notes | None
    verdicts: list[RuleVerdict]
    decision: Decision
