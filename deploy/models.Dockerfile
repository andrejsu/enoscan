# Retriever model weights (DINOv2 ONNX + SAM ViT-B), fetched in CI by the
# same download scripts the dev stack runs, then shipped as an image.
# The VPS cannot rely on reaching huggingface.co, so compose.prod.yaml's
# retriever-model step only copies these files into the models volume.
# Build context is the repo root.
FROM python:3.12-slim-bookworm AS fetch

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app:/app/scripts
ENV MODEL_PATH=/models/dinov2-small.onnx
ENV SAM_MODEL_DIR=/models/sam_vit_b_quant

WORKDIR /app
COPY services/retrieval/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY services/retrieval/app ./app
COPY scripts/label_prep.py ./scripts/label_prep.py
RUN python -m app.download_model && python -m app.download_sam

FROM busybox:1.37

COPY --from=fetch /models /bundled
# Replaces a file only when its bytes differ, via rename, so a running
# retriever never sees a half-written model.
CMD ["sh", "-c", "cd /bundled && find . -type f | while read -r f; do cmp -s \"$f\" \"/models/$f\" && continue; mkdir -p \"/models/$(dirname \"$f\")\" && cp \"$f\" \"/models/$f.tmp\" && mv \"/models/$f.tmp\" \"/models/$f\" && echo \"installed $f\"; done; echo 'Models ready.'"]
