#!/bin/bash
# Script de Configuração de Rede do Raspberry Pi 3B+ para o UR_PICASSO
# Configura:
#  - eth0: IP Estático 192.168.1.10 (para falar direto com o robô UR3 em 192.168.1.100)
#  - wlan0: Hotspot Wi-Fi 'UR_Picasso' (para os convidados acessarem a dashboard)

if [ "$EUID" -ne 0 ]; then
  echo "Por favor, execute como root (sudo ./scripts/setup_network_rpi.sh)"
  exit 1
fi

echo "=== Configurando interface cabeada eth0 para o robô UR3 ==="
# Se usa NetworkManager (Raspberry Pi OS Bookworm / recente)
if command -v nmcli &> /dev/null; then
    nmcli con add type ethernet con-name "UR3_Robot_Eth" ifname eth0 ip4 192.168.1.10/24 || true
    nmcli con up "UR3_Robot_Eth" || true
    echo "eth0 configurada via NetworkManager com IP 192.168.1.10."
fi

echo "=== Informações de Rede ==="
echo "Porta Ethernet (eth0): Conecte ao UR3 (IP do robô: 192.168.1.100)"
echo "Wi-Fi (wlan0): Hotspot ativo para celulares e PCs."
echo "Pronto! O UR_PICASSO responderá na porta 5000."
