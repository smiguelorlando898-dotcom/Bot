#!/bin/bash
# Iniciar servidor gráfico virtual
Xvfb :0 -screen 0 1024x768x16 &
export DISPLAY=:0

# Iniciar gestor de ventanas ligero
fluxbox &

# Iniciar servidor VNC
x11vnc -display :0 -nopw -forever -shared &

# Iniciar noVNC en puerto 8080 (corregido)
# En versiones recientes de noVNC se usa 'novnc_proxy' en lugar de 'launch.sh'
/opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen 8080