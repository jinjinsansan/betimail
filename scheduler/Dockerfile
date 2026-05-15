FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt && \
    python -m pip install --no-cache-dir playwright==1.49.0

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

COPY config.py db.py logging_config.py /app/
COPY tools/daily_lucky_reward.py /app/tools/daily_lucky_reward.py
COPY tools/sync_nftportal_withdraws.py /app/tools/sync_nftportal_withdraws.py

# 既定はラッキー報酬分配スクリプトを実行
CMD ["python", "/app/tools/daily_lucky_reward.py"]
