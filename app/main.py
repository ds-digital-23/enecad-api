# -*- coding: utf-8 -*-

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import os
import asyncio
from ultralytics import YOLO
from core.configs import settings
from api.v1.api import api_router



loaded_models = {}


@asynccontextmanager
async def lifespan(application: FastAPI):
    await load_models()
    yield


async def load_models():
    model_directory = 'ia'
    model_files = [f for f in os.listdir(model_directory) if os.path.isfile(os.path.join(model_directory, f))]

    for model_file in model_files:
        model_path = os.path.join(model_directory, model_file)
        model_ia = await asyncio.to_thread(YOLO, model_path)
        loaded_models[model_file] = model_ia
    print("Modelos carregados:", loaded_models)


app = FastAPI(
    title='Enecad - API',
    version='1.0.0',
    description='API desenvolvida para a Enecad a fim de detectar objetos em rede de distribuição via modelos de visão computacional.',
    license="Licença Comercial Enecad",
    lifespan=lifespan
)


@app.get("/")
def health_check():
    content = {"mensagem": "Bem-vindo à Enecad-API para detecção de objetos em rede de distribuição!"}
    return JSONResponse(content=content, media_type="application/json; charset=utf-8")


app.include_router(api_router, prefix=settings.API_VERSION)
