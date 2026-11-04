import pytest

from herald_core.providers import UnknownProvider
from herald_core.providers.openrouter import OpenRouterModel
from herald_server.services import build_model, build_services
from herald_server.settings import Settings


@pytest.fixture(autouse=True)
def no_keys(monkeypatch, tmp_path):
    # Nothing from the shell or a real .env may reach these tests.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HERALD_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("HERALD_MODEL_NAME", raising=False)
    monkeypatch.chdir(tmp_path)


def test_key_from_dotenv_reaches_the_provider(tmp_path):
    # pydantic-settings never exports .env to os.environ, so Settings reads the key itself.
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=sk-or-test\n")
    assert Settings().secret("OPENROUTER_API_KEY") == "sk-or-test"
    assert isinstance(build_model(Settings()), OpenRouterModel)


def test_environment_wins_over_dotenv(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=from-file\n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    assert Settings().secret("OPENROUTER_API_KEY") == "from-env"


def test_empty_key_counts_as_unset(tmp_path):
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=\n")
    assert Settings().secret("OPENROUTER_API_KEY") is None


def test_missing_key_names_the_variable(monkeypatch):
    # Only the Anthropic key is set: the openrouter provider must not use it.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    with pytest.raises(RuntimeError) as info:
        build_model(Settings(model_provider="openrouter"))
    assert "OPENROUTER_API_KEY" in str(info.value)
    assert "sk-ant-secret" not in str(info.value)


def test_unknown_provider_fails_at_startup(settings):
    with pytest.raises(UnknownProvider, match="nope"):
        build_services(settings.model_copy(update={"model_provider": "nope"}))


def test_startup_fails_without_the_provider_key(settings):
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        build_services(settings)


def test_model_name_defaults_to_the_provider_default(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    assert build_model(Settings(model_name=None))._model == "openai/gpt-oss-20b"
    assert build_model(Settings(model_name="other/model"))._model == "other/model"
