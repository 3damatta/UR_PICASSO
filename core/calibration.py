"""
Módulo de Calibração do Plano da Folha A6 e Altura Z da Caneta
=============================================================
Facilita o setup no local do evento:
- Leitura de pose em tempo real
- Teste de toque da caneta com verificação do amortecedor mecânico (mola)
- Salvamento automático das coordenadas no 'config.json'
"""

import json
import logging
from typing import Dict, Any, Optional, List
from .ur_driver import UR3PicassoDriver

log = logging.getLogger("Calibration")


class CalibrationManager:
    def __init__(self, driver: UR3PicassoDriver, config_path: str = "config.json"):
        self.driver = driver
        self.config_path = config_path

    def test_pen_touch(self, test_length_mm: float = 8.0) -> bool:
        """
        Executa um traço de teste de 8mm no canto superior do papel para validar:
        1. Altura Z e compressão do amortecimento mecânico (mola).
        2. Saída uniforme de tinta no papel.
        """
        log.info("Executando teste de toque da caneta...")
        # Traço de teste no canto superior esquerdo (após a margem de 20mm)
        x_start = float(self.driver.paper_cfg.get("margin_sides_mm", 6.0)) + 2.0
        y_start = float(self.driver.paper_cfg.get("margin_top_mm", 20.0)) + 2.0
        
        test_stroke = [
            (x_start, y_start),
            (x_start + test_length_mm, y_start)
        ]
        
        return self.driver.draw_portrait([test_stroke])

    def set_origin_from_current_pose(self) -> Optional[List[float]]:
        """
        Lê as juntas reais do robô, calcula a cinemática direta e define como nova origem A6.
        """
        joints = self.driver.read_current_joints()
        if not joints:
            log.error("Não foi possível ler as juntas para calibração.")
            return None

        # Envia script rápido para obter o TCP pose exato
        # Como fallback quando não houver leitura direta de pose cartesiana,
        # utilizamos script URScript com handshake
        local_ip = self.driver.get_local_ip()
        sync_port = self.driver.sync_port
        
        script = (
            f"  p_act = get_actual_tcp_pose()\n"
            f"  if socket_open(\"{local_ip}\", {sync_port}, \"calib_sock\"):\n"
            f"    socket_send_string(\"pose:\" + to_str(p_act), \"calib_sock\")\n"
            f"    socket_close(\"calib_sock\")\n"
            f"  end\n"
        )
        # Execução com captura da mensagem
        import socket
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.settimeout(6.0)

        try:
            server.bind(("0.0.0.0", sync_port))
            server.listen(1)
            
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(3.0)
                s.connect((self.driver.robot_ip, self.driver.primary_port))
                full_script = f"def calib_task():\n{script}end\ncalib_task()\n"
                s.sendall(full_script.encode('utf-8'))

            conn, _ = server.accept()
            msg = conn.recv(256).decode('utf-8', errors='ignore')
            conn.close()

            if "pose:" in msg:
                pose_str = msg.replace("pose:p[", "").replace("pose:[", "").replace("]", "").strip()
                coords = [float(v.strip()) for v in pose_str.split(",")]
                if len(coords) == 6:
                    self.update_origin_pose(coords)
                    log.info("✓ Nova origem do papel A6 configurada: %s", coords)
                    return coords
        except Exception as e:
            log.error("Erro ao obter pose do TCP para calibração: %s", e)
        finally:
            server.close()

        return None

    def update_origin_pose(self, new_pose: List[float]):
        """Atualiza a pose de origem no config.json."""
        self.driver.calib_cfg["origin_pose"] = [round(v, 5) for v in new_pose]
        self.save_config()

    def save_config(self):
        """Persiste as alterações em disco."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.driver.config, f, indent=2)
            log.info("✓ Arquivo config.json atualizado com sucesso!")
        except Exception as e:
            log.error("Erro ao salvar config.json: %s", e)

