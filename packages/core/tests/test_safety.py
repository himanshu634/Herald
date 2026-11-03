import pytest

from herald_core.safety import word_check
from herald_core.schema import RiskFlag

SAFETY, DATA, LEGAL = RiskFlag.SAFETY, RiskFlag.ACCOUNT_OR_DATA, RiskFlag.LEGAL_THREAT


@pytest.mark.parametrize(
    ("text", "flag"),
    [
        ("I want to kill myself", SAFETY),
        ("I will hurt you", SAFETY),
        ("Feeling suicidal tonight", SAFETY),
        ("There is a bomb in your warehouse", SAFETY),
        ("I'll bring a weapon", SAFETY),
        ("My account was hacked", DATA),
        ("Someone hacked my Tripfold account", DATA),
        ("A hacker got into my email", DATA),
        ("My login got hacked yesterday", DATA),
        ("Someone used my card", DATA),
        ("My stolen card was charged", DATA),
        ("There is an unauthorised charge on my statement", DATA),
        ("I see unauthorized transactions", DATA),
        ("Your data breach exposed my address", DATA),
        ("This is fraud", DATA),
        ("My lawyer will be in touch", LEGAL),
        ("I have spoken to an attorney", LEGAL),
        ("We will take legal action", LEGAL),
        ("Expect a legal notice", LEGAL),
        ("I will sue you", LEGAL),
        ("I'm going to sue Tripfold", LEGAL),
        ("I'll sue", LEGAL),
        ("See you in court", LEGAL),
        ("I will take you to court", LEGAL),
        ("I'm taking this to court", LEGAL),
        ("Filing a case in consumer court", LEGAL),
        ("Complaint at the consumer forum", LEGAL),
    ],
)
def test_real_threats_are_caught(text, flag):
    assert flag in word_check(text)


# Each of these alerted through the safety floor in the evals, and no rule can undo that.
@pytest.mark.parametrize(
    "text",
    [
        "Hi, this is Sue Mathews. Thanks, Sue",
        "I saw your pop-up stall near the food court at Phoenix Mall",
        "We're a court reporting agency using Ledgerly",
        "The zip jammed shut and I hacked it open with a pen knife",
        "Are they an unauthorised reseller?",
        "Honestly this duffel is the bomb.",
        "Basketball court shoes, do they fit in the backpack?",
    ],
)
def test_ordinary_words_are_not_threats(text):
    assert word_check(text) == set()
