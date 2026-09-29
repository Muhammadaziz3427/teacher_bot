# Teacher Bot — 24/7 uchun kichik konteyner (polling rejimida ishlaydi)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Tashkent

WORKDIR /app

# System packages: tzdata (vaqt zonasi) va curl (healthcheck uchun)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY miniapp ./miniapp
COPY scripts ./scripts
COPY run.py ./

# Ma'lumotlar va loglar doimiy volume'da saqlanadi
RUN mkdir -p /app/data /app/logs
VOLUME ["/app/data", "/app/logs"]

# Konteyner ichida .env emas, environment o'zgaruvchilari ishlatiladi
CMD ["python", "run.py"]
