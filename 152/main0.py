import json
import io
import os
from flask import Flask, render_template, request, Response, session
import itertools
from datetime import datetime, timedelta
from googlemaps import Client as GoogleMapsClient
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

# Google Maps APIキーを取得
with open("config.json", "r") as config_file:
    config = json.load(config_file)
API_KEY = config["API_KEY"]
gmaps = GoogleMapsClient(key=API_KEY)
font_candidates = glob.glob("/usr/share/fonts/**/ipaexg.ttf", recursive=True)
if font_candidates:
    FONT_PATH = font_candidates[0]  # 最初に見つかったフォントを使用
else:
    raise FileNotFoundError("IPAexフォントが見つかりません。フォントをインストールしてください。")

# **日本語フォント設定**
#FONT_PATH = "/usr/share/fonts/opentype/ipaexfont/ipaexg.ttf"
#if not os.path.exists(FONT_PATH):
 #   raise FileNotFoundError(f"フォントが見つかりません: {FONT_PATH}")

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

        # セッションにルート情報を保存（PDF生成用）
        session["route_details"] = route_details

        return render_template("result.html", route_details=route_details)

    return render_template("index.html")

def calculate_route(waypoints, departure_time):
    """
    Google Maps APIを使ってルートの距離、時間、到着時刻を計算。
    """
    try:
        response = gmaps.directions(waypoints[0], waypoints[-1], waypoints=waypoints[1:-1])
        leg = response[0]["legs"]

        # 総距離と総時間を計算
        total_distance = sum(leg[i]["distance"]["value"] for i in range(len(leg))) / 1000
        total_duration_sec = sum(leg[i]["duration"]["value"] for i in range(len(leg)))
        total_duration = f"{int(total_duration_sec // 60)} min {int(total_duration_sec % 60)} sec"

        # 到着時刻を計算
        current_time = departure_time
        arrival_times = []

        for i in range(len(leg)):
            current_time += timedelta(seconds=leg[i]["duration"]["value"])
            arrival_times.append(current_time.strftime("%H:%M:%S"))

        return f"{total_distance:.2f} km", total_duration, arrival_times
    except Exception as e:
        return "Error", "Error", ["Error"]

@app.route("/download_pdf", methods=["POST"])
def download_pdf():
    """
    選択したルートの情報をPDF化し、日本語対応フォントを使う
    """
    route_details = session.get("route_details", [])

    selected_index = request.form.get("selected_route")
    if selected_index is None or not route_details:
        return "ルートを選択してください", 400

    selected_index = int(selected_index)
    selected_route = route_details[selected_index]

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("選択されたルート")

    # **日本語フォントを適用**
    pdf.setFont("IPAexGothic", 12)
    y_position = 750

    # PDF内容
    pdf.drawString(100, y_position, "=======================")
    y_position -= 20
    pdf.drawString(100, y_position, "選択されたルート")
    y_position -= 20
    pdf.drawString(100, y_position, "=======================")
    y_position -= 30

    pdf.drawString(100, y_position, f"ルート: {selected_route['route']}")
    y_position -= 20
    pdf.drawString(100, y_position, f"総距離: {selected_route['distance']}")
    y_position -= 20
    pdf.drawString(100, y_position, f"総時間: {selected_route['duration']}")
    y_position -= 30

    pdf.drawString(100, y_position, "-----------------------")
    y_position -= 20
    pdf.drawString(100, y_position, "各地点の到着時刻:")
    y_position -= 20

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

