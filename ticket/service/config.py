import os
from pathlib import Path

from dotenv import load_dotenv


SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
load_dotenv(Path(PROJECT_ROOT) / ".env")
# 本地联调时两个项目位于同一父目录；若 ticket/.env 未配置，复用识别项目令牌。
load_dotenv(
    Path(PROJECT_ROOT).parent / "Construction-Hazard-Detection" / ".env",
    override=False,
)

# ==============================================================================
# Configuration for Work Ticket Intelligent Parsing System
# ==============================================================================

# 1. Python Environment Paths
# IMPORTANT: Please update these paths to match your local environment!
# These should match the ones in your run_pipeline.bat
PADDLE_PYTHON = r"C:\Software\Anaconda\envs\workticket2-ocr\python.exe"
BERT_PYTHON = r"D:\Conda\envs\mrc_ner\python.exe"

# 2. Project Directories (Relative to this config file)
PADDLE_PROJECT_ROOT = os.path.join(PROJECT_ROOT, "paddle_models")
BERT_PROJECT_ROOT = os.path.join(PROJECT_ROOT, "mrc-for-flat-nested-ner")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "pipeline_output")

# 3. OCR Configuration and Script Paths
OCR_ENGINE = os.getenv("OCR_ENGINE", "ppstructure-v3")
OCR_USE_OPENCV_PREPROCESS = (
    os.getenv("OCR_USE_OPENCV_PREPROCESS", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
OCR_SCRIPT = "preprocess_and_ocr.py"
OCR_PRE_SCRIPT = "preprocess_and_ocr.py"
NER_SCRIPT = os.path.join("inference", "work_ticket_ner_from_ocr_json.py")

# 4. Neo4j Configuration
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j-rag")
NEO4J_URI = os.getenv("NEO4J_URI", f"http://localhost:7474/db/{NEO4J_DATABASE}/tx/commit")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")

# 5. Aliyun DashScope API Configuration
ALIYUN_API_KEY = os.getenv("ALIYUN_API_KEY", "sk-1a6a941a94374a199178cf7aa08aeb0a")
ALIYUN_BASE_URL = os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
ALIYUN_MODEL_NAME = os.getenv("ALIYUN_MODEL_NAME", "qwen-plus-2025-12-01")

# 6. LLM Provider Selection
# 可选值: 'ollama', 'aliyun'
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "aliyun")
LOW_CONF_THRESHOLD = float(os.getenv("LOW_CONF_THRESHOLD", "0.7"))

# 7. Construction Hazard Detection Integration
HAZARD_DBM_BASE_URL = os.getenv("HAZARD_DBM_BASE_URL", "http://127.0.0.1:8005")
HAZARD_INTEGRATION_TOKEN = os.getenv("HAZARD_INTEGRATION_TOKEN", "")

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)
