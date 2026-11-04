"""Model providers: plug-ins that build a `TriageModel` for one API.

A provider is found by name through the `herald.model_providers` entry-point group, so any
installed package can add one. The entry point's name must equal the provider's `name`.
"""

from importlib.metadata import entry_points
from typing import Protocol

from herald_core.model import TriageModel

ENTRY_POINT_GROUP = "herald.model_providers"


class ModelProvider(Protocol):
    name: str  # what HERALD_MODEL_PROVIDER says
    default_model: str  # used when no model name is set
    api_key_env: str  # the one environment variable this provider reads its key from

    def build(self, model: str, api_key: str, max_retries: int = 2) -> TriageModel: ...


class UnknownProvider(ValueError):
    """No installed provider has this name."""


def provider_names() -> list[str]:
    return sorted(ep.name for ep in entry_points(group=ENTRY_POINT_GROUP))


def load_provider(name: str) -> ModelProvider:
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        if ep.name == name:
            return ep.load()
    # Name the installed ones: the usual cause is a typo in HERALD_MODEL_PROVIDER.
    raise UnknownProvider(
        f"Unknown model provider {name!r}. Installed providers: {', '.join(provider_names())}."
    )
