"""
Gerenciador da Webcam USB
=========================
Executa thread dedicada para captura contínua e streaming MJPEG de baixa latência,
permitindo pré-visualização fluida na interface e foto instantânea de alta definição.
"""

import cv2
import time
import threading
import numpy as np
import logging
from typing import Optional, Dict, Any

log = logging.getLogger("Camera")


class CameraManager:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.cam_cfg = config.get("camera", {})
        self.device_index = int(self.cam_cfg.get("device_index", 0))
        self.width = int(self.cam_cfg.get("width", 640))
        self.height = int(self.cam_cfg.get("height", 480))
        self.fps = int(self.cam_cfg.get("fps", 30))

        self.cap: Optional[cv2.VideoCapture] = None
        self.current_frame: Optional[np.ndarray] = None
        self.is_running = False
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None

        self.start()

    def start(self):
        """Inicia a captura de vídeo em background."""
        if self.is_running:
            return

        try:
            self.cap = cv2.VideoCapture(self.device_index)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                self.is_running = True
                self.thread = threading.Thread(target=self._update_loop, daemon=True)
                self.thread.start()
                log.info("✓ Webcam USB iniciada com sucesso (Dispositivo %d: %dx%d)", 
                         self.device_index, self.width, self.height)
            else:
                log.warning("Webcam USB não pôde ser aberta no índice %d.", self.device_index)
        except Exception as e:
            log.warning("Erro ao inicializar webcam: %s", e)

    def _update_loop(self):
        """Loop de captura contínua de frames."""
        while self.is_running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.current_frame = frame
            time.sleep(1.0 / max(self.fps, 10))

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Retorna cópia do último frame capturado."""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()

        # Se a câmera não estiver disponível, gera um frame elegante de simulação/placeholder
        placeholder = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        placeholder[:] = (40, 35, 30)
        cv2.putText(placeholder, "Aguardando Webcam USB...", (80, self.height // 2), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        return placeholder

    def capture_photo(self) -> Optional[np.ndarray]:
        """Captura foto de alta resolução no momento do disparo."""
        frame = self.get_latest_frame()
        return frame

    def generate_mjpeg_stream(self):
        """Gerador para transmissão de vídeo contínua via multipart/x-mixed-replace."""
        while True:
            frame = self.get_latest_frame()
            if frame is not None:
                # Comprime para JPEG com qualidade otimizada para Wi-Fi
                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ret:
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.04) # ~25 FPS

    def stop(self):
        """Finaliza a thread e libera a câmera."""
        self.is_running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        log.info("Webcam liberada.")

