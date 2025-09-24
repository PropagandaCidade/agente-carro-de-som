# app.py (Agente de Busca de Carro de Som v3.0 - Busca por Endereço)
import os
import httpx
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
from typing import List, Dict

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

GOOGLE_API_BASE_URL = "https://maps.googleapis.com/maps/api"

def get_google_api_key():
    """Busca a chave da API do Google a partir das variáveis de ambiente."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        logger.error("ERRO CRÍTICO: Variável de ambiente GOOGLE_MAPS_API_KEY não encontrada.")
    return key

def geocode_address(address: str, api_key: str) -> Dict:
    """Converte um endereço (cidade, uf, bairro) em coordenadas."""
    logger.info(f"Geocodificando o endereço: {address}...")
    url = f"{GOOGLE_API_BASE_URL}/geocode/json"
    params = {"address": address, "key": api_key, "language": "pt-BR"}
    
    with httpx.Client() as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    if data['status'] == 'OK' and data.get('results'):
        result = data['results'][0]
        location = result['geometry']['location']
        # Usamos o endereço formatado retornado pelo Google para maior precisão
        formatted_address = result.get('formatted_address', address)
        logger.info(f"Sucesso na geocodificação: {formatted_address} -> {location}")
        return {"location": location, "formatted_address": formatted_address}
    
    logger.warning(f"Geocodificação falhou para '{address}'. Status: {data['status']}")
    return None

def search_nearby_places(location: Dict, radius: int, keywords: List[str], api_key: str) -> Dict:
    """Busca por estabelecimentos próximos usando uma lista de palavras-chave."""
    logger.info(f"Iniciando busca em um raio de {radius}m...")
    all_results = {}
    
    with httpx.Client() as client:
        for keyword in keywords:
            logger.info(f"Buscando por '{keyword}'...")
            url = f"{GOOGLE_API_BASE_URL}/place/nearbysearch/json"
            params = {
                "location": f"{location['lat']},{location['lng']}",
                "radius": radius,
                "keyword": keyword,
                "key": api_key,
                "language": "pt-BR"
            }
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            if data['status'] == 'OK':
                logger.info(f"Encontrados {len(data['results'])} resultados para '{keyword}'.")
                for place in data['results']:
                    place_id = place.get('place_id')
                    # Adiciona apenas se o local tiver um place_id e ainda não estiver na lista
                    if place_id and place_id not in all_results:
                        all_results[place_id] = place
    return all_results

def get_details_and_distances(origin_location: Dict, places: Dict, api_key: str) -> List[Dict]:
    """Busca detalhes (telefone) e calcula a distância por estrada para cada local."""
    if not places:
        return []

    logger.info(f"Calculando distâncias e buscando detalhes para {len(places)} locais...")
    
    destination_place_ids = [f"place_id:{place_id}" for place_id in places.keys()]
    
    distance_url = f"{GOOGLE_API_BASE_URL}/distancematrix/json"
    distance_params = {
        "origins": f"{origin_location['lat']},{origin_location['lng']}",
        "destinations": "|".join(destination_place_ids),
        "key": api_key,
        "language": "pt-BR",
        "units": "metric"
    }
    
    final_results = []
    
    with httpx.Client(timeout=30.0) as client:
        distance_response = client.get(distance_url, params=distance_params).json()
        
        for i, place_id in enumerate(places.keys()):
            place_data = places[place_id]
            
            details_url = f"{GOOGLE_API_BASE_URL}/place/details/json"
            details_params = {
                "place_id": place_id,
                "fields": "name,formatted_address,formatted_phone_number,website,url",
                "key": api_key,
                "language": "pt-BR"
            }
            details_response = client.get(details_url, params=details_params).json()
            
            place_details = details_response.get('result', {})
            distance_info = {}
            
            if distance_response.get('status') == 'OK' and i < len(distance_response['rows'][0]['elements']) and distance_response['rows'][0]['elements'][i]['status'] == 'OK':
                element = distance_response['rows'][0]['elements'][i]
                distance_info = {
                    "distance_text": element['distance']['text'],
                    "distance_meters": element['distance']['value'],
                    "duration_text": element['duration']['text']
                }

            final_results.append({
                "name": place_details.get('name', place_data.get('name')),
                "address": place_details.get('formatted_address', place_data.get('vicinity')),
                "phone": place_details.get('formatted_phone_number'),
                "google_maps_url": place_details.get('url'),
                **distance_info
            })

    final_results.sort(key=lambda x: x.get('distance_meters', float('inf')))
    logger.info("Processamento de detalhes e distâncias concluído.")
    
    return final_results

@app.route('/')
def home():
    return jsonify({"status": "Agente de busca de carro de som v3.0 está online."})

@app.route('/api/find-services', methods=['POST'])
def find_services_endpoint():
    api_key = get_google_api_key()
    if not api_key:
        return jsonify({"error": "O servidor não está configurado corretamente."}), 500

    payload = request.get_json()
    # A MUDANÇA PRINCIPAL ESTÁ AQUI: recebemos 'address' em vez de 'city'
    address = payload.get('address') if payload else None
    if not address:
        return jsonify({"error": "O campo 'address' é obrigatório."}), 400

    # 1. Geocodificar o endereço completo
    geo_info = geocode_address(address, api_key)
    if not geo_info:
        return jsonify({"error": f"Não foi possível encontrar o local: '{address}'."}), 404
    
    center_location = geo_info['location']
    formatted_address = geo_info['formatted_address']

    # 2. Realizar buscas (a lógica de raios continua a mesma)
    search_keywords = ["carro de som", "propaganda volante", "moto som", "anúncio em carro", "bike som"]
    
    logger.info("FASE 1: Busca em raio curto (10km).")
    found_places = search_nearby_places(center_location, 10000, search_keywords, api_key)
    search_radius_used = 10

    if not found_places:
        logger.info("FASE 2: Nenhum resultado no raio curto. Expandindo para raio longo (40km).")
        found_places = search_nearby_places(center_location, 40000, search_keywords, api_key)
        search_radius_used = 40

    # 3. Obter detalhes e calcular distâncias
    final_results = get_details_and_distances(center_location, found_places, api_key)
    
    if not final_results:
        return jsonify({
            "status": "nenhum_servico_encontrado",
            "message": f"Nenhum serviço encontrado em um raio de {search_radius_used}km de {formatted_address}.",
            "address_searched": formatted_address
        })

    return jsonify({
        "status": "servicos_encontrados",
        "address_searched": formatted_address,
        "search_radius_km": search_radius_used,
        "results": final_results
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)