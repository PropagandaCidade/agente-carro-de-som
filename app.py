# app.py (Agente de Busca de Carro de Som v5.0 - Agente Detetive)
import os
import httpx
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import re
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

GOOGLE_API_BASE_URL = "https://maps.googleapis.com/maps/api"

def load_config(filename: str) -> Dict:
    default_config = {"search_keywords": [], "positive_keywords_in_name": [], "negative_keywords_in_name": [], "negative_business_types": []}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"Arquivo de configuração '{filename}' carregado com sucesso.")
            return config
    except Exception as e:
        logger.error(f"Não foi possível carregar '{filename}': {e}. Usando configuração padrão.")
        return default_config

CONFIG = load_config('config.json')
SEARCH_KEYWORDS = CONFIG.get('search_keywords', [])
POSITIVE_KEYWORDS = CONFIG.get('positive_keywords_in_name', [])
NEGATIVE_KEYWORDS = CONFIG.get('negative_keywords_in_name', [])
NEGATIVE_TYPES = CONFIG.get('negative_business_types', [])

def get_google_api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key: logger.error("ERRO CRÍTICO: GOOGLE_MAPS_API_KEY não encontrada.")
    return key

# --- INÍCIO DA LÓGICA DE VALIDAÇÃO INTELIGENTE ---
def is_relevant_business(place_details: Dict) -> bool:
    """Verifica se um negócio é relevante com base em nome e tipo."""
    if not place_details:
        return False
        
    name = place_details.get('name', '').lower()
    types = place_details.get('types', [])

    # 1. Eliminação Imediata por Tipo de Negócio
    if any(neg_type in types for neg_type in NEGATIVE_TYPES):
        logger.info(f"FILTRADO (por tipo): '{place_details.get('name')}' tem tipo indesejado: {types}")
        return False

    # 2. Eliminação por Palavra-Chave Negativa no Nome
    if any(neg_word in name for neg_word in NEGATIVE_KEYWORDS):
        logger.info(f"FILTRADO (por nome negativo): '{place_details.get('name')}' contém palavra negativa.")
        return False
        
    # 3. Validação Positiva Obrigatória no Nome
    if any(pos_word in name for pos_word in POSITIVE_KEYWORDS):
        logger.info(f"APROVADO: '{place_details.get('name')}' parece relevante.")
        return True

    # Se sobreviveu aos filtros negativos mas não tem prova positiva, é descartado.
    logger.info(f"FILTRADO (sem prova positiva): '{place_details.get('name')}' é muito genérico.")
    return False
# --- FIM DA LÓGICA DE VALIDAÇÃO ---

def format_phone_for_whatsapp(phone_number: str) -> Optional[str]:
    if not phone_number: return None
    digits_only = re.sub(r'\D', '', phone_number)
    if len(digits_only) in [11, 10]: return f"https://wa.me/55{digits_only}"
    return None

def geocode_address(address: str, api_key: str) -> Dict:
    params = {"address": address, "key": api_key, "language": "pt-BR"}
    with httpx.Client() as client:
        response = client.get(f"{GOOGLE_API_BASE_URL}/geocode/json", params=params).json()
    if response['status'] == 'OK' and response.get('results'):
        result = response['results'][0]
        return {"location": result['geometry']['location'], "formatted_address": result.get('formatted_address', address)}
    return None

def search_nearby_places(location: Dict, radius: int, api_key: str) -> List[str]:
    """Retorna apenas uma lista de place_ids para investigação."""
    logger.info(f"FASE 1 - BUSCA AMPLA: Procurando candidatos em um raio de {radius}m...")
    place_ids = set()
    with httpx.Client() as client:
        for keyword in SEARCH_KEYWORDS:
            params = {"location": f"{location['lat']},{location['lng']}", "radius": radius, "keyword": keyword, "key": api_key, "language": "pt-BR"}
            response = client.get(f"{GOOGLE_API_BASE_URL}/place/nearbysearch/json", params=params).json()
            if response['status'] == 'OK':
                for place in response['results']:
                    if place.get('place_id'):
                        place_ids.add(place['place_id'])
    logger.info(f"Busca Ampla encontrou {len(place_ids)} candidatos únicos.")
    return list(place_ids)

def investigate_and_process_candidates(origin_location: Dict, place_ids: List[str], api_key: str) -> List[Dict]:
    """Investiga cada candidato, filtra os irrelevantes e calcula distâncias."""
    if not place_ids: return []
    logger.info(f"FASE 2 - INVESTIGAÇÃO: Analisando {len(place_ids)} candidatos...")
    
    final_results = []
    relevant_places = {}

    with httpx.Client(timeout=30.0) as client:
        # Interrogatório: Pega a ficha completa de cada candidato
        for place_id in place_ids:
            details_params = {"place_id": place_id, "fields": "name,formatted_address,formatted_phone_number,url,types", "key": api_key, "language": "pt-BR"}
            details_response = client.get(f"{GOOGLE_API_BASE_URL}/place/details/json", params=details_params).json()
            
            if details_response.get('status') == 'OK':
                place_details = details_response.get('result', {})
                # Julgamento: Decide se o candidato é válido
                if is_relevant_business(place_details):
                    relevant_places[place_id] = place_details
        
        if not relevant_places:
            logger.info("Nenhum candidato passou na fase de investigação.")
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
    api_key = get_google_api_key()
    if not api_key: return jsonify({"error": "Servidor não configurado."}), 500
    address = request.get_json().get('address')
    if not address: return jsonify({"error": "O campo 'address' é obrigatório."}), 400
    geo_info = geocode_address(address, api_key)
    if not geo_info: return jsonify({"error": f"Não foi possível encontrar: '{address}'."}), 404
    
    candidate_place_ids = search_nearby_places(geo_info['location'], 10000, api_key)
    search_radius_used = 10
    if not candidate_place_ids:
        logger.info("Expandindo busca para raio de 40km.")
        candidate_place_ids = search_nearby_places(geo_info['location'], 40000, api_key)
        search_radius_used = 40
        
    final_results = investigate_and_process_candidates(geo_info['location'], candidate_place_ids, api_key)
    
    if not final_results:
        return jsonify({"status": "nenhum_servico_encontrado", "message": f"Nenhum serviço relevante encontrado em um raio de {search_radius_used}km de {geo_info['formatted_address']}.", "address_searched": geo_info['formatted_address']})
    
    return jsonify({"status": "servicos_encontrados", "address_searched": geo_info['formatted_address'], "search_radius_km": search_radius_used, "results": final_results})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)