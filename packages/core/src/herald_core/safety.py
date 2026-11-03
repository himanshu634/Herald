"""Word check that runs beside the AI.

Either this check or the AI can raise a safety-floor flag, so one AI mistake (or an email
written to fool the AI) is not enough to bury a real threat.

A match always alerts and no rule can undo it, so a pattern that also fits everyday words is
an alert the owner cannot quiet. Words with an ordinary meaning ("Sue" the name, a food court,
"hacked it open", "the bomb" as praise) only count in a threat's phrasing. The evals
(`packages/evals`, tags `word_false_positive` and `safety_floor`) hold the cases behind each
pattern; check both tags after changing one.
"""

import re

from herald_core.schema import RiskFlag

# Within one sentence: an account word and "hack" close together.
_HACKED = (
    r"\b(account|e-?mail|login|password|profile|data|card|phone|site|store)\b"
    r"[^.!?\n]{0,40}\bhack(ed|ers?|ing)?\b"
    r"|\bhack(ed|ers?|ing)?\b[^.!?\n]{0,40}"
    r"\b(account|e-?mail|login|password|profile|data|card|phone|site|store)\b"
)

_PATTERNS: dict[RiskFlag, re.Pattern[str]] = {
    RiskFlag.SAFETY: re.compile(
        r"\b(kill|hurt|harm)\s+(myself|yourself|you)\b|\bsuicid\w*"
        # Not "the bomb", which is praise.
        r"|(?<!\bthe )\bbombs?\b|\bweapons?\b",
        re.I,
    ),
    RiskFlag.ACCOUNT_OR_DATA: re.compile(
        _HACKED + r"|\bstolen\s+card\b|\bused\s+my\s+card\b"
        r"|\bunauthori[sz]ed\s+(charges?|payments?|transactions?|access|logins?|purchases?"
        r"|orders?|use|debits?)\b"
        r"|\bdata\s+(leak|breach)\b|\bfraud\w*",
        re.I,
    ),
    RiskFlag.LEGAL_THREAT: re.compile(
        r"\blawyer\b|\battorney\b|\blegal\s+(action|notice)\b"
        # "sue" is also a name: only as a verb aimed at someone, or after "will" and the like.
        r"|\bsue\s+(you|your|them|us)\b|\b(will|going\s+to|gonna|shall|'ll)\s+sue\b"
        # "court" is also a food court or a court reporter: only when someone goes to one.
        r"|\b(to|in|into)\s+court\b|\bcourt\s+(case|notice|order|summons)\b"
        r"|\bconsumer\s+(forum|court)\b",
        re.I,
    ),
}


def word_check(text: str) -> set[RiskFlag]:
    return {flag for flag, pattern in _PATTERNS.items() if pattern.search(text)}
