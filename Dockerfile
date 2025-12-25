FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Instala entorno gráfico, Wine y utilidades
RUN apt-get update && apt-get install -y \
    xfce4 xfce4-goodies x11vnc xvfb wine supervisor git python3 python3-pip net-tools tzdata \
    && ln -fs /usr/share/zoneinfo/$TZ /etc/localtime \
    && dpkg-reconfigure --frontend noninteractive tzdata

# Configura contraseña VNC
RUN mkdir -p /root/.vnc && \
    x11vnc -storepasswd 1234 /root/.vnc/passwd

# Instala noVNC y websockify
RUN git clone https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone https://github.com/novnc/websockify /opt/noVNC/utils/websockify && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html

# Copia configuración de supervisord y script de inicio
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 5900 8080

CMD ["/usr/bin/supervisord"]