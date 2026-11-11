# 🤖🎨 UR_PICASSO: Robô Retratista para Recepção de Eventos

Sistema completo para transformar um robô colaborativo **Universal Robots (UR3)** em uma atração interativa ao vivo em eventos. Os convidados conectam-se ao Wi-Fi Hotspot do **Raspberry Pi 3B+**, tiram uma foto com a webcam (ou enviam do celular), o sistema vetoriza um retrato em **traço cartoon** de alto contraste e o UR3 desenha a obra de arte em uma folha **A6** em menos de **60 a 90 segundos**.

---

## 📐 Especificações Técnicas e de Hardware

- **Controlador Host:** Raspberry Pi 3B+ (Wi-Fi Hotspot para convidados + Ethernet estático para o robô).
- **Manipulador Robótico:** Universal Robots UR3 (CB3 ou e-Series).
- **Ferramenta (End-Effector):** Suporte impresso em 3D seguro pela garra OnRobot com caneta amortecida mecanicamente (mola de 2 mm de compensação).
- **Formato do Papel:** **A6 vertical** (105 mm de largura × 148 mm de altura).
- **Margens de Proteção:** **20 mm** reservadas no topo e **20 mm** na base (espaço para logotipo/dados do evento).
- **Área Útil Ativa de Desenho:** **93 mm × 108 mm**.

---

## 🚀 Arquitetura e Fluxo do Sistema

1. **Rede e Acesso:**
   - O Raspberry Pi cria a rede Wi-Fi (Hotspot) onde os convidados conectam seus celulares/tablets.
   - Pelo navegador, acessam `http://192.168.4.1:5000` (ou IP do hotspot).
2. **Captura / Upload:**
   - **Modo Câmera:** Transmissão ao vivo da webcam USB com moldura guia e contagem regressiva de 3 segundos (*3.. 2.. 1.. 📸*).
   - **Modo Upload:** O convidado envia uma foto direto do rolo de câmera do smartphone.
3. **Pipeline de Visão & Estilização Cartoon (OpenCV Ultraleve):**
   - Recorte e enquadramento automático do rosto no aspect ratio exato da prancheta A6.
   - Filtro Bilateral para suavizar texturas de pele mantendo olhos, nariz, boca e contornos nítidos.
   - Extração de bordas adaptativas + afinamento morfológico (esqueletização) para traços de 1 pixel.
4. **Otimizador de Trajetória TSP (Caneta no Ar Mínima):**
   - Simplificação geométrica (*Ramer-Douglas-Peucker*).
   - Algoritmo do Caixeiro Viajante (*Greedy Nearest Neighbor*) para encadear os traços, eliminando mais de 80% dos movimentos de caneta levantada (*Pen-Up*).
5. **Driver Robótico UR3 (Padrão de Engenharia do Guia):**
   - Envio de URScript pela porta **30002**.
   - Handshake bidirecional via socket reverso na porta **50007** (elimina `time.sleep` cegos e previne *race conditions*).
   - Altura de desenho segura ($Z_{down}$) com pré-carga na mola e subida rápida de apenas 5 mm ($Z_{lift}$).
   - Blend radius ($r=0.002$ m) nos pontos intermediários para que o UR3 não sofra trancos ou paradas bruscas nas curvas.

---

## 📂 Estrutura de Arquivos

```
UR_PICASSO/
├── app.py                      # Servidor FastAPI com WebSockets e streaming de vídeo
├── config.json                 # Configuração de portas, papel A6, calibração Z e velocidade
├── requirements.txt            # Dependências Python
├── start.sh                    # Script de inicialização no Raspberry Pi
├── start.bat                   # Script de teste no Windows
├── INSTRUCOES_AGENTE_UR.md     # Manual oficial de comandos e cinemática do UR
│
├── core/
│   ├── ur_driver.py            # Driver cinemático UR3 (30002, 30003, 50007, OnRobot)
│   ├── vision_pipeline.py      # Estilização cartoon e detecção facial
│   ├── vectorizer.py           # Simplificação poligonal e otimizador TSP
│   ├── camera.py               # Gerenciador de streaming MJPEG da webcam USB
│   └── calibration.py          # Rotinas de calibração do plano A6 e teste de toque da caneta
│
├── templates/
│   └── index.html              # Interface web mobile-first para os convidados
└── static/
    ├── css/style.css           # Estilo escuro moderno / neon
    └── js/app.js               # Lógica client-side com feedback via WebSocket
```

---

## ⚡ Como Iniciar no Raspberry Pi 3B+

1. Conecte no Raspberry Pi via terminal e entre na pasta:
   ```bash
   cd ~/UR_PICASSO
   ```

2. Instale as dependências:
   ```bash
   pip3 install -r requirements.txt
   ```

3. Inicie o sistema:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```

4. Acesse pelo celular conectado ao Wi-Fi do Raspberry Pi no navegador:
   ```
   http://192.168.4.1:5000
   ```

---

## ⚙️ Calibração no Local do Evento (Menu do Operador)

No canto superior direito da tela, clique no ícone **⚙️** para abrir o menu do operador:
1. **Mover para HOME:** Move o braço para a posição inicial de descanso elevada.
2. **Definir Origem A6:** Com o Teach Pendant, posicione a ponta da caneta suavemente sobre o canto superior esquerdo da folha de papel A6 e clique neste botão. A nova coordenada cartesiana é salva instantaneamente no `config.json`.
3. **Testar Toque da Caneta:** O robô desce e faz um risco horizontal de 8 mm para você conferir visualmente a compressão da mola (amortecedor de 2 mm) e a marca da tinta no papel.

