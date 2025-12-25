#!/bin/bash

# Inicia servidor gráfico virtual
Xvfb :0 -screen 0 1024x768x16 &

# Inicia VNC con contraseña
x11vnc -display :0 -rfbport 5900 -usepw -forever &

# Inicia escritorio XFCE
startxfce4 &

# Inicia noVNC en puerto 8080
/opt/noVNC/utils/launch.sh --vnc localhost:5900 --listen 8080