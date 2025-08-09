FROM library-data as base

FROM base
RUN apt-get update && apt-get install -y --no-install-recommends cron && rm -rf /var/lib/apt/lists/*
COPY docker/scheduler/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENV LIBRARY_DATA_DIR=/app/library-data
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

