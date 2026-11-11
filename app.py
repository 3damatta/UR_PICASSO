"""
UR_PICASSO - Servidor Web Principal (FastAPI + WebSockets)
==========================================================
Interface responsiva e leve para convidados e operadores em eventos.
Roda perfeitamente no Raspberry Pi 3B+ servindo o Wi-Fi Hotspot.
"""

import os
import json
import base64
import asyncio
import logging
import threading
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from core.ur_driver import UR3PicassoDriver
from core.vision_pipeline import CartoonVisionPipeline
from core.vectorizer import TrajectoryOptimizer
from core.camera import CameraManager
from core.calibration import CalibrationManager

# Configuração de Logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger("UR_Picasso_App")

# Carrega Configurações
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

# Inicializa Componentes Core
robot_driver = UR3PicassoDriver(config)
vision_pipe = CartoonVisionPipeline(config)
vectorizer = TrajectoryOptimizer(config)
camera_mgr = CameraManager(config)
calib_mgr = CalibrationManager(robot_driver, CONFIG_PATH)

# Estado Global em Memória
app_state = {
    "last_raw_image": None,
    "last_preview_base64": None,
    "current_strokes": [],
    "current_svg": "",
    "selected_profile": config.get("drawing", {}).get("speed_profile", "ultra_fast"),
    "drawing_status": "idle", # "idle", "drawing", "completed", "error"
    "progress_pct": 0.0,
    "status_message": "Pronto para receber convidados."
}

# Inicializa FastAPI
app = FastAPI(title="UR Picasso - Event Portrait Robot")

# Monta arquivos estáticos e templates
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
os.makedirs(os.path.join(static_dir, "css"), exist_ok=True)
os.makedirs(os.path.join(static_dir, "js"), exist_ok=True)

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(templates_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

# Gerenciador de WebSockets para Notificações em Tempo Real
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(data)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()
loop = asyncio.get_event_loop()

def notify_progress_sync(progress: float, message: str):
    """Callback síncrono chamado pelo UR driver que repassa para o WebSocket assíncrono."""
    app_state["progress_pct"] = progress
    app_state["status_message"] = message
    if progress >= 100.0:
        app_state["drawing_status"] = "completed"
    
    payload = {
        "event": "progress",
        "progress": progress,
        "message": message,
        "status": app_state["drawing_status"]
    }
    try:
        asyncio.run_coroutine_threadsafe(ws_manager.broadcast(payload), loop)
    except Exception:
        pass


# ── ROTAS DA INTERFACE WEB ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    """Página principal da dashboard para convidados e operador."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "robot_ip": robot_driver.robot_ip,
        "paper_format": config.get("paper", {}).get("format", "A6"),
        "profiles": config.get("drawing", {}).get("profiles", {})
    })


