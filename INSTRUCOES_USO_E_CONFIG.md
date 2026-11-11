# 📋 Manual de Configuração e Uso — UR_PICASSO

Guia prático para configuração física, de rede e operação do robô retratista UR3 em eventos.

---

## 1. Topologia de Rede & Conexões Físicas

```
[ Smartphone / PC do Convidado ]
               │ (Wi-Fi Hotspot: wlan0)
               ▼
    [ RASPBERRY PI 3B+ ] (Host da Dashboard: porta 5000)
               │ (Cabo de Rede Direto: eth0)
               ▼
      [ ROBÔ UR3 / CB3 ] (Porta 30002 / 30003 / 41414)
```

### Configurações de IP Recomendadas:
- **Robô UR3 (Teach Pendant ➔ Configurar Rede):**
  - IP: `192.168.1.100`
  - Máscara: `255.255.255.0`
  - Gateway: `192.168.1.1`
- **Raspberry Pi (Interface eth0):**
  - IP: `192.168.1.10`
  - Máscara: `255.255.255.0`
- **Raspberry Pi Hotspot Wi-Fi (Interface wlan0):**
  - IP Gateway padrão: `192.168.4.1` (ou o configurado no seu hostapd/NetworkManager).

---

## 2. Configurações em `config.json`

O arquivo `config.json` centraliza todos os parâmetros do sistema:

```json
{
  "robot": {
    "ip": "192.168.1.100",          // IP da controladora do robô
    "primary_port": 30002,           // Porta primária de envio de scripts
    "realtime_port": 30003,          // Leitura de estados e juntas (125/500Hz)
    "sync_port": 50007,              // Handshake reverso para sincronização
    "gripper_port": 41414,           // Daemon XML-RPC da OnRobot
    "gripper_hold_width_mm": 35.0,   // Largura da garra para segurar o suporte 3D
    "gripper_force_n": 40.0          // Força de aperto
  },
  "paper": {
    "format": "A6",
    "width_mm": 105.0,               // Largura do papel
    "height_mm": 148.0,              // Altura do papel
    "margin_top_mm": 20.0,           // Desprezar 20mm topo (dados do evento)
    "margin_bottom_mm": 20.0,        // Desprezar 20mm base (dados do evento)
    "margin_sides_mm": 6.0           // Margens laterais de segurança
  },
  "calibration": {
    "origin_pose": [-0.200, -0.350, 0.085, 2.22, -2.22, 0.0], // Ponto X0, Y0, Z0 do papel
    "z_draw_offset_m": 0.000,        // Contato no papel (com pré-carga de ~1mm na mola)
    "z_lift_m": 0.005                // Caneta no ar (apenas 5mm de subida rápida)
  },
  "motion": {
    "draw_speed": 0.22,              // Velocidade de desenho (m/s)
    "draw_accel": 1.2,               // Aceleração de desenho (m/s²)
    "travel_speed": 0.35,            // Velocidade aéreo/deslocamento (m/s)
    "blend_radius": 0.002            // Raio de curvatura suave nos traços
  }
}
```

---

## 3. Passo a Passo de Calibração no Local do Evento

1. **Fixação do Papel:**
   - Prenda o bloco de folhas A6 na prancheta/mesa do robô na orientação vertical.
2. **Posicionar Origem A6 (Canto Superior Esquerdo):**
   - No Teach Pendant do robô, coloque em modo manual (*Freedrive*).
   - Encoste a ponta da caneta no **canto superior esquerdo** da folha de papel A6, comprimindo a mola da caneta em cerca de 1 mm.
   - Abra a Dashboard web no celular/PC: `http://192.168.4.1:5000` (ou IP do seu Pi).
   - Clique no ícone de engrenagem **⚙️** (canto superior direito) e selecione:
     👉 **"📍 Definir Posição Atual como Origem A6"**.
   - As coordenadas serão salvas instantaneamente no `config.json`.
3. **Teste de Toque da Caneta:**
   - No mesmo menu do operador, clique em:
     👉 **"✏️ Testar Toque da Caneta (8mm)"**.
   - O robô fará um traço de 8 mm na margem superior para validar se a caneta está soltando tinta de forma homogênea e se a mola está compensando perfeitamente.
4. **Mover para HOME:**
   - Clique em **"🏠 Mover Robô para HOME"** para deixar o braço na posição elevada de espera.

---

## 4. Fluxo de Operação com os Convidados

1. O convidado conecta no Wi-Fi do Raspberry Pi e abre o navegador no endereço da dashboard.
2. **Foto:**
   - O convidado escolhe se prefere tirar uma foto na **Webcam** (com contagem regressiva de 3 segundos na tela) ou **Enviar do Celular**.
3. **Pré-visualização:**
   - O sistema gera a versão cartoon em traço vetorial na proporção exata do papel A6.
   - Selecione a velocidade:
     - ⚡ **Ultra Rápido (~45s):** Perfeito para quando há fila de espera.
     - 🎨 **Equilibrado (~90s):** Traços mais ricos e detalhados.
4. **Desenho:**
   - Clique no botão **"🚀 Desenhar no Robô UR3"**.
   - A tela exibirá a barra de progresso em tempo real e desenhará o retrato junto com o robô.
5. **Finalização:**
   - O robô eleva a caneta e recua.
   - A tela avisa: *"Retire sua folha A6 da prancheta"*.
   - O convidado pode clicar em **"Baixar Cópia Digital (SVG/JPG)"** para salvar no celular e postar nas redes sociais.
   - Clique em **"✨ Próximo Convidado"** para reiniciar o ciclo!

---

## 5. Parada de Emergência

- Na tela da dashboard, durante a execução, há o botão vermelho **"⏹️ Parar / Cancelar Desenho"** que envia interrupção instantânea para o robô.
- O botão físico de **E-Stop** da controladora do UR3 sempre tem prioridade absoluta de segurança.

