# app.py (Agente de Busca de Carro de Som v6.2 - Gemini Robusto)
import os
import httpx
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import re
from typing import List, Dict, Optional

# --- CONFIGURAÇÃO ---
CONFIDENCE_THRESHOLD = 0.50 

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

GOOGLE_API_BASE_URL = "https://maps.googleapis.com/maps/api"
SEARCH_KEYWORDS = ["carro de som", "moto som", "bike som", "propaganda volante", "publicidade"]

PROMPT_TEMPLATE = """
Você é um assistente de prospecção para uma empresa de publicidade que identifica se um negócio oferece serviços de propaganda volante (por exemplo: carro de som, moto som, bike som, som ambulante). 
INSTRUÇÕES (leia e obedeça estritamente):

1) Use APENAS os dados fornecidos abaixo (nome e tipos). Não consulte a web nem outras fontes fora do input.  
2) Analise se o negócio oferece ou provavelmente oferece serviços de propaganda volante. Pense em palavras-chave e categorias típicas: 
   ["carro de som","moto som","bike som","propaganda volante","som ambulante","locução volante","sonorização ambulante","divulgação sonora","carro de propaganda","som automotivo","publicidade sonora"].
3) Responda SOMENTE em JSON, exatamente nesse formato (sem texto adicional, sem explicações):
{
  "answer": "sim" | "não",
  "confidence": float_between_0_and_1,
  "reason": "frase curta explicando a decisão (máx 30 palavras)",
  "keywords_found": ["lista","de","palavras","encontradas"],
  "flags": ["[NÃO VERIFICADO]" | "[INFERÊNCIA]" | "[ESPECULAÇÃO]"]
}

4) Regras para `confidence`:
   - 0.80–1.00 = forte evidência (palavras-chaves diretas, ex.: "carro de som", "moto som", "propaganda volante").
   - 0.50–0.79 = evidência moderada (tipos que sugerem serviços de som, ex.: "serviços de som", "sonorização").
   - 0.00–0.49 = fraca/nenhuma evidência (somente termos genéricos: "entretenimento", "eventos", sem referência a som móvel).

5) Se os dados forem ambíguos ou insuficientes:
   - Use `answer: "não"` **somente** quando existir evidência clara de que NÃO é relevante.
   - Se incerto, preferir `answer: "não"` com `flags`: ["[INFERÊNCIA]","[NÃO VERIFICADO]"] e explique isso em `reason`.

6) Se a saída contiver qualquer suposição, marque-a explicitamente nas `flags` usando `[INFERÊNCIA]` ou `[ESPECULAÇÃO]` e escreva em `reason` a parte que é suposição.

7) Exemplos (input → output JSON):
   - Input: name="CarroSom Silva", types=["car audio", "serviço local"]
     Output: {{"answer":"sim","confidence":0.95,"reason":"Nome contém 'CarroSom' e tipo 'car audio'.","keywords_found":["carro","som","car audio"],"flags":[]}}
   - Input: name="Eventos XYZ", types=["event planner","decoração"]
     Output: {{"answer":"não","confidence":0.2,"reason":"Tipos indicam eventos genéricos sem referência a som móvel.","keywords_found":[],"flags":["[INFERÊNCIA]","[NÃO VERIFICADO]"]}}

DADOS A ANALISAR:
- Nome do negócio: "{name}"
- Tipos (Google): {types}

RETORNE apenas o JSON conforme o esquema acima.
"""

def get_google_api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key: logger.error("ERRO CRÍTICO: GOOGLE_MAPS_API_KEY não encontrada.")
    return key

def configure_gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("ERRO CRÍTICO: GEMINI_API_KEY não encontrada.")
        return None
    genai.configure(api_key=api_key)
    # --- CORREÇÃO: Removemos a exigência de JSON na chamada para torná-la mais robusta ---
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    return model

# --- CÉREBRO DE IA ATUALIZADO E ROBUSTO ---
def is_relevant_with_gemini(place_details: Dict, model) -> bool:
    if not place_details or not model: return False
    name = place_details.get('name', 'N/A')
    types = place_details.get('types', [])
    prompt = PROMPT_TEMPLATE.format(name=name, types=types)
    
    try:
        logger.info(f"GEMINI: Analisando '{name}'...")
        response = model.generate_content(prompt)
        
        # --- CORREÇÃO: Bloco de limpeza e parse seguro da resposta ---
        if not response.parts:
            logger.warning(f"GEMINI: Resposta vazia para '{name}'.")
            return False

        raw_text = response.text.strip()
        # Remove os acentos graves do Markdown se o Gemini os incluir
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()

        result_json = json.loads(raw_text)
        # --- FIM DO BLOCO DE CORREÇÃO ---
        
        answer = result_json.get("answer")
        confidence = result_json.get("confidence", 0)
        reason = result_json.get("reason")

        logger.info(f"GEMINI: Veredito para '{name}': {answer.upper()} (Confiança: {confidence:.2f}). Motivo: {reason}")
        return answer == "sim" and confidence >= CONFIDENCE_THRESHOLD
        
    except json.JSONDecodeError:
        logger.error(f"GEMINI: ERRO DE PARSE. Não foi possível decodificar a resposta para '{name}'. Resposta recebida: {raw_text}")
        return False
    except Exception as e:
        logger.error(f"GEMINI: Erro inesperado ao analisar '{name}': {e}")
        return False

# ... (O restante das funções continua exatamente igual) ...
def format_phone_for_whatsapp(phone_number: str) -> Optional[str]:
    if not phone_number: return None
    digits_only = re.sub(r'\D', '', phone_number)
    if len(digits_only) in [11, 10]: return f"https://wa.me/55{digits_only}"
    return None

