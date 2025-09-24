# app.py
# Roda com: uvicorn app:app --host 0.0.0.0 --port 8000
import os
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

# Gemini SDK (google gen ai)
# docs/quickstart: https://ai.google.dev/gemini-api/docs/quickstart
# NOTE: a biblioteca pode variar de nome/versão; ver notas abaixo. [NÃO VERIFICADO]
try:
    from google import genai
except Exception:
    genai = None

app = FastAPI(title="Agente Carro de Som - Protótipo")

class SearchReq(BaseModel):
    city: str
    state: str = None
    radii: list[int] = [10000,30000,50000]

# --- util: geocode com Nominatim (OpenStreetMap) ---
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

async def geocode_city(city: str, state: str|None = None):
    q = city + (f", {state}" if state else "") + ", Brasil"
    params = {"q": q, "format": "json", "limit": 1}
    headers = {"User-Agent": "SomAgent-Test/1.0 (+contato@exemplo.com)"}
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        r = await client.get(NOMINATIM_URL, params=params)
        if r.status_code != 200:
            return None
        arr = r.json()
        if not arr:
            return None
        return {"lat": float(arr[0]["lat"]), "lon": float(arr[0]["lon"]), "display_name": arr[0].get("display_name")}

# --- util: chamar Gemini (via google-genai SDK) ---
# Requer variável de ambiente GEMINI_API_KEY ou GOOGLE_API_KEY conforme quickstart.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

def call_gemini_sync(prompt: str, model: str = "gemini-2.5-flash") -> dict:
    """
    Chamada sincrona ao Gemini via SDK 'google.genai' (se instalado).
    Retorna dicionário com texto gerado ou erro.
    """
    if genai is None:
        return {"error": "SDK google.genai não disponível (instale google-genai)."}
    try:
        # Configura client: o SDK usa variáveis de ambiente automaticamente
        client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else genai.Client()
        # Usa models.generate_content conforme quickstart
        resp = client.models.generate_content(model=model, contents=prompt)
        # A resposta pode ter estrutura diferente dependendo da versão; tentamos extrair texto.
        text = getattr(resp, "text", None) or (resp.get("candidates")[0].get("content") if isinstance(resp, dict) and resp.get("candidates") else str(resp))
        return {"text": text}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/search_city")
async def search_city(payload: SearchReq):
    if not payload.city:
        raise HTTPException(status_code=400, detail="Informe city no payload")
    # 1) geocode
    geo = await geocode_city(payload.city, payload.state)
    if not geo:
        return {"status":"city_not_geocoded", "city": payload.city}
    # 2) gerar prompt simples para Gemini (exemplo de uso)
    prompt = (
        f"Você é um assistente técnico. Gere uma lista curta de frases/keywords para buscar empresas "
        f"que prestem serviço de 'carro de som' ou 'moto som' na cidade de {payload.city}. "
        f"Retorne apenas uma lista separada por vírgulas, sem explicações."
    )
    # 3) chamar Gemini (sincrono via cliente)
    gemini_out = await asyncio.get_event_loop().run_in_executor(None, call_gemini_sync, prompt)

    # 4) montar resposta minimal
    return {
        "status": "ok",
        "city": payload.city,
        "geocoding": geo,
        "gemini_query_suggestions": gemini_out
    }
