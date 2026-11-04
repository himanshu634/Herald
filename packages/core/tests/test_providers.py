import pytest

from herald_core.providers import UnknownProvider, load_provider, provider_names
from herald_core.providers.anthropic import AnthropicModel


def test_built_in_providers_are_installed():
    assert {"anthropic", "openrouter"} <= set(provider_names())


def test_anthropic_provider_builds_its_model():
    provider = load_provider("anthropic")
    assert provider.name == "anthropic"
    assert provider.default_model == "claude-haiku-5-5"
    assert provider.api_key_env == "ANTHROPIC_API_KEY"
    assert isinstance(provider.build("claude-haiku-5-5", "sk-test"), AnthropicModel)


def test_unknown_provider_lists_the_installed_ones():
    with pytest.raises(UnknownProvider) as info:
        load_provider("openrutor")
    assert "openrutor" in str(info.value)
    assert "anthropic" in str(info.value)
