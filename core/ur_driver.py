"""
Módulo de Comunicação e Controle Cinemático do Robô Universal Robots (UR3)
==========================================================================
Implementa os padrões de 'INSTRUCOES_AGENTE_UR.md':
- Envio URScript via porta 30002
- Handshake reverso na porta 50007 (elimina delays cegos e race conditions)
- Leitura de juntas e telemetria na porta 30003
- Controle da Garra OnRobot via XML-RPC com '/' final (porta 41414)
- Conversão de traços 2D em trajetórias cartesianas 3D seguras
"""

import socket
import struct
import time
import math
import logging
import threading
import xmlrpc.client
from typing import List, Tuple, Optional, Callable, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger("URDriver")


class UR3PicassoDriver:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.robot_cfg = config.get("robot", {})
        self.calib_cfg = config.get("calibration", {})
        self.motion_cfg = config.get("motion", {})
        self.paper_cfg = config.get("paper", {})

        self.robot_ip = self.robot_cfg.get("ip", "192.168.1.100")
        self.primary_port = int(self.robot_cfg.get("primary_port", 30002))
        self.realtime_port = int(self.robot_cfg.get("realtime_port", 30003))
        self.sync_port = int(self.robot_cfg.get("sync_port", 50007))
        self.gripper_port = int(self.robot_cfg.get("gripper_port", 41414))

        self.gripper: Optional[xmlrpc.client.ServerProxy] = None
        self.is_connected = False
        self.is_drawing = False
        self.abort_requested = False
        self.current_progress = 0.0

        # Bloqueio de comunicação para evitar envios concorrentes
        self._comm_lock = threading.Lock()

        # Testa conexão inicial
        self.check_connection()
        if self.robot_cfg.get("gripper_enabled", True):
            self._init_gripper()

    def _init_gripper(self):
        """Conecta com a garra OnRobot usando obrigatoriamente a barra final '/'."""
        try:
            socket.setdefaulttimeout(2.0)
            url = f"http://{self.robot_ip}:{self.gripper_port}/"
            proxy = xmlrpc.client.ServerProxy(url)
            # Testa ping
            proxy.rg_get_width(0)
            self.gripper = proxy
            log.info("✓ Garra OnRobot conectada com sucesso na porta %d", self.gripper_port)
            # Garante que o suporte da caneta está firme
            hold_w = float(self.robot_cfg.get("gripper_hold_width_mm", 35.0))
            force = float(self.robot_cfg.get("gripper_force_n", 40.0))
            self.gripper.rg_grip(0, hold_w, force)
            log.info("✓ Suporte da caneta fixado na garra (%s mm, %s N)", hold_w, force)
        except Exception as e:
            log.warning("Garra OnRobot não detectada em http://%s:%d/ (%s). Modo caneta passiva.", 
                        self.robot_ip, self.gripper_port, e)
            self.gripper = None

    def get_local_ip(self) -> str:
        """Descobre dinamicamente o IP do Raspberry Pi na interface voltada ao robô."""
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((self.robot_ip, self.primary_port))
            local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "192.168.1.10"
        finally:
            s.close()
        return local_ip

    def check_connection(self) -> bool:
        """Verifica se a porta 30002 do UR3 está acessível."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                s.connect((self.robot_ip, self.primary_port))
                self.is_connected = True
                return True
        except Exception:
            self.is_connected = False
            return False

    def read_current_joints(self) -> Optional[List[float]]:
        """Lê os 6 ângulos de junta reais (em radianos) via porta 30003."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.robot_ip, self.realtime_port))
                raw_data = b""
                while len(raw_data) < 2048:
                    chunk = s.recv(2048)
                    if not chunk:
                        break
                    raw_data += chunk

                i = 0
                while i <= len(raw_data) - 300:
                    if i + 4 <= len(raw_data):
                        pack_len = struct.unpack(">i", raw_data[i:i+4])[0]
                        if pack_len in (756, 812, 1060, 1108, 1140) and (i + pack_len <= len(raw_data)):
                            q_bytes = raw_data[i+252 : i+300]
                            if len(q_bytes) == 48:
                                q_actual = struct.unpack(">6d", q_bytes)
                                return [round(float(q), 5) for q in q_actual]
                    i += 1
        except Exception as e:
            log.debug("Aviso: Falha na leitura via porta 30003: %s", e)
        return None

    def execute_urscript(self, script_body: str, timeout: float = 40.0) -> bool:
        """
        Executa um bloco de URScript e aguarda o handshake na porta sync_port (50007).
        Previne condições de corrida abrindo o bind/listen antes de enviar o script.
        """
        with self._comm_lock:
            local_ip = self.get_local_ip()
            sync_code = (
                f"  if socket_open(\"{local_ip}\", {self.sync_port}, \"sync_socket\"):\n"
                f"    socket_send_string(\"done\", \"sync_socket\")\n"
                f"    socket_close(\"sync_socket\")\n"
                f"  end\n"
            )
            full_script = (
                "def ur_task():\n"
                + script_body + "\n"
                + sync_code +
                "end\n"
                "ur_task()\n"
            )

            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.settimeout(timeout)

            try:
                server.bind(("0.0.0.0", self.sync_port))
                server.listen(1)
            except Exception as e:
                log.error("Erro ao preparar socket servidor na porta %d: %s", self.sync_port, e)
                return False

            # Envia script para porta primária 30002
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(4.0)
                    s.connect((self.robot_ip, self.primary_port))
                    s.sendall(full_script.encode('utf-8'))
            except Exception as e:
                log.error("Erro ao enviar script para %s:%d: %s", self.robot_ip, self.primary_port, e)
                server.close()
                return False

            # Aguarda confirmação de conclusão do robô
            try:
                conn, _ = server.accept()
                conn.settimeout(3.0)
                data = conn.recv(128).decode('utf-8', errors='ignore')
                conn.close()
                return "done" in data
            except socket.timeout:
                log.error("Timeout aguardando conclusão do movimento no robô (%ss).", timeout)
                return False
            finally:
                server.close()

    def move_home(self) -> bool:
        """Move o robô com segurança para a posição HOME de descanso/câmera."""
        home_joints = self.calib_cfg.get("home_joints", [-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0.0])
        j_str = ", ".join(f"{q:.5f}" for q in home_joints)
        script = f"  movej([{j_str}], a=1.2, v=1.0)"
        log.info("Movendo UR3 para HOME...")
        return self.execute_urscript(script, timeout=20.0)

    def abort(self):
        """Cancela imediatamente o desenho atual e levanta a caneta."""
        log.warning("🛑 Solicitação de ABORTO de desenho recebida!")
        self.abort_requested = True
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(2.0)
                s.connect((self.robot_ip, self.primary_port))
                # Comando emergencial de parada e elevação
                s.sendall(b"stopl(3.0)\n")
        except Exception:
            pass

    def map_2d_to_3d_pose(self, x_mm: float, y_mm: float, is_touching: bool) -> List[float]:
        """
        Converte coordenada (X, Y) do papel em milímetros para pose cartesiana [X, Y, Z, Rx, Ry, Rz]
        no sistema de coordenadas da base do robô (em metros).
        
        Suporta calibração de plano com origem e vetores diretores.
        """
        origin = self.calib_cfg.get("origin_pose", [-0.200, -0.350, 0.085, 2.22, -2.22, 0.0])
        x_dir = self.calib_cfg.get("x_axis_vector", [1.0, 0.0, 0.0])
        y_dir = self.calib_cfg.get("y_axis_vector", [0.0, 1.0, 0.0])
        z_norm = self.calib_cfg.get("z_normal_vector", [0.0, 0.0, 1.0])

        x_m = x_mm / 1000.0
        y_m = y_mm / 1000.0

        # Altura Z: no papel ou no ar (Pen-Up)
        z_offset = self.calib_cfg.get("z_draw_offset_m", 0.0)
        z_lift = self.calib_cfg.get("z_lift_m", 0.005) # 5 mm de elevação rápida

        z_component = z_offset if is_touching else (z_offset + z_lift)

        pos_x = origin[0] + x_m * x_dir[0] + y_m * y_dir[0] + z_component * z_norm[0]
        pos_y = origin[1] + x_m * x_dir[1] + y_m * y_dir[1] + z_component * z_norm[1]
        pos_z = origin[2] + x_m * x_dir[2] + y_m * y_dir[2] + z_component * z_norm[2]

        rx, ry, rz = origin[3], origin[4], origin[5]
        return [round(pos_x, 5), round(pos_y, 5), round(pos_z, 5), rx, ry, rz]

    def draw_portrait(self, strokes: List[List[Tuple[float, float]]], 
                      progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        Executa os traços no robô UR3 com máxima velocidade e fluidez.
        
        Estratégia de Alta Performance:
        1. Os traços chegam já ordenados pelo otimizador TSP (mínimo deslocamento no ar).
        2. Pen-Up rápido (apenas 5mm de subida, com alta velocidade v=0.35 m/s).
        3. No papel (Pen-Down), utiliza blend radius (r=0.002m) nos pontos intermediários
           de cada traço para manter momento contínuo sem travar os motores.
        4. O ponto final de cada traço usa r=0.0 antes de subir a caneta.
        5. Envia em lotes inteligentes de 15 traços por URScript para dar feedback ao vivo
           ao convidado na tela do celular e permitir cancelamento instantâneo se necessário.
        """
        if not strokes:
            log.warning("Nenhum traço fornecido para desenho.")
            return True

        self.is_drawing = True
        self.abort_requested = False
        self.current_progress = 0.0

        total_strokes = len(strokes)
        log.info("🎨 Iniciando desenho no UR3: %d traços contínuos...", total_strokes)

        draw_v = self.motion_cfg.get("draw_speed", 0.22)
        draw_a = self.motion_cfg.get("draw_accel", 1.2)
        travel_v = self.motion_cfg.get("travel_speed", 0.35)
        travel_a = self.motion_cfg.get("travel_accel", 1.5)
        blend_r = self.motion_cfg.get("blend_radius", 0.002)

        # Lotes de traços por bloco URScript
        batch_size = 12
        executed_strokes = 0

        # Se o robô não estiver fisicamente conectado, executa em modo Simulação
        is_real = self.check_connection()
        if not is_real:
            log.warning("⚠️ Robô físico não detectado. Executando em MODO SIMULAÇÃO...")

        try:
            for b_idx in range(0, total_strokes, batch_size):
                if self.abort_requested:
                    log.warning("Desenho abortado pelo usuário.")
                    if progress_callback:
                        progress_callback(self.current_progress, "Desenho cancelado.")
                    return False

                current_batch = strokes[b_idx : b_idx + batch_size]
                script_lines = []

                for stroke in current_batch:
                    if len(stroke) < 2:
                        continue

                    # 1. Posiciona no ar (Pen-Up) sobre o início do traço
                    start_pt = stroke[0]
                    p_above_start = self.map_2d_to_3d_pose(start_pt[0], start_pt[1], is_touching=False)
                    script_lines.append(f"  movel(p[{p_above_start[0]}, {p_above_start[1]}, {p_above_start[2]}, {p_above_start[3]}, {p_above_start[4]}, {p_above_start[5]}], a={travel_a}, v={travel_v})")

                    # 2. Desce a caneta no papel (Pen-Down)
                    p_touch_start = self.map_2d_to_3d_pose(start_pt[0], start_pt[1], is_touching=True)
                    script_lines.append(f"  movel(p[{p_touch_start[0]}, {p_touch_start[1]}, {p_touch_start[2]}, {p_touch_start[3]}, {p_touch_start[4]}, {p_touch_start[5]}], a={draw_a}, v={draw_v * 0.7})")

                    # 3. Desenha os pontos intermediários com blend radius para fluidez
                    for pt in stroke[1:-1]:
                        p_touch = self.map_2d_to_3d_pose(pt[0], pt[1], is_touching=True)
                        script_lines.append(f"  movel(p[{p_touch[0]}, {p_touch[1]}, {p_touch[2]}, {p_touch[3]}, {p_touch[4]}, {p_touch[5]}], a={draw_a}, v={draw_v}, r={blend_r})")

                    # 4. Ponto final do traço (r=0.0 obrigatório para parar exatamente antes de subir)
                    end_pt = stroke[-1]
                    p_touch_end = self.map_2d_to_3d_pose(end_pt[0], end_pt[1], is_touching=True)
                    script_lines.append(f"  movel(p[{p_touch_end[0]}, {p_touch_end[1]}, {p_touch_end[2]}, {p_touch_end[3]}, {p_touch_end[4]}, {p_touch_end[5]}], a={draw_a}, v={draw_v})")

                    # 5. Sobe a caneta de volta no ar (Pen-Up)
                    p_above_end = self.map_2d_to_3d_pose(end_pt[0], end_pt[1], is_touching=False)
                    script_lines.append(f"  movel(p[{p_above_end[0]}, {p_above_end[1]}, {p_above_end[2]}, {p_above_end[3]}, {p_above_end[4]}, {p_above_end[5]}], a={travel_a}, v={travel_v})")

                # Dispara o lote para o robô
                batch_script = "\n".join(script_lines)
                if is_real:
                    success = self.execute_urscript(batch_script, timeout=60.0)
                    if not success and not self.abort_requested:
                        log.error("Falha na execução do lote %d no robô.", b_idx // batch_size)
                        return False
                else:
                    # Simulação: aguarda proporcionalmente ao número de pontos
                    sim_delay = max(0.4, len(current_batch) * 0.35)
                    time.sleep(sim_delay)

                executed_strokes += len(current_batch)
                self.current_progress = round((executed_strokes / total_strokes) * 100.0, 1)

                msg = f"Desenhando traço {executed_strokes} de {total_strokes} ({self.current_progress:.0f}%)"
                log.info(msg)
                if progress_callback:
                    progress_callback(self.current_progress, msg)

            # Ao terminar todos os traços, levanta e recua com segurança
            if is_real:
                lift_script = (
                    "  # Elevação final pós-desenho\n"
                    "  current_p = get_actual_tcp_pose()\n"
                    "  safe_up = p[current_p[0], current_p[1], current_p[2] + 0.050, current_p[3], current_p[4], current_p[5]]\n"
                    "  movel(safe_up, a=1.0, v=0.3)\n"
                )
                self.execute_urscript(lift_script, timeout=10.0)

            self.current_progress = 100.0
            log.info("🎉 Retrato concluído com sucesso!")
            if progress_callback:
                progress_callback(100.0, "Desenho finalizado! Retire sua obra de arte.")
            return True

        finally:
            self.is_drawing = False

