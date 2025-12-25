FROM ubuntu:22.04

# Evitar prompts interactivos durante la instalación
ENV DEBIAN_FRONTEND=noninteractive
ARG TZ=America/Havana
ENV TZ=${TZ}

# Instalar dependencias básicas
RUN apt-get update && apt-get install -y \
    wget curl unzip xvfb x11vnc fluxbox \
    python3 python3-pip git \
    wine64 winbind \
    tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata \
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