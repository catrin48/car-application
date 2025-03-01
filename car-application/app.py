import json #JSONデータの取得
import io #io.BytesIO PDF生成のため
from flask import Flask, render_template, request, Response, session #Flask pythonの軽量フレームワーク
import itertools 
from datetime import datetime, timedelta
from googlemaps import Client as GoogleMapsClient #google maps apiを使用して計算するため
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

app = Flask(__name__)
app.secret_key = "supersecretkey"  # セッション用のキー

# Google Maps APIキー
with open("config.json", "r") as config_file:
    config = json.load(config_file)
API_KEY = config["API_KEY"]
gmaps = GoogleMapsClient(key=API_KEY)

# PDFとして出力するときのフォントを登録 
pdfmetrics.registerFont(TTFont('IPAexGothic', '/usr/share/fonts/opentype/ipaexfont-gothic/ipaexg.ttf'))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST": #ユーザーがフォームを送信したときに
        departure_time_str = request.form.get("departure_time") #ユーザーの入力
        departure_time = datetime.strptime(departure_time_str, "%H:%M")
        num_children = int(request.form.get("num_children")) #子供の数
        current_location_name = request.form.get("current_location_name")#現在地の表示名
        current_location = request.form.get("current_location")#現在地の住所
        children_info = []#子供の情報を格納するリストを作る

        for i in range(1, num_children + 1):
            #子供の情報を取得
            name = request.form.get(f"child_name_{i}")
            address = request.form.get(f"child_address_{i}")
            time = request.form.get(f"child_time_{i}")
            children_info.append({"name": name, "address": address, "time": time}) #　リストに実際に格納

        addresses = [child["address"] for child in children_info] #children_infoのリストからaddressをaddressesというリストに格納。["石川県","富山県","福井県"]みたいに
        routes = list(itertools.permutations(children_info))#　リストについて順列を生成する(訪問順序)、例[a,b,c],[a,c,b],[b,a,c],[b,c,a],[c,a,b],[c,b,a]

        route_details = []
        for route in routes:  #routesの各リストについての処理、
            waypoints = [current_location] + [child["address"] for child in route]#各routeのリストから道順を作成する。[出発地点]+[目的地点]*全て
            distance, duration, arrival_times = calculate_route(waypoints, departure_time)#caluculate_routeで実際に計算する、引数としてwaypoints,departure_time 住所と出発時刻
            route_info = {
                "route": " → ".join([current_location_name] + [child["name"] for child in route]),#出力するときのために"自宅" →"A" →"B"のように
                "distance": distance,#距離
                "duration": duration,#経過時間
                "arrival_times": [
                    {"name": child["name"], "arrival_time": arrival_times[idx]} #name: arrival_time:としてリスト形式で保存する
                    for idx, child in enumerate(route)
                ]
            }
            route_details.append(route_info) #route_detailsにroute_infoを格納する

        session["route_details"] = route_details  # 計算結果をセッションに保存
        return render_template("result.html", route_details=route_details)

    return render_template("index.html")

def calculate_route(waypoints, departure_time):#実際にかかる時間を計算する、自身で計算しているわけではなく、Google Map APIを使用して距離、時間の計算をしている。
    try:
        response = gmaps.directions(waypoints[0], waypoints[-1], waypoints=waypoints[1:-1]) #Google Maps APIのdirectionsメソッドの計算、引数(出発地点,目的地、経由地点)
        leg = response[0]["legs"]#距離、時間について メートル、秒、地点も、、、

        total_distance = sum(leg[i]["distance"]["value"] for i in range(len(leg))) / 1000
        total_duration_sec = sum(leg[i]["duration"]["value"] for i in range(len(leg)))
        total_duration = f"{int(total_duration_sec // 60)} min {int(total_duration_sec % 60)} sec"

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
    route_details = session.get("route_details", [])

    selected_index = request.form.get("selected_route")
    if selected_index is None or not route_details:
        return "ルートを選択してください", 400

    selected_index = int(selected_index)
    selected_route = route_details[selected_index]

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("選択されたルート")

    # 日本語フォントを適用　上で登録したものを使用している。
    pdf.setFont("IPAexGothic", 12)

    pdf.drawString(100, 750, "選択されたルート")
    pdf.drawString(100, 730, f"ルート: {selected_route['route']}")
    pdf.drawString(100, 710, f"総距離: {selected_route['distance']}")
    pdf.drawString(100, 690, f"総時間: {selected_route['duration']}")

    y_position = 670
    pdf.drawString(100, y_position, "各地点の到着時刻:")
    y_position -= 20

    for item in selected_route["arrival_times"]:
        pdf.drawString(120, y_position, f"{item['name']}: {item['arrival_time']}")
        y_position -= 20

    pdf.save()
    buffer.seek(0)

    response = Response(buffer, mimetype="application/pdf")
    response.headers["Content-Disposition"] = "attachment; filename=selected_route.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)
