import os
import subprocess
import uuid
import json
import shutil
import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))
import config

class PipelineRunner:
    @staticmethod
    def run_pipeline(image_path: str):
        """
        Executes the full Work Ticket Parsing Pipeline:
        Image -> PaddleOCR -> BERT-MRC -> JSON/Graph
        """
        image_path = Path(image_path)
        if not image_path.exists():
            return {"error": f"Image file not found: {image_path}"}

        # Generate a unique session ID for this run to avoid collisions
        session_id = uuid.uuid4().hex[:8]
        filename_no_ext = image_path.stem
        
        # ----------------------------------------------------------------------
        # Step 1: PaddleOCR
        # ----------------------------------------------------------------------
        print(f"[{session_id}] Starting OCR Step...")
        ocr_cmd = [
            config.PADDLE_PYTHON,
            config.OCR_SCRIPT,
            "--image_path", str(image_path),
            "--output_dir", config.OUTPUT_DIR,
            "--ocr_engine", config.OCR_ENGINE,
        ]
        if config.OCR_USE_OPENCV_PREPROCESS:
            ocr_cmd.append("--opencv_preprocess")
        
        try:
            subprocess.run(
                ocr_cmd, 
                cwd=config.PADDLE_PROJECT_ROOT, 
                check=True, 
                capture_output=True, 
                text=True,
                encoding='utf-8' # Ensure encoding handles Chinese output
            )
        except subprocess.CalledProcessError as e:
            print(f"OCR Error Output: {e.stderr}")
            return {"error": "OCR Step failed", "details": e.stderr}

        ocr_json_path = Path(config.OUTPUT_DIR) / f"{filename_no_ext}.json"
        if not ocr_json_path.exists():
            return {"error": "OCR output JSON not found"}

        # ----------------------------------------------------------------------
        # Step 2: BERT-MRC
        # ----------------------------------------------------------------------
        print(f"[{session_id}] Starting NER Step...")
        ner_output_json = Path(config.OUTPUT_DIR) / f"{filename_no_ext}_ner.json"
        
        ner_cmd = [
            config.BERT_PYTHON,
            config.NER_SCRIPT,
            "--ocr_json", str(ocr_json_path),
            "--output_json", str(ner_output_json)
        ]
        
        try:
            subprocess.run(
                ner_cmd, 
                cwd=config.BERT_PROJECT_ROOT, 
                check=True, 
                capture_output=True, 
                text=True,
                encoding='utf-8'
            )
        except subprocess.CalledProcessError as e:
            print(f"NER Error Output: {e.stderr}")
            return {"error": "NER Step failed", "details": e.stderr}

        if not ner_output_json.exists():
            return {"error": "NER output JSON not found"}

        # ----------------------------------------------------------------------
        # Step 3: Load Results
        # ----------------------------------------------------------------------
        with open(ner_output_json, 'r', encoding='utf-8') as f:
            ner_data = json.load(f)

        # Load Graph Data (Cypher)
        cypher_path = Path(config.OUTPUT_DIR) / f"{filename_no_ext}_ner_graph.cypher"
        cypher_query = ""
        if cypher_path.exists():
            with open(cypher_path, 'r', encoding='utf-8') as f:
                cypher_query = f.read()

        return {
            "status": "success",
            "ocr_json_path": str(ocr_json_path),
            "ner_json_path": str(ner_output_json),
            "result": ner_data,
            "knowledge_graph_cypher": cypher_query
        }