@app.get("/video_feed")
def video_feed():
    """Streaming de vídeo ao vivo da Webcam USB para exibição na tela."""
    return StreamingResponse(
        camera_mgr.generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


# ── ROTAS DE API REST ───────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Retorna o status completo do robô, câmera e desenho atual."""
    is_connected = robot_driver.check_connection()
    return {
        "robot_connected": is_connected,
        "robot_ip": robot_driver.robot_ip,
        "drawing_status": app_state["drawing_status"],
        "progress_pct": app_state["progress_pct"],
        "status_message": app_state["status_message"],
        "has_processed_art": len(app_state["current_strokes"]) > 0,
        "stroke_count": len(app_state["current_strokes"]),
        "selected_profile": app_state["selected_profile"]
    }


def _process_image_common(img_bgr: np.ndarray, profile: str) -> Dict[str, Any]:
    """Rotina compartilhada para processar a foto e gerar o desenho cartoon."""
    app_state["last_raw_image"] = img_bgr.copy()
    app_state["selected_profile"] = profile

    # 1. Processa imagem pelo pipeline cartoon
    preview_img, skeleton = vision_pipe.process_to_cartoon_lines(img_bgr, profile=profile)

    # 2. Vetoriza e otimiza a trajetória com TSP
    strokes = vectorizer.extract_and_optimize(skeleton, profile_name=profile)
    app_state["current_strokes"] = strokes

    # 3. Gera SVG vetorial
    svg_str = vectorizer.strokes_to_svg(strokes)
    app_state["current_svg"] = svg_str

    # 4. Codifica imagem de preview para base64
    _, buf = cv2.imencode('.jpg', preview_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64_str = base64.b64encode(buf).decode('utf-8')
    app_state["last_preview_base64"] = b64_str

    profile_cfg = config.get("drawing", {}).get("profiles", {}).get(profile, {})
    est_time = profile_cfg.get("approx_time_s", 60)

    return {
        "success": True,
        "stroke_count": len(strokes),
        "estimated_time_s": est_time,
        "preview_image_base64": b64_str,
        "svg": svg_str
    }


@app.post("/api/capture")
async def capture_from_camera(profile: str = Form("ultra_fast")):
    """Captura foto ao vivo da webcam e converte em desenho linear cartoon."""
    frame = camera_mgr.capture_photo()
    if frame is None:
        return JSONResponse(status_code=500, content={"success": False, "error": "Falha ao capturar da webcam."})

    result = _process_image_common(frame, profile)
    return result


@app.post("/api/upload")
async def upload_photo(file: UploadFile = File(...), profile: str = Form("ultra_fast")):
    """Recebe uma foto enviada do celular ou computador do convidado."""
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return JSONResponse(status_code=400, content={"success": False, "error": "Imagem inválida ou corrompida."})

    result = _process_image_common(img, profile)
    return result


@app.post("/api/reprocess")
async def reprocess_art(profile: str = Form(...)):
    """Reprocessa a foto atual com um perfil diferente de detalhamento/velocidade."""
    if app_state["last_raw_image"] is None:
        return JSONResponse(status_code=400, content={"success": False, "error": "Nenhuma foto carregada."})

    result = _process_image_common(app_state["last_raw_image"], profile)
    return result


@app.post("/api/draw")
async def start_drawing():
    """Inicia o desenho físico no robô UR3."""
    if not app_state["current_strokes"]:
        return JSONResponse(status_code=400, content={"success": False, "error": "Nenhum desenho pronto para executar."})

    if robot_driver.is_drawing:
        return JSONResponse(status_code=400, content={"success": False, "error": "O robô já está desenhando neste momento."})

    app_state["drawing_status"] = "drawing"
    app_state["progress_pct"] = 0.0
    app_state["status_message"] = "Iniciando desenho no UR3..."

    # Executa em thread separada para não travar o servidor FastAPI
    def run_robot_task():
        success = robot_driver.draw_portrait(
            app_state["current_strokes"],
            progress_callback=notify_progress_sync
        )
        if success:
            app_state["drawing_status"] = "completed"
            app_state["status_message"] = "Desenho finalizado! Retire seu retrato."
        else:
            app_state["drawing_status"] = "error" if not robot_driver.abort_requested else "idle"
            app_state["status_message"] = "Desenho cancelado ou interrompido."

    t = threading.Thread(target=run_robot_task, daemon=True)
    t.start()

    return {"success": True, "message": "Desenho iniciado no robô UR3."}


@app.post("/api/abort")
async def abort_drawing():
    """Para o robô imediatamente em caso de emergência ou cancelamento."""
    robot_driver.abort()
    app_state["drawing_status"] = "idle"
    app_state["status_message"] = "Desenho interrompido pelo usuário."
    await ws_manager.broadcast({
        "event": "aborted",
        "message": "Desenho cancelado!"
    })
    return {"success": True, "message": "Comando de parada enviado ao robô."}


@app.post("/api/home")
async def move_robot_home():
    """Envia o robô para a pose HOME segura."""
    if robot_driver.is_drawing:
        return JSONResponse(status_code=400, content={"success": False, "error": "Aguarde o desenho terminar ou aborte primeiro."})

    success = robot_driver.move_home()
    return {"success": success, "message": "Robô movido para HOME." if success else "Falha ao mover para HOME."}


@app.post("/api/calibrate/touch")
async def calibrate_touch():
    """Executa traço de teste de 8mm para validar a altura Z e a mola da caneta."""
    if robot_driver.is_drawing:
        return JSONResponse(status_code=400, content={"success": False, "error": "Robô ocupado."})

    success = calib_mgr.test_pen_touch()
    return {"success": success, "message": "Traço de teste executado." if success else "Falha no teste de toque."}


@app.post("/api/calibrate/origin")
async def calibrate_origin():
    """Salva a posição atual do robô como a nova origem do papel A6."""
    coords = calib_mgr.set_origin_from_current_pose()
    if coords:
        return {"success": True, "origin": coords, "message": "Nova origem salva com sucesso!"}
    else:
        return JSONResponse(status_code=500, content={"success": False, "error": "Não foi possível calibrar a origem."})


@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    """Canal WebSocket para atualização instantânea do progresso do desenho no celular/PC."""
    await ws_manager.connect(websocket)
    try:
        # Envia estado inicial imediatamente ao conectar
        await websocket.send_json({
            "event": "initial_state",
            "status": app_state["drawing_status"],
            "progress": app_state["progress_pct"],
            "message": app_state["status_message"]
        })
        while True:
            # Mantém conexão viva aguardando pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    host = config.get("web", {}).get("host", "0.0.0.0")
    port = int(config.get("web", {}).get("port", 5000))
    log.info("🚀 Iniciando UR_PICASSO em http://%s:%d", host, port)
    uvicorn.run(app, host=host, port=port)

