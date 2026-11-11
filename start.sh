#!/bin/bash
# Script de Inicialização Automática do UR_PICASSO no Raspberry Pi 3B+

echo "=================================================="
echo "    🎨 INICIANDO UR_PICASSO - ROBÔ RETRATISTA     "
echo "=================================================="

# Navega para a pasta do script
cd "$(dirname "$0")"

# Ativa ambiente virtual se existir
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Verifica se dependências estão instaladas
python3 -c "import fastapi, uvicorn, cv2, jinja2" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Instalando dependências necessárias..."
    pip3 install -r requirements.txt
fi

# Inicia o servidor FastAPI na porta 5000 acessível pelo Hotspot Wi-Fi
echo "Iniciando servidor Web em 0.0.0.0:5000..."
python3 -m uvicorn app:app --host 0.0.0.0 --port 5000

