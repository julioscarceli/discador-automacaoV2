# Dockerfile

# Usa uma imagem Python leve e otimizada
FROM python:3.11-slim

# Define o diretório de trabalho
WORKDIR /app

# Variáveis de Ambiente essenciais para o Playwright em Linux/Railway
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright/browsers \
    PYTHONUNBUFFERED=1

# Instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instala os binários do navegador Chromium e suas dependências de sistema operacional
# O --with-deps garante que os pacotes necessários sejam instalados
RUN python -m playwright install --with-deps chromium

# Copia o restante do código (incluindo o main.py)
COPY . .

# Comando de inicialização do Scheduler principal (roda o loop infinito)
CMD ["python", "main.py"]




