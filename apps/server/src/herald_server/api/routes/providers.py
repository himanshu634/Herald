"""Mail providers this server can connect, so the web shows only connect buttons that work."""

from fastapi import APIRouter

from herald_server.api.deps import ServicesDep

router = APIRouter(prefix="/api/providers", tags=["mailboxes"])


@router.get("")
def list_providers(services: ServicesDep) -> list[str]:
    # Without the token key a connect can neither seal its OAuth state nor store the tokens,
    # so no provider can connect, however many are configured.
    if services.secrets is None:
        return []
    return sorted(services.connectors)
