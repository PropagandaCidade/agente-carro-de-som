# app.py
# FastAPI minimal com CORS configurado para permitir chamadas do seu front (Hostinger)
# Salve este arquivo na raiz do seu projeto (substitua o app.py atual), commit e push.

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import httpx

# =========================
# Configurações - ajuste aqui se necessário
# =========================
# Domínios permitidos (CORS) — substitua/adicione domínios conforme precisar
ALLOWED_ORIGINS = [
    "https://propagandacidadeaudio.com.br",   # seu frontend na Hostinger
    "https://agente-carro-de-som.railway.app", # opcional: permitir também o domínio da API
    "http://localhost:3000",                   # opcional: dev local
]

# Se precisar de teste rápido e quiser permitir todas as origens (NÃO recomendado em produção),
# altere ALLOWED_ORIGINS para ["*"] temporariamente.
# =========================

app = FastAPI(title="Agente Carro de Som - Protótipo")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modelo de request
class SearchReq(BaseModel):
    city: str
    state: Optional[str] = None
    radii: Optional[List[int]] = [10000, 30000, 50000]

# Root
@app.get("/")
async def root():
    return "Agente Carro de Som — serviço ativo (root)."

# Health
@app.get("/health")
async def health():
    return "OK"

# Rota principal (protótipo)
@app.post("/api/search_city")
async def search_city(payload: SearchReq):
    """
    Protótipo:
    - Geocode via Nominatim (OpenStreetMap)
    - Retorna JSON com geocoding ou status city_not_geocoded
    """
    if not payload.city or not payload.city.strip():
        raise HTTPException(status_code=400, detail="Informe 'city' no payload.")

    nominatim_url = "https://nominatim.openstreetmap.org/search"
    q = payload.city + (f", {payload.state}" if payload.state else "") + ", Brasil"
    params = {"q": q, "format": "json", "limit": 1}
    headers = {"User-Agent": "SomAgent-Test/1.0 (+contato@exemplo.com)"}

    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            resp = await client.get(nominatim_url, params=params)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Erro ao consultar serviço de geocoding.")
            arr = resp.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Erro de conexão no geocoding: {str(e)}")

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
        "note": "Protótipo: rota funcionando com CORS para seu domínio. Integre Gemini/Places depois."
    }

# Permite rodar com `python app.py` também
if __name__ == "__main__":
    import uvicorn
    # Porta padrão 8000 localmente; Railway sobrescreve via $PORT geralmente
    uvicorn.run("app:app", host="0.0.0.0", port=8000, log_level="info")
