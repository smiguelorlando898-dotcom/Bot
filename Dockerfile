FROM ubuntu:22.04

# Dependencias básicas
RUN apt-get update && apt-get install -y \
    wget curl unzip xvfb x11vnc fluxbox \
    python3 python3-pip git \
    wine64 winbind \
    && rm -rf /var/lib/apt/lists/*

# Instalar noVNC + websockify
RUN git clone https://github.com/novnc/noVNC.git /opt/noVNC \
    && git clone https://github.com/novnc/websockify /opt/noVNC/utils/websockify

WORKDIR /opt/noVNC
EXPOSE 8080

# Script de arranque
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]