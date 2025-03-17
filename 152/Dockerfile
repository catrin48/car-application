# Python 3.9 の公式イメージを使用
FROM python:3.9

# 作業ディレクトリを設定
WORKDIR /app

# 必要なファイルをコンテナにコピー
COPY requirements.txt .
COPY main.py .
COPY config.json .
COPY templates/ templates/

# 依存パッケージをインストール
RUN pip install --no-cache-dir -r requirements.txt

# IPAexフォントをインストール
RUN apt-get update && apt-get install -y fonts-ipaexfont \
    && fc-cache -fv  # フォントキャッシュを更新

# ポートを指定
EXPOSE 8080

# Flaskアプリを起動
CMD ["gunicorn", "-b", "0.0.0.0:8080", "main:app"]

