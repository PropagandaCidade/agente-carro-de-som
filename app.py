# app.py (versão 4 - com ProxyHeadersMiddleware)
import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

# Middleware para ajudar o FastAPI a entender que está atrás de um proxy (como o da Railway)
# Importação necessária:
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

# --- TENTATIVA ANTERIOR (MANTIDA PARA GARANTIA) ---
# Forçando a origem permitida diretamente no código para eliminar
# qualquer dúvida sobre a variável de ambiente.
ALLOWED_ORIGINS = ["https://propagandacidadeaudio.com.br"]
# --- FIM DA TENTATIVA ANTERIOR ---

app = FastAPI(title="Agente Carro de Som - Protótipo v4")

# --- MUDANÇA PRINCIPAL ---
# 1. Adicionar o middleware para o proxy da Railway
# Este middleware deve ser um dos primeiros a serem adicionados.
# Ele corrige como o FastAPI interpreta os cabeçalhos de host, porta e esquema.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# 2. Adicionar o middleware do CORS depois
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# --- FIM DA MUDANÇA PRINCIPAL ---

class SearchReq(BaseModel):
    city: str
    state: Optional[str] = None
    radii: Optional[List[int]] = [10000, 30000, 50000]

@app.get("/")
async def root():
    return {"message": "Agente Carro de Som — serviço ativo."}

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/search_city")
async def search_city(payload: SearchReq):
    if not payload.city or not payload.city.strip():
        raise HTTPException(status_code=400, detail="Informe 'city' no payload.")

    nominatim_url = "https://nominatim.openstreetmap.org/search"
    q = payload.city + (f", {payload.state}" if payload.state else "") + ", Brasil"
    params = {"q": q, "format": "json", "limit": 1}
    headers = {"User-Agent": "SomAgent-Test/1.0 (+contato@exemplo.com)"}

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(nominatim_url, params=params)
            resp.raise_for_status()
            arr = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Erro ao consultar geocoding: {str(e)}")

    if not arr:
        return {"status": "city_not_geocoded", "city": payload.city}

    first = arr[0]
    geocoding = {
        "lat": float(first.get("lat")),
        "lon": float(first.get("lon")),
        "display_name": first.get("display_name")
    }

    return {
        "status": "ok",
        "city": payload.city,
        "geocoding": geocoding,
        "note": "Protótipo: rota funcionando com middleware de proxy."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)