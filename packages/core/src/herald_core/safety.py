"""Word check that runs beside the AI.

Either this check or the AI can raise a safety-floor flag, so one AI mistake (or an email
written to fool the AI) is not enough to bury a real threat.
"""

import re

from herald_core.schema import RiskFlag

_PATTERNS: dict[RiskFlag, re.Pattern[str]] = {
    RiskFlag.SAFETY: re.compile(
        r"\b(kill|hurt|harm)\s+(myself|yourself|you)\b|\bsuicid\w*|\bbomb\b|\bweapon\b", re.I
    ),
    RiskFlag.ACCOUNT_OR_DATA: re.compile(
        r"\bhack(ed|er)?\b|\bstolen\s+card\b|\bused\s+my\s+card\b|\bunauthori[sz]ed\b"
        r"|\bdata\s+(leak|breach)\b|\bfraud\w*",
        re.I,
    ),
    RiskFlag.LEGAL_THREAT: re.compile(
        r"\blawyer\b|\battorney\b|\blegal\s+(action|notice)\b|\bsue\b|\bcourt\b"
        r"|\bconsumer\s+(forum|court)\b",
        re.I,
    ),
}


def word_check(text: str) -> set[RiskFlag]:
    return {flag for flag, pattern in _PATTERNS.items() if pattern.search(text)}
