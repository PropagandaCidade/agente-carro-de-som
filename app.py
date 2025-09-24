# app.py (Agente de Busca de Carro de Som v1.0)
import os
import httpx
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging

# Configuração básica de logging para vermos o que o agente está fazendo no console da Railway
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
# Mantemos o CORS aberto, que já sabemos que funciona bem na Railway
CORS(app)

# URL base para as APIs da Plataforma Google Maps
GOOGLE_API_BASE_URL = "https://maps.googleapis.com/maps/api"

def get_google_api_key():
    """Busca a chave da API do Google a partir das variáveis de ambiente."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        logger.error("ERRO CRÍTICO: Variável de ambiente GOOGLE_MAPS_API_KEY não encontrada.")
    return key

def geocode_city(city_name: str, api_key: str) -> dict:
    """Converte um nome de cidade em coordenadas (latitude e longitude)."""
    logger.info(f"Geocodificando a cidade: {city_name}...")
    url = f"{GOOGLE_API_BASE_URL}/geocode/json"
    params = {"address": city_name, "key": api_key, "language": "pt-BR"}
    
    with httpx.Client() as client:
        response = client.get(url, params=params)
        response.raise_for_status() # Lança um erro se a requisição falhar
        data = response.json()

    if data['status'] == 'OK' and data.get('results'):
        location = data['results'][0]['geometry']['location']
        logger.info(f"Sucesso na geocodificação: {location}")
        return location # Retorna {'lat': -23.55, 'lng': -46.63}
    
    logger.warning(f"Geocodificação falhou para '{city_name}'. Status: {data['status']}")
    return None

def search_nearby_places(location: dict, radius: int, keyword: str, api_key: str) -> list:
    """Busca por estabelecimentos próximos a uma coordenada."""
    logger.info(f"Buscando por '{keyword}' em um raio de {radius}m...")
    url = f"{GOOGLE_API_BASE_URL}/place/nearbysearch/json"
    params = {
        "location": f"{location['lat']},{location['lng']}",
        "radius": radius,
        "keyword": keyword,
        "key": api_key,
        "language": "pt-BR"
    }
    
    with httpx.Client() as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    if data['status'] == 'OK':
        logger.info(f"Encontrados {len(data['results'])} resultados para '{keyword}'.")
        return data['results']
        
    logger.warning(f"Busca por '{keyword}' falhou. Status: {data['status']}")
    return []

@app.route('/')
def home():
    return jsonify({"status": "Agente de busca de carro de som está online."})

@app.route('/api/find-services', methods=['POST'])
def find_services_endpoint():
    api_key = get_google_api_key()
    if not api_key:
        return jsonify({"error": "O servidor não está configurado corretamente."}), 500

    payload = request.get_json()
    if not payload or not payload.get('city'):
        return jsonify({"error": "O campo 'city' é obrigatório."}), 400

    city_name = payload['city']
    
    # 1. Obter coordenadas da cidade
    location = geocode_city(city_name, api_key)
    if not location:
        return jsonify({"error": f"Não foi possível encontrar a cidade '{city_name}'."}), 404

    # 2. Realizar buscas
    search_keywords = ["carro de som", "propaganda volante", "moto som", "bicicleta de som"]
    all_results = {} # Usamos um dicionário para evitar resultados duplicados

    # TODO: Implementar a lógica de busca com raios diferentes e cálculo de distância.
    # Por enquanto, vamos fazer uma busca simples com um raio fixo.
    radius = 20000 # Raio de 20km

    for keyword in search_keywords:
        results = search_nearby_places(location, radius, keyword, api_key)
        for place in results:
            place_id = place['place_id']
            if place_id not in all_results:
                # Armazenamos apenas a informação que nos interessa
                all_results[place_id] = {
                    "name": place.get('name'),
                    "address": place.get('vicinity'),
                    "location": place.get('geometry', {}).get('location')
                }
    
    if not all_results:
        return jsonify({
            "status": "nenhum_servico_encontrado",
            "message": f"Nenhum serviço encontrado em um raio de {radius/1000}km de {city_name}."
        })

    # Formata a saída para uma lista
    formatted_results = list(all_results.values())

    return jsonify({
        "status": "servicos_encontrados",
        "city_searched": city_name,
        "center_coordinates": location,
        "results": formatted_results
    })

if __name__ == "__main__":
    # A Railway usará o Procfile, esta parte é para teste local.
    port = int(os.environ.get("PORT", 8000))
    app.run(host='0.0.0.0', port=port)