# app.py (versão de depuração com CORS fixo)
import os
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

# --- INÍCIO DA ALTERAÇÃO PARA DEBUG ---
# Em vez de ler da variável de ambiente, estamos definindo a origem permitida diretamente.
# Isso garante que o valor está 100% correto para o teste.
# Se isso resolver, o problema estava na configuração da variável de ambiente na Railway.
ALLOWED_ORIGINS = ["https://propagandacidadeaudio.com.br"]
# --- FIM DA ALTERAÇÃO PARA DEBUG ---

# O código original para ler a variável de ambiente foi comentado abaixo.
# _allow = os.environ.get("ALLOW_ORIGINS", "*")
# if _allow.strip() == "*":
#     ALLOWED_ORIGINS = ["*"]
# else:
#     ALLOWED_ORIGINS = [o.strip() for o in _allow.split(",") if o.strip()]

app = FastAPI(title="Agente Carro de Som - Protótipo (CORS Fixo para Debug)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS, # Usando a lista definida acima
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "note": "Protótipo: rota funcionando com CORS fixo para depuração."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)