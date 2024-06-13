FROM python:3.11-bullseye

ENV PYTHONUNBUFFERED 1
ENV PATH="/root/.local/bin:$PATH"
ENV PYTHONPATH='/'

RUN apt-get update -y && apt-get install -y \
    build-essential \
    libsm6 \
    libxext6 \
    && apt-get clean

RUN python -m pip install --upgrade pip --default-timeout=6000

COPY ./requirements.txt /

RUN pip install --default-timeout=6000 -r /requirements.txt --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip install opencv-python-headless

COPY ./app /app
WORKDIR /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
