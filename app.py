# app.py (versão final - com tratamento manual de CORS para compatibilidade com proxy)
import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
import httpx

# A origem permitida (idealmente vinda de uma variável de ambiente)
# Para garantir, vamos deixar o valor fixo por enquanto.
ALLOWED_ORIGIN = "https://propagacidadeaudio.com.br"

app = FastAPI(title="Agente Carro de Som - Protótipo (CORS Manual)")

# --- INÍCIO DA CORREÇÃO DE CORS ---

# 1. Middleware para adicionar o cabeçalho CORS a TODAS as respostas normais
@app.middleware("http")
async def add_cors_header(request: Request, call_next):
    # Pula a lógica para requisições de preflight (OPTIONS), que terão seu próprio handler
    if request.method == "OPTIONS":
        return await call_next(request)
    
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    return response

# 2. Handler explícito para TODAS as requisições OPTIONS (preflight)
# Isso intercepta a requisição antes que o middleware do FastAPI que causa o conflito atue.
@app.options("/api/{path:path}")
async def handle_options_requests(path: str):
    response = Response()
    response.headers["Access-Control-Allow-Origin"] = ALLOWED_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# --- FIM DA CORREÇÃO DE CORS ---
# NOTA: O app.add_middleware(CORSMiddleware, ...) FOI REMOVIDO INTENCIONALMENTE.


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
        "note": "Protótipo: rota funcionando com CORS manual."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)