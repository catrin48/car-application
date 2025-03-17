import json
import io
import os
from flask import Flask, render_template, request, Response, session
import itertools
from datetime import datetime, timedelta
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from flask_cors import CORS
import glob

# Flaskアプリ設定
app = Flask(__name__)
CORS(app)  # CORS対応
app.secret_key = "supersecretkey"  # セッション用のキー

# Google Maps Routes API の設定
ROUTES_API_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

# APIキーの取得
with open("config.json", "r") as config_file:
    config = json.load(config_file)
API_KEY = config["API_KEY"]

# 日本語フォントの設定
font_candidates = glob.glob("/usr/share/fonts/**/ipaexg.ttf", recursive=True)
if font_candidates:
    FONT_PATH = font_candidates[0]  # 最初に見つかったフォントを使用
else:
    raise FileNotFoundError("IPAexフォントが見つかりません。フォントをインストールしてください。")

pdfmetrics.registerFont(TTFont("IPAexGothic", FONT_PATH))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # 入力データ取得
        departure_time_str = request.form.get("departure_time")
        departure_time = datetime.strptime(departure_time_str, "%H:%M")
        num_children = int(request.form.get("num_children"))
        current_location_name = request.form.get("current_location_name")
        current_location = request.form.get("current_location")
        children_info = []

        # 子供の情報を取得
        for i in range(1, num_children + 1):
            name = request.form.get(f"child_name_{i}")
            address = request.form.get(f"child_address_{i}")
            time = request.form.get(f"child_time_{i}")
            children_info.append({"name": name, "address": address, "time": time})

        # ルートの全順列を生成
        routes = list(itertools.permutations(children_info))
        route_details = []

        for route in routes:
            waypoints = [current_location] + [child["address"] for child in route]
            distance, duration, arrival_times = calculate_route(waypoints, departure_time)
            route_info = {
                "route": f"{current_location_name} → " + " → ".join([child["name"] for child in route]),
                "distance": distance,
                "duration": duration,
                "arrival_times": [{"name": child["name"], "arrival_time": arrival_times[idx]} for idx, child in enumerate(route)]
            }
            route_details.append(route_info)

        session["route_details"] = route_details
        return render_template("result.html", route_details=route_details)

    return render_template("index.html")

def calculate_route(waypoints, departure_time):
    """
    Google Maps Routes API を使ってルートの距離、時間、到着時刻を計算。
    """
    try:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "routes.distanceMeters,routes.duration"
        }

        # Geocoding APIで住所を緯度・経度に変換
        waypoints_latlng = []
        for address in waypoints:
            latlng = geocode_address(address)
            if latlng:
                waypoints_latlng.append(latlng)
            else:
                return "Error", "Error", ["Error"]

        data = {
            "origin": {"location": {"latLng": waypoints_latlng[0]}},
            "destination": {"location": {"latLng": waypoints_latlng[-1]}},
            "intermediates": [{"location": {"latLng": loc}} for loc in waypoints_latlng[1:-1]],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE_OPTIMAL",
            

        }

        response = requests.post(ROUTES_API_URL, headers=headers, json=data)
        response_json = response.json()

        if "routes" not in response_json:
            print("ERROR: Routes API response is invalid:", response_json)
            return "Error", "Error", ["Error"]

        route = response_json["routes"][0]
        total_distance = route["distanceMeters"] / 1000  # 距離 (km)
        total_duration_sec = int(route["duration"][:-1])  # "21415s" の "s" を除去して秒数に変換
        total_duration = f"{total_duration_sec // 3600} hr { (total_duration_sec % 3600) // 60} min"

        # 到着時刻の計算
        current_time = departure_time
        arrival_times = [current_time.strftime("%H:%M:%S")]

        current_time += timedelta(seconds=total_duration_sec)
        arrival_times.append(current_time.strftime("%H:%M:%S"))

        return f"{total_distance:.2f} km", total_duration, arrival_times

    except Exception as e:
        print(f"ERROR: Exception in calculate_route: {e}")
        return "Error", "Error", ["Error"]

def geocode_address(address):
    """
    Google Maps Geocoding APIを使って住所を緯度・経度に変換
    """
    GEOCODING_API_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": API_KEY
    }
    
    response = requests.get(GEOCODING_API_URL, params=params)
    response_json = response.json()

    if response_json["status"] == "OK":
        location = response_json["results"][0]["geometry"]["location"]
        return {"latitude": location["lat"], "longitude": location["lng"]}
    else:
        print(f"ERROR: Geocoding failed for {address} - {response_json}")
        return None

@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    route_details = session.get("route_details", [])

    selected_index = request.form.get("selected_route")
    if selected_index is None or not route_details:
        return "ルートを選択してください", 400

    selected_index = int(selected_index)
    selected_route = route_details[selected_index]

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("選択されたルート")
    pdf.setFont("IPAexGothic", 12)
    y_position = 750

    pdf.drawString(100, y_position, "=======================")
    y_position -= 20
    pdf.drawString(100, y_position, f"ルート: {selected_route['route']}")
    y_position -= 20
    pdf.drawString(100, y_position, f"総距離: {selected_route['distance']}")
    y_position -= 20
    pdf.drawString(100, y_position, f"総時間: {selected_route['duration']}")
    y_position -= 30

    for item in selected_route["arrival_times"]:
        pdf.drawString(120, y_position, f"{item['name']}: {item['arrival_time']}")
        y_position -= 20

    pdf.drawString(100, y_position, "=======================")
    pdf.save()
    buffer.seek(0)

    response = Response(buffer, mimetype="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=selected_route.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)

