FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    g++ gcc \
    gdal-bin libgdal-dev \
    libgeos-dev libproj-dev \
    libsqlite3-mod-spatialite \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app/ /app/

CMD ["python", "main.py"]