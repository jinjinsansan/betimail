FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

RUN pip install --no-cache-dir playwright==1.49.0

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app
COPY tools/daily_lucky_reward.py /app/tools/

# 既定はラッキー報酬分配スクリプトを実行
CMD ["python", "/app/tools/daily_lucky_reward.py"]
