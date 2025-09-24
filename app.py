# app.py (cole exatamente este arquivo, commit e redeploy)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx

app = FastAPI(title="Agente Carro de Som - Protótipo")

class SearchReq(BaseModel):
    city: str
    state: Optional[str] = None
    radii: Optional[list[int]] = [10000,30000,50000]

@app.get("/")
async def root():
    return "Agente Carro de Som — serviço ativo (root)."

@app.get("/health")
async def health():
    return "OK"

@app.post("/api/search_city")
async def search_city(payload: SearchReq):
    # protótipo: faz geocode simples com Nominatim e retorna
    nominatim = "https://nominatim.openstreetmap.org/search"
    q = f"{payload.city}" + (f", {payload.state}" if payload.state else "") + ", Brasil"
    params = {"q": q, "format": "json", "limit": 1}
    headers = {"User-Agent": "SomAgent-Test/1.0 (+contato@exemplo.com)"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        r = await client.get(nominatim, params=params)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail="Erro no geocoding")
        arr = r.json()
        if not arr:
            return {"status":"city_not_geocoded", "city": payload.city}
        geo = {"lat": float(arr[0]["lat"]), "lon": float(arr[0]["lon"]), "display_name": arr[0].get("display_name")}
    # resposta de teste
    return {
        "status":"ok",
        "city": payload.city,
        "geocoding": geo,
        "note": "Versão protótipo: rota funcionando. Substitua por integração real com Gemini/Places."
    }

# possibilita executar com 'python app.py' também (opcional)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
