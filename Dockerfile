# ---------- Etapa 1: compilar Tailwind con binario standalone ----------
FROM alpine:3.19 AS assets
WORKDIR /build

# Certs + curl para descargar el binario
RUN apk add --no-cache curl ca-certificates

# Copiamos lo mínimo necesario para que Tailwind encuentre clases
COPY tailwind.config.js ./tailwind.config.js
COPY app/templates ./app/templates
COPY app/static/css/input.css ./app/static/css/input.css

# Descarga del binario (elige el target correcto para Linux x64)
# Última 3.4.x estable al momento de escribir esto:
RUN curl -sL -o /usr/local/bin/tailwindcss \
  https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.13/tailwindcss-linux-x64 \
  && chmod +x /usr/local/bin/tailwindcss

# Compila el CSS minificado
RUN tailwindcss \
  -c ./tailwind.config.js \
  -i ./app/static/css/input.css \
  -o ./output.css \
  --minify


# ---------- Etapa 2: imagen Python de la app ----------
FROM python:3.12-slim
WORKDIR /app

# Dependencias del sistema que ya usabas + curl para healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc postgresql-client curl \
  && rm -rf /var/lib/apt/lists/*

# Requisitos Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código de la app
COPY . .

# Copiamos el CSS compilado desde la etapa 'assets'
COPY --from=assets /build/output.css /app/app/static/css/output.css

# Usuario no root
RUN useradd --create-home --shell /bin/bash app \
  && chown -R app:app /app
USER app

EXPOSE 8000

# Healthcheck (opcional si ya lo tienes en compose)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/ || exit 1

# Importante: sin --factory (tu app usa create_app() pero el entrypoint ya lo ejecuta)
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "app:app"]
