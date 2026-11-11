"""
Módulo de Vetorização e Otimização de Trajetórias (TSP)
======================================================
Transforma a imagem binária de linhas em polilinhas milimétricas calibradas
para a prancheta de papel A6, aplicando o algoritmo do Caixeiro Viajante (TSP)
guloso para minimizar o tempo de caneta no ar (Pen-Up).
"""

import math
import cv2
import numpy as np
import logging
from typing import List, Tuple, Dict, Any

log = logging.getLogger("Vectorizer")


class TrajectoryOptimizer:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.paper_cfg = config.get("paper", {})
        self.drawing_cfg = config.get("drawing", {})

        # Dimensões da folha A6 e margens
        self.paper_w = float(self.paper_cfg.get("width_mm", 105.0))
        self.paper_h = float(self.paper_cfg.get("height_mm", 148.0))
        self.margin_top = float(self.paper_cfg.get("margin_top_mm", 20.0))
        self.margin_bottom = float(self.paper_cfg.get("margin_bottom_mm", 20.0))
        self.margin_sides = float(self.paper_cfg.get("margin_sides_mm", 6.0))

        # Área útil ativa de desenho
        self.active_w = self.paper_w - (2 * self.margin_sides) # 93.0 mm
        self.active_h = self.paper_h - (self.margin_top + self.margin_bottom) # 108.0 mm

    def extract_and_optimize(self, skeleton_img: np.ndarray, profile_name: str = "ultra_fast") -> List[List[Tuple[float, float]]]:
        """
        Extrai contornos, simplifica geometrias e ordena com algoritmo TSP guloso.
        Retorna lista de traços em milímetros: [[[x1, y1], [x2, y2], ...], ...]
        """
        profiles = self.drawing_cfg.get("profiles", {})
        profile = profiles.get(profile_name, profiles.get("ultra_fast", {
            "max_strokes": 80,
            "min_stroke_length_mm": 2.5,
            "poly_epsilon_ratio": 0.0040
        }))

        max_strokes = profile.get("max_strokes", 80)
        min_length_mm = profile.get("min_stroke_length_mm", 2.5)
        epsilon_ratio = profile.get("poly_epsilon_ratio", 0.0040)

        img_h, img_w = skeleton_img.shape[:2]

        # 1. Encontra contornos da imagem afinada
        contours, _ = cv2.findContours(skeleton_img, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

        raw_strokes: List[List[Tuple[float, float]]] = []

        # Fatores de conversão de pixel para milímetros
        scale_x = self.active_w / float(img_w)
        scale_y = self.active_h / float(img_h)

        # 2. Simplificação Poligonal Ramer-Douglas-Peucker (RDP)
        for cnt in contours:
            if len(cnt) < 3:
                continue

            # Calcula perímetro para tolerância adaptativa de curvatura
            peri = cv2.arcLength(cnt, closed=False)
            epsilon = max(1.0, peri * epsilon_ratio)
            approx = cv2.approxPolyDP(cnt, epsilon, closed=False)

            if len(approx) < 2:
                continue

            # Converte pontos para coordenadas milimétricas com deslocamento das margens
            stroke_pts: List[Tuple[float, float]] = []
            stroke_len_mm = 0.0
            prev_pt = None

            for pt in approx:
                px, py = pt[0]
                # Injeta offset das margens (superior 20mm, laterais 6mm)
                mx = self.margin_sides + (px * scale_x)
                my = self.margin_top + (py * scale_y)
                current_pt = (round(mx, 2), round(my, 2))
                stroke_pts.append(current_pt)

                if prev_pt is not None:
                    dx = current_pt[0] - prev_pt[0]
                    dy = current_pt[1] - prev_pt[1]
                    stroke_len_mm += math.hypot(dx, dy)
                prev_pt = current_pt

            # Filtra traços minúsculos que apenas tomam tempo do robô sem agregar valor visual
            if stroke_len_mm >= min_length_mm and len(stroke_pts) >= 2:
                raw_strokes.append(stroke_pts)

        # 3. Limita os traços mantendo os mais expressivos (maior comprimento)
        if len(raw_strokes) > max_strokes:
            raw_strokes.sort(key=lambda s: sum(math.hypot(s[i][0]-s[i-1][0], s[i][1]-s[i-1][1]) for i in range(1, len(s))), reverse=True)
            raw_strokes = raw_strokes[:max_strokes]

        # 4. Algoritmo TSP Guloso (Nearest-Neighbor) para Otimização de Percurso
        # Minimiza o tempo de deslocamento aéreo (caneta levantada)
        optimized_strokes = self._tsp_greedy_order(raw_strokes)

        log.info("Vetorização concluída: %d traços otimizados para desenho.", len(optimized_strokes))
        return optimized_strokes

    def _tsp_greedy_order(self, strokes: List[List[Tuple[float, float]]]) -> List[List[Tuple[float, float]]]:
        """
        Ordena os traços de forma que o início do próximo seja o mais próximo possível
        do término do traço anterior. Pode inverter o sentido do traço se a distância for menor!
        """
        if not strokes:
            return []

        remaining = list(strokes)
        ordered: List[List[Tuple[float, float]]] = []

        # Posição inicial da caneta: canto superior esquerdo da margem
        current_x = self.margin_sides
        current_y = self.margin_top

        while remaining:
            best_idx = -1
            best_dist_sq = float('inf')
            reverse_chosen = False

            for idx, stroke in enumerate(remaining):
                start_pt = stroke[0]
                end_pt = stroke[-1]

                # Distância até o início do traço
                d_start = (current_x - start_pt[0]) ** 2 + (current_y - start_pt[1]) ** 2
                # Distância até o final do traço
                d_end = (current_x - end_pt[0]) ** 2 + (current_y - end_pt[1]) ** 2

                if d_start < best_dist_sq:
                    best_dist_sq = d_start
                    best_idx = idx
                    reverse_chosen = False

                if d_end < best_dist_sq:
                    best_dist_sq = d_end
                    best_idx = idx
                    reverse_chosen = True

            chosen_stroke = remaining.pop(best_idx)
            if reverse_chosen:
                chosen_stroke = list(reversed(chosen_stroke))

            ordered.append(chosen_stroke)
            # Atualiza a posição atual para onde a caneta terminou
            current_x, current_y = chosen_stroke[-1]

        return ordered

    def strokes_to_svg(self, strokes: List[List[Tuple[float, float]]]) -> str:
        """Gera representação SVG vetorial perfeita para renderização rápida no frontend."""
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.paper_w} {self.paper_h}" width="100%" height="100%" style="background:#fff;">',
            # Marcações das margens reservadas (20mm topo e base) em linha tracejada discreta
            f'<line x1="0" y1="{self.margin_top}" x2="{self.paper_w}" y2="{self.margin_top}" stroke="#e0e0e0" stroke-dasharray="2,2" stroke-width="0.5"/>',
            f'<line x1="0" y1="{self.paper_h - self.margin_bottom}" x2="{self.paper_w}" y2="{self.paper_h - self.margin_bottom}" stroke="#e0e0e0" stroke-dasharray="2,2" stroke-width="0.5"/>',
            # Traços do desenho
            '<g fill="none" stroke="#111" stroke-width="0.6" stroke-linecap="round" stroke-linejoin="round">'
        ]

        for stroke in strokes:
            if not stroke:
                continue
            d_cmds = [f"M {stroke[0][0]:.2f} {stroke[0][1]:.2f}"]
            for pt in stroke[1:]:
                d_cmds.append(f"L {pt[0]:.2f} {pt[1]:.2f}")
            path_str = " ".join(d_cmds)
            svg_parts.append(f'<path d="{path_str}" />')

        svg_parts.append('</g></svg>')
        return "".join(svg_parts)

