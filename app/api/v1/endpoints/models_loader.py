import os
import asyncio
from ultralytics import YOLO

loaded_models = {}

async def load_models():
    model_directory = 'ia'  # Diretório onde os modelos estão armazenados
    model_files = [f for f in os.listdir(model_directory) if os.path.isfile(os.path.join(model_directory, f))]

    for model_file in model_files:
        model_path = os.path.join(model_directory, model_file)
        model_ia = await asyncio.to_thread(YOLO, model_path)
        loaded_models[model_file] = model_ia
    print("Modelos carregados:", loaded_models)
