# app.py (Agente de Busca de Carro de Som v4.3 - Configuração via JSON)
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
    """Carrega a configuração de busca (palavras-chave) de um arquivo JSON."""
    default_config = {"search_keywords": [], "negative_keywords": []}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Log para confirmar que o arquivo foi lido corretamente
            logger.info(f"Arquivo '{filename}' carregado com sucesso.")
            logger.info(f"Filtro ativo com {len(config.get('negative_keywords', []))} palavras negativas.")
            return config
    except FileNotFoundError:
        logger.error(f"ARQUIVO DE CONFIGURAÇÃO '{filename}' NÃO ENCONTRADO! O filtro de palavras não funcionará.")
        return default_config
    except json.JSONDecodeError:
        logger.error(f"ERRO DE SINTAXE NO ARQUIVO '{filename}'! Verifique se o JSON é válido.")
        return default_config

# --- MUDANÇA PRINCIPAL: Carrega as palavras do arquivo JSON ---
CONFIG = load_config('config.json')
SEARCH_KEYWORDS = CONFIG.get('search_keywords', ["publicidade volante"])
NEGATIVE_KEYWORDS = CONFIG.get('negative_keywords', [])

def get_google_api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        logger.error("ERRO CRÍTICO: Variável de ambiente GOOGLE_MAPS_API_KEY não encontrada.")
    return key

def format_phone_for_whatsapp(phone_number: str) -> Optional[str]:
    if not phone_number: return None
    digits_only = re.sub(r'\D', '', phone_number)
    if len(digits_only) in [11, 10]: return f"https://wa.me/55{digits_only}"
    return None

def geocode_address(address: str, api_key: str) -> Dict:
    logger.info(f"Geocodificando: {address}...")
    url = f"{GOOGLE_API_BASE_URL}/geocode/json"
    params = {"address": address, "key": api_key, "language": "pt-BR"}
    with httpx.Client() as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    if data['status'] == 'OK' and data.get('results'):
        result = data['results'][0]
        return {"location": result['geometry']['location'], "formatted_address": result.get('formatted_address', address)}
    logger.warning(f"Geocodificação falhou para '{address}'. Status: {data['status']}")
    return None

def search_nearby_places(location: Dict, radius: int, api_key: str) -> Dict:
    logger.info(f"Iniciando busca em raio de {radius}m...")
    all_results = {}
    with httpx.Client() as client:
        for keyword in SEARCH_KEYWORDS:
            params = {"location": f"{location['lat']},{location['lng']}", "radius": radius, "keyword": keyword, "key": api_key, "language": "pt-BR"}
            response = client.get(f"{GOOGLE_API_BASE_URL}/place/nearbysearch/json", params=params)
            data = response.json()
            if data['status'] == 'OK':
                for place in data['results']:
                    place_name = place.get('name', '').lower()
                    if any(neg_word in place_name for neg_word in NEGATIVE_KEYWORDS):
                        logger.info(f"FILTRADO: '{place.get('name')}' descartado.")
                        continue
                    place_id = place.get('place_id')
                    if place_id and place_id not in all_results:
                        all_results[place_id] = place
    logger.info(f"Busca concluída com {len(all_results)} resultados únicos e filtrados.")
    return all_results

def get_details_and_distances(origin_location: Dict, places: Dict, api_key: str) -> List[Dict]:
    if not places: return []
    logger.info(f"Processando detalhes para {len(places)} locais...")
    destination_place_ids = [f"place_id:{pid}" for pid in places.keys()]
    distance_params = {"origins": f"{origin_location['lat']},{origin_location['lng']}", "destinations": "|".join(destination_place_ids), "key": api_key, "language": "pt-BR", "units": "metric"}
    final_results = []
    with httpx.Client(timeout=30.0) as client:
        distance_response = client.get(f"{GOOGLE_API_BASE_URL}/distancematrix/json", params=distance_params).json()
        for i, place_id in enumerate(places.keys()):
            details_params = {"place_id": place_id, "fields": "name,formatted_address,formatted_phone_number,url", "key": api_key, "language": "pt-BR"}
            details_response = client.get(f"{GOOGLE_API_BASE_URL}/place/details/json", params=details_params).json()
            place_details = details_response.get('result', {})
            distance_info = {}
            if (distance_response.get('status') == 'OK' and distance_response.get('rows') and distance_response['rows'][0].get('elements') and i < len(distance_response['rows'][0]['elements']) and distance_response['rows'][0]['elements'][i].get('status') == 'OK'):
                element = distance_response['rows'][0]['elements'][i]
                distance_info = {"distance_text": element['distance']['text'], "distance_meters": element['distance']['value'], "duration_text": element['duration']['text']}
            phone = place_details.get('formatted_phone_number')
            final_results.append({"name": place_details.get('name', places[place_id].get('name')), "address": place_details.get('formatted_address', places[place_id].get('vicinity')), "phone": phone, "whatsapp_url": format_phone_for_whatsapp(phone), "google_maps_url": place_details.get('url'), **distance_info})
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
    
    found_places = search_nearby_places(geo_info['location'], 10000, api_key)
    search_radius_used = 10
    if not found_places:
        logger.info("Expandindo busca para raio de 40km.")
        found_places = search_nearby_places(geo_info['location'], 40000, api_key)
        search_radius_used = 40
        
    final_results = get_details_and_distances(geo_info['location'], found_places, api_key)
    
    if not final_results:
        return jsonify({"status": "nenhum_servico_encontrado", "message": f"Nenhum serviço de propaganda volante encontrado em um raio de {search_radius_used}km de {geo_info['formatted_address']}.", "address_searched": geo_info['formatted_address']})
    
    return jsonify({"status": "servicos_encontrados", "address_searched": geo_info['formatted_address'], "search_radius_km": search_radius_used, "results": final_results})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)