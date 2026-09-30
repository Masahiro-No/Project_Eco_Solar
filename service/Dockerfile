# ---------- Trainer Worker ----------
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

WORKDIR /workspace

# ตั้งค่า pip ให้ทนต่อเน็ตช้า/ไม่เสถียร
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

RUN pip install --no-cache-dir --default-timeout=120 --retries=5 \
    "arq>=0.28.0,<0.29" \
    "transformers>=4.40.0,<4.45" \
    "datasets>=2.19.0,<3.0" \
    "minio>=7.2.0,<8.0" \
    "seqeval>=1.2.2,<2.0" \
    "accelerate>=0.29.0,<0.35" \
    "mlflow>=2.14.0,<2.15" \
    "boto3>=1.34.0,<1.35" \
    "pandas>=2.2.0" \
    "scikit-learn>=1.4.0" \
    "joblib>=1.3.0" \
    "onnx>=1.16.0" \
    "onnxruntime>=1.17.0" \
    "opentelemetry-exporter-otlp-proto-grpc"

COPY . /workspace/service/

ENV PYTHONPATH=/workspace

CMD ["python", "-m", "arq", "service.main.WorkerSettings"]