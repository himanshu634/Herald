"""What the model nodes do when their call fails: sort the error and log it once.

The nodes never raise. A raise inside the parallel step would stop word_check and decide too,
and the safety floor would be lost with the notes. The failure goes into state instead, and
the server decides after decide whether to save the result or try the email again later.
"""

import logging

from herald_core.model import failure_of
from herald_core.schema import AiFailure, FailureKind


def record_failure(log: logging.Logger, call: str, email_id: str, exc: Exception) -> AiFailure:
    failure = failure_of(call, exc)
    message = "%s failed for email %s: %s (%s, request %s)"
    args = (call, email_id, failure.error, failure.kind, failure.request_id)
    if failure.kind is FailureKind.UNAVAILABLE:
        # Expected during an outage, and retried: no traceback per email.
        log.warning(message, *args)
    elif failure.kind is FailureKind.SETUP:
        # Every email will fail this way until someone fixes the key, model or billing.
        log.error(message, *args)
    else:
        log.error(message, *args, exc_info=exc)
    return failure
