FROM python:3.13-slim
WORKDIR /app
COPY server.py queue_store.py entrypoint.py muse_store.py muse_api.py muse_agent.py vm_agent.py runtime.py .
COPY LICENSE ./LICENSE
COPY static ./static
ENV PYTHONUNBUFFERED=1
CMD ["python", "entrypoint.py"]
