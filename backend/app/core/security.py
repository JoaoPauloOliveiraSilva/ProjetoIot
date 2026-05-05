from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from app.core.config import settings

API_KEY_NAME = "X-API-Key"

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def is_valid_api_key(api_key: str | None) -> bool:
    return bool(api_key) and api_key == settings.API_KEY_EDGE

async def validar_api_key(api_key_header: str = Security(api_key_header)):
    """
    Verifica se a chave enviada no cabeçalho corresponde à chave configurada no .env.
    """
    if is_valid_api_key(api_key_header):
        return api_key_header
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso Negado: API Key inválida ou ausente. Apenas dispositivos Edge autorizados."
        )
