# Imagen base con escritorio LXDE + VNC ya configurado
FROM dorowu/ubuntu-desktop-lxde-vnc

USER root

# Instala Wine y utilidades adicionales
RUN apt-get update && apt-get install -y \
    wine supervisor net-tools \
    && rm -rf /var/lib/apt/lists/*

# Configura contraseña VNC
RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd 1234 /root/.vnc/passwd

# Exponer puertos: VNC y noVNC
EXPOSE 5900 6080