FROM python:3.11-bullseye

ENV PYTHONUNBUFFERED=1
ENV PATH="/root/.local/bin:$PATH"
ENV PYTHONPATH='/'

# Instala dependências do sistema necessárias
RUN apt-get update -y && apt-get install -y \
    build-essential \
    libsm6 \
    libxext6 \
    && apt-get clean

# Atualiza o pip
RUN python -m pip install --upgrade pip --default-timeout=6000

# Copia os requisitos do projeto
COPY ./requirements.txt /

# Instala as dependências do Python
RUN pip install --default-timeout=6000 -r /requirements.txt --no-cache-dir

# Copia o código da aplicação
COPY ./app /app

# Define o diretório de trabalho
WORKDIR /app

# Comando para iniciar a aplicação
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