def geocode_address(address: str, api_key: str) -> Optional[Dict]:
    params = {"address": address, "key": api_key, "language": "pt-BR"}
    try:
        with httpx.Client() as client:
            response = client.get(f"{GOOGLE_API_BASE_URL}/geocode/json", params=params).json()
        if response['status'] == 'OK' and response.get('results'):
            result = response['results'][0]
            return {"location": result['geometry']['location'], "formatted_address": result.get('formatted_address', address)}
    except Exception as e:
        logger.error(f"Erro na geocodificação: {e}")
    return None

def search_nearby_places(location: Dict, radius: int, api_key: str) -> List[str]:
    logger.info(f"FASE 1 - BUSCA AMPLA: Procurando candidatos em um raio de {radius}m...")
    place_ids = set()
    with httpx.Client() as client:
        for keyword in SEARCH_KEYWORDS:
            params = {"location": f"{location['lat']},{location['lng']}", "radius": radius, "keyword": keyword, "key": api_key, "language": "pt-BR"}
            response = client.get(f"{GOOGLE_API_BASE_URL}/place/nearbysearch/json", params=params).json()
            if response.get('status') == 'OK':
                for place in response.get('results', []):
                    if place.get('place_id'):
                        place_ids.add(place.get('place_id'))
    logger.info(f"Busca Ampla encontrou {len(place_ids)} candidatos únicos.")
    return list(place_ids)

def investigate_and_process_candidates(origin_location: Dict, place_ids: List[str], api_key: str, gemini_model) -> List[Dict]:
    if not place_ids: return []
    logger.info(f"FASE 2 - INVESTIGAÇÃO COM IA: Analisando {len(place_ids)} candidatos...")
    final_results, relevant_places = [], {}
    with httpx.Client(timeout=30.0) as client:
        for place_id in place_ids:
            details_params = {"place_id": place_id, "fields": "name,url,types", "key": api_key, "language": "pt-BR"}
            details_response = client.get(f"{GOOGLE_API_BASE_URL}/place/details/json", params=details_params).json()
            if details_response.get('status') == 'OK':
                place_details = details_response.get('result', {})
                if is_relevant_with_gemini(place_details, gemini_model):
                    full_details_params = {"place_id": place_id, "fields": "name,formatted_address,formatted_phone_number,url", "key": api_key, "language": "pt-BR"}
                    full_details_response = client.get(f"{GOOGLE_API_BASE_URL}/place/details/json", params=full_details_params).json()
                    if full_details_response.get('status') == 'OK':
                        relevant_places[place_id] = full_details_response.get('result', {})
        if not relevant_places:
            logger.info("Nenhum candidato passou na fase de investigação com IA.")
            return []
        logger.info(f"FASE 3 - PROCESSAMENTO: {len(relevant_places)} candidatos aprovados. Calculando distâncias...")
        destination_place_ids = [f"place_id:{pid}" for pid in relevant_places.keys()]
        distance_params = {"origins": f"{origin_location['lat']},{origin_location['lng']}", "destinations": "|".join(destination_place_ids), "key": api_key, "language": "pt-BR", "units": "metric"}
        distance_response = client.get(f"{GOOGLE_API_BASE_URL}/distancematrix/json", params=distance_params).json()
        for i, place_id in enumerate(relevant_places.keys()):
            place_details = relevant_places[place_id]
            distance_info = {}
            if (distance_response.get('status') == 'OK' and distance_response.get('rows') and distance_response['rows'][0].get('elements') and i < len(distance_response['rows'][0]['elements']) and distance_response['rows'][0]['elements'][i].get('status') == 'OK'):
                element = distance_response['rows'][0]['elements'][i]
                distance_info = {"distance_text": element['distance']['text'], "distance_meters": element['distance']['value'], "duration_text": element['duration']['text']}
            phone = place_details.get('formatted_phone_number')
            final_results.append({"name": place_details.get('name'), "address": place_details.get('formatted_address'), "phone": phone, "whatsapp_url": format_phone_for_whatsapp(phone), "google_maps_url": place_details.get('url'), **distance_info})
    final_results.sort(key=lambda x: x.get('distance_meters', float('inf')))
    return final_results

@app.route('/api/find-services', methods=['POST'])
def find_services_endpoint():
    google_api_key = get_google_api_key()
    gemini_model = configure_gemini()
    if not google_api_key or not gemini_model:
        return jsonify({"error": "Servidor não configurado corretamente. Verifique as chaves de API."}), 500
    address = request.get_json().get('address')
    if not address: return jsonify({"error": "O campo 'address' é obrigatório."}), 400
    geo_info = geocode_address(address, google_api_key)
    if not geo_info: return jsonify({"error": f"Não foi possível encontrar: '{address}'."}), 404
    candidate_place_ids = search_nearby_places(geo_info['location'], 10000, google_api_key)
    search_radius_used = 10
    if not candidate_place_ids:
        logger.info("Expandindo busca para raio de 40km.")
        candidate_place_ids = search_nearby_places(geo_info['location'], 40000, google_api_key)
        search_radius_used = 40
    final_results = investigate_and_process_candidates(geo_info['location'], candidate_place_ids, google_api_key, gemini_model)
    if not final_results:
        return jsonify({"status": "nenhum_servico_encontrado", "message": f"Nenhum serviço relevante encontrado em um raio de {search_radius_used}km de {geo_info['formatted_address']}.", "address_searched": geo_info['formatted_address']})
    return jsonify({"status": "servicos_encontrados", "address_searched": geo_info['formatted_address'], "search_radius_km": search_radius_used, "results": final_results})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)