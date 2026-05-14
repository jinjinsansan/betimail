FROM python:3.12-slim

WORKDIR /app

# 依存パッケージを先にコピーしてキャッシュを効かせる
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# データディレクトリを永続化用ボリュームに
VOLUME ["/app/data"]

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
