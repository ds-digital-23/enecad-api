import logging
import os
import asyncio
import time
import json
import httpx
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from ultralytics import YOLO
from models.solicitacao_model import SolicitacaoModel
from models.usuario_model import UsuarioModel
from models.modelo_model import ModeloModel
from schemas.modelo_schema import ModeloResponse
from schemas.solicitacao_schema import SolicitacaoCreate, PolesRequest, Resultado
from core.deps import get_session, get_current_user

# logging.getLogger('ultralytics').setLevel(logging.ERROR)

router = APIRouter()
semaphore = asyncio.Semaphore(5)

model_path = 'ia/model_ip_v1.3.pt'

def test_model_loading():
    try:
        model = YOLO(model_path)
        logging.info("Model loaded successfully")
    except Exception as e:
        logging.error(f"Error loading model: {e}")


loaded_model = None


async def load_model():
    global loaded_model
    if loaded_model is None:
        logging.info(f"Loading model from {model_path}")
        try:
            loaded_model = await asyncio.to_thread(YOLO, model_path)
            logging.info("Model loaded successfully")
        except Exception as e:
            logging.error(f"Error loading model: {e}")
            raise e
    return loaded_model


async def process_batch_images(images: List[str]) -> Dict[str, bool]:
    async with semaphore:
        model = await load_model()
        detection_results = await asyncio.to_thread(model.predict, images, stream=True)

    results = {}
    for image, result in zip(images, detection_results):
        results[image] = any(len(res.boxes) > 0 for res in result)

    return results


async def process_images(images: List[str], photo_ids: List[int]) -> List[Resultado]:
    start_time = time.time()
    detection_results = await process_batch_images(images)
    end_time = time.time()
    logging.info(f"Processed batch of {len(images)} images in {end_time - start_time} seconds")

    resultados = []
    for photo_id, image in zip(photo_ids, images):
        detection_result = detection_results[image]
        resultados.append(Resultado(PhotoId=photo_id, URL=image, Resultado={"model_ip_v1.3.pt": detection_result}))

    return resultados


async def detect_objects(request: PolesRequest, solicitacao_id: int):
    response = {solicitacao_id: []}
    batch_size = 10  # Define o tamanho do lote de processamento
    for pole in request.Poles:
        images = [photo.URL for photo in pole.Photos]
        photo_ids = [photo.PhotoId for photo in pole.Photos]
        for i in range(0, len(images), batch_size):
            batch_images = images[i:i+batch_size]
            batch_photo_ids = photo_ids[i:i+batch_size]
            results = await process_images(batch_images, batch_photo_ids)
            pole_results = {"PoleId": pole.PoleId, "Photos": [result.model_dump() for result in results]}
            response[solicitacao_id].append(pole_results)

    os.makedirs('results', exist_ok=True)
    response_file_path = os.path.join('results', f"solicitacao_{solicitacao_id}.json")
    with open(response_file_path, 'w') as response_file:
        json.dump(response, response_file, indent=4)

    if request.webhook_url:
        async with httpx.AsyncClient() as client:
            await client.post(str(request.webhook_url), json=response)

    return response


@router.get("/obter_modelo/{modelo_id}", response_model=List[ModeloResponse])
async def obter_modelo(modelo_id: int, db: AsyncSession = Depends(get_session), usuario_logado: UsuarioModel = Depends(get_current_user)):
    async with db as session:
        query = select(ModeloModel).filter(ModeloModel.modelo_id == modelo_id, ModeloModel.status == 1)
        result = await session.execute(query)
        modelos = result.scalars().unique().all()

        if not modelos:
            raise HTTPException(status_code=404, detail="Nenhum modelo ativo encontrado")

        return modelos


@router.get("/obter_solicitacao/{solicitacao_id}", response_model=List[SolicitacaoCreate])
async def obter_solicitacao(solicitacao_id: int, db: AsyncSession = Depends(get_session), usuario_logado: UsuarioModel = Depends(get_current_user)):
    async with db as session:
        query = select(SolicitacaoModel).filter(SolicitacaoModel.id == solicitacao_id)
        result = await session.execute(query)
        solicitacao = result.scalars().unique().one_or_none()

        if not solicitacao:
            raise HTTPException(status_code=404, detail="Nenhuma solicitação encontrada")

        if solicitacao.status == "Concluído":
            response_file_path = os.path.join('results', f"solicitacao_{solicitacao_id}.json")
            if not os.path.exists(response_file_path):
                raise HTTPException(status_code=404, detail="Arquivo de resultado não encontrado")
            return FileResponse(path=response_file_path, filename=f"solicitacao_{solicitacao_id}.json", media_type='application/json')

        return [solicitacao]


async def update_status(solicitacao_id: int, status: str, db: AsyncSession):
    async with db as session:
        query = select(SolicitacaoModel).filter(SolicitacaoModel.id == solicitacao_id)
        result = await session.execute(query)
        solicitacao = result.scalars().unique().one_or_none()
        if solicitacao:
            solicitacao.status = status
            await session.commit()
            await session.refresh(solicitacao)


async def trigger_model_and_detection_tasks(solicitacao_id: int, db: AsyncSession, poles_request: PolesRequest):
    async with db as session:
        try:
            logging.info(f"Triggering detection tasks for solicitation {solicitacao_id}")
            detection_results = await detect_objects(request=poles_request, solicitacao_id=solicitacao_id)
            await update_status(solicitacao_id=solicitacao_id, status='Concluído', db=session)
            logging.info(f"Detection tasks completed for solicitation {solicitacao_id}")
            return detection_results
        except Exception as e:
            logging.error(f"Error during detection tasks for solicitation {solicitacao_id}: {e}")
            await update_status(solicitacao_id=solicitacao_id, status='Falhou', db=session)
            raise e


@router.post("/", response_model=SolicitacaoCreate)
async def criar_solicitacao(poles_request: PolesRequest, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_session), usuario_logado: UsuarioModel = Depends(get_current_user)):
    total_poles = len(poles_request.Poles)
    total_photos = sum(len(pole.Photos) for pole in poles_request.Poles)

    if total_poles > 100:
        raise HTTPException(status_code=400, detail="Número de postes não pode ser maior que 100.")

    nova_solicitacao: SolicitacaoModel = SolicitacaoModel(status="Em andamento", postes=total_poles, imagens=total_photos, usuario_id=usuario_logado.id)

    async with db as session:
        session.add(nova_solicitacao)
        await session.commit()
        await session.refresh(nova_solicitacao)

        logging.info(f"Created new solicitation with id {nova_solicitacao.id}")
        background_tasks.add_task(trigger_model_and_detection_tasks, nova_solicitacao.id, session, poles_request)

        return {"id": nova_solicitacao.id, "status": nova_solicitacao.status, "postes": nova_solicitacao.postes, "imagens": nova_solicitacao.imagens}

# Função para testar o carregamento do modelo isoladamente
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_model_loading()
    asyncio.run(load_model())
