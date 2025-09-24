# app.py (versão convertida para Flask para o teste final)
import os
import httpx
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)

# Configurando o CORS com Flask-CORS, assim como no seu outro projeto que funciona.
# Lendo a origem da variável de ambiente.
allowed_origin = os.environ.get("ALLOW_ORIGINS", "*")
CORS(app, origins=[allowed_origin])

@app.route("/")
def root():
    return jsonify({"message": "Agente Carro de Som — serviço ativo (Flask)."})

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/search_city", methods=["POST"])
def search_city():
    payload = request.get_json()
    if not payload or not payload.get('city'):
        return jsonify({"error": "Informe 'city' no payload."}), 400

    city = payload['city']
    state = payload.get('state')

    nominatim_url = "https://nominatim.openstreetmap.org/search"
    q = city + (f", {state}" if state else "") + ", Brasil"
    params = {"q": q, "format": "json", "limit": 1}
    headers = {"User-Agent": "SomAgent-Test/1.0 (+contato@exemplo.com)"}

    try:
        # Usando 'requests' que é síncrono, ideal para Flask
        resp = httpx.get(nominatim_url, params=params, headers=headers, timeout=15.0)
        resp.raise_for_status()
        arr = resp.json()
    except Exception as e:
        return jsonify({"error": f"Erro ao consultar geocoding: {str(e)}"}), 502

    if not arr:
        return jsonify({"status": "city_not_geocoded", "city": city})

    first = arr[0]
    geocoding = {
        "lat": float(first.get("lat")),
        "lon": float(first.get("lon")),
        "display_name": first.get("display_name")
    }

    return jsonify({
        "status": "ok",
        "city": city,
        "geocoding": geocoding
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Esta parte é apenas para teste local, a Railway usará o Procfile.
    app.run(host="0.0.0.0", port=port)