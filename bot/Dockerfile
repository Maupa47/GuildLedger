# Optional alternative to systemd + venv (the default, see deploy/). Build from the repository root:
#   docker build -f bot/Dockerfile -t guildledger-bot .
#   docker run -d --restart=always --name guildledger-bot \
#     -v /etc/guildledger/config.toml:/config/config.toml:ro -v guildledger-data:/data guildledger-bot
# In config.toml set [storage] db_path = "/data/guildledger.db".
FROM python:3.12-slim

RUN useradd --system --home-dir /data --shell /usr/sbin/nologin guildledger \
    && mkdir -p /data /app && chown guildledger:guildledger /data
WORKDIR /app
COPY companion/ /app/companion/
COPY bot/ /app/bot/
COPY shared/ /app/shared/
RUN pip install --no-cache-dir /app/companion /app/bot \
    && rm -rf /app/companion/tests /app/bot/tests

USER guildledger
VOLUME ["/data"]
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "-m", "guildledger_bot", "--config", "/config/config.toml"]
CMD ["run"]
