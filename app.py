# app.py (v7.1 - Correção Final de Sintaxe)
import os
import httpx
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import re
from typing import List, Dict, Optional
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

GOOGLE_API_BASE_URL = "https://maps.googleapis.com/maps/api"

def load_config(filename: str) -> Dict:
    default_config = {
        "confidence_threshold": 0.5,
        "search_keywords": ["carro de som", "publicidade"],
        "prompt_template": "Prompt padrão de emergência: analise {name} e {types} e responda com 'sim' ou 'não'."
    }
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"Arquivo de configuração '{filename}' carregado com sucesso.")
            return config
    except Exception as e:
        logger.error(f"ERRO CRÍTICO: Não foi possível carregar ou ler o arquivo '{filename}': {e}. Usando configuração padrão.")
        return default_config

CONFIG = load_config('config.json')
CONFIDENCE_THRESHOLD = CONFIG.get('confidence_threshold', 0.5)
SEARCH_KEYWORDS = CONFIG.get('search_keywords', [])
PROMPT_TEMPLATE = CONFIG.get('prompt_template', "")

def get_google_api_key():
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key: logger.error("DIAGNÓSTICO: Variável GOOGLE_MAPS_API_KEY está VAZIA.")
    return key

def configure_gemini():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("DIAGNÓSTICO: Variável GEMINI_API_KEY está VAZIA.")
            return None
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest', generation_config={"response_mime_type": "application/json"})
        return model
    except Exception as e:
        logger.error(f"DIAGNÓSTICO: CRASH AO CONFIGURAR GEMINI. Detalhes: {e}", exc_info=True)
        return None

def is_relevant_with_gemini(place_details: Dict, model) -> bool:
    if not place_details or not model or not PROMPT_TEMPLATE: return False
    name = place_details.get('name', 'N/A')
    types = place_details.get('types', [])
    prompt = PROMPT_TEMPLATE.format(name=name, types=types)
    try:
        logger.info(f"GEMINI: Analisando '{name}'...")
        response = model.generate_content(prompt)
        result_json = json.loads(response.text)
        answer = result_json.get("answer")
        confidence = result_json.get("confidence", 0)
        reason = result_json.get("reason")
        logger.info(f"GEMINI: Veredito para '{name}': {answer.upper()} (Confiança: {confidence:.2f}). Motivo: {reason}")
        return answer == "sim" and confidence >= CONFIDENCE_THRESHOLD
    except Exception as e:
        logger.error(f"GEMINI: Erro inesperado ao analisar '{name}': {e}. Resposta recebida: {getattr(response, 'text', 'N/A')}")
        return False

def format_phone_for_whatsapp(phone_number: str) -> Optional[str]:
    if not phone_number: return None
    digits_only = re.sub(r'\D', '', phone_number)
    if len(digits_only) in:
        return f"https://wa.me/55{digits_only}"
    return None

def geocode_address(address: str, api_key: str) -> Optional[Dict]:
    params = {"address": address, "key": api_key, "language": "pt-BR"}
    try:
        with httpx.Client() as client:
            response = client.get(f"{GOOGLE_API_BASE_URL}/geocode/json", params=params).json()
        if response['status'] == 'OK' and response.get('results'):
            result = response['results']
            return {"location": result['geometry']['location'], "formatted_address": result.get('formatted_address', address)}
    except Exception as e:
        logger.error(f"Erro na geocodificação: {e}")
    return None

def search_nearby_places(location: Dict, radius: int, api_key: str) -> List[str]:
    logger.info(f"FASE 1 - BUSCA AMPLA: Procurando candidatos em raio de {radius}m...")
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
            if (distance_response.get('status') == 'OK' and distance_response.get('rows') and distance_response['rows'].get('elements') and i < len(distance_response['rows']['elements']) and distance_response['rows']['elements'][i].get('status') == 'OK'):
                element = distance_response['rows']['elements'][i]
                distance_info = {"distance_text": element['distance']['text'], "distance_meters": element['distance']['value'], "duration_text": element['duration']['text']}
            phone = place_details.get('formatted_phone_number')
            final_results.append({"name": place_details.get('name'), "address": place_details.get('formatted_address'), "phone": phone, "whatsapp_url": format_phone_for_whatsapp(phone), "google_maps_url": place_details.get('url'), **distance_info})
    final_results.sort(key=lambda x: x.get('distance_meters', float('inf')))
    return final_results

@app.route('/api/find-services', methods=['POST'])
def find_services_endpoint():
    gemini_model = configure_gemini()
    if not gemini_model:
        return jsonify({"error": "Falha crítica na inicialização do serviço de IA. Verifique os logs do servidor."}), 500
    google_api_key = get_google_api_key()
    if not google_api_key:
        return jsonify({"error": "Chave da API do Google Maps não configurada."}), 500
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

# --- CORREÇÃO FINAL: Removido o bloco if __name__ == "__main__": que causava o erro ---
