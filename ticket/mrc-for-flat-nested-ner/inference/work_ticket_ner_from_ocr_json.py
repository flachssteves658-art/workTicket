import os
import json
import argparse
import re
from pathlib import Path

from inference.interactive_inference import InteractiveInference
from inference.kg_builder import KnowledgeGraphBuilder


class TextCleaner:
    """
    Implements text cleaning rules defined in Section 2.3 of the technical route.
    """
    def __init__(self):
        # Terminology map: key -> standard value
        self.term_map = {
            "刀闸": "隔离开关",
            "PT": "电压互感器",
            "CT": "电流互感器",
        }

    def clean_text(self, text):
        # 1. Remove noise (spaces, invisible chars) - already partially done by stripped, but let's be thorough
        text = "".join(text.split())
        
        # 2. Terminology Standardization
        for term, standard in self.term_map.items():
            text = text.replace(term, standard)
            
        # 3. Time Normalization (Simple Regex for YYYY.MM.DD -> YYYY-MM-DD)
        # Matches 2024.5.6 or 2024/5/6 or 2024年5月6日
        # This is a basic implementation.
        text = re.sub(r'(\d{4})[./年](\d{1,2})[./月](\d{1,2})[日]?', r'\1-\2-\3', text)
        
        return text


def auto_find_work_ticket_model(repo_root):
    outputs_root = Path(repo_root) / "outputs" / "work_ticket_model"
    if not outputs_root.exists():
        raise RuntimeError(f"outputs directory not found: {outputs_root}")
    run_dirs = [d for d in outputs_root.iterdir() if d.is_dir()]
    if not run_dirs:
        raise RuntimeError("no work_ticket_model run directories found")
    latest_run = max(run_dirs, key=lambda d: d.stat().st_mtime)
    ckpts = sorted(latest_run.glob("*.ckpt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not ckpts:
        raise RuntimeError(f"no checkpoint found in {latest_run}")
    ckpt_path = ckpts[0]
    hparams_file = latest_run / "lightning_logs" / "version_0" / "hparams.yaml"
    if not hparams_file.exists():
        raise RuntimeError(f"hparams.yaml not found: {hparams_file}")
    bert_dir = Path(repo_root) / "models" / "chinese-roberta-wwm-ext"
    if not bert_dir.exists():
        raise RuntimeError(f"bert dir not found: {bert_dir}")
    query_path = Path(repo_root) / "ner2mrc" / "queries" / "work_ticket.json"
    if not query_path.exists():
        query_path = None
    return ckpt_path, hparams_file, bert_dir, query_path


def collect_texts_from_ocr_json(ocr_json_path):
    with open(ocr_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    texts = []
    for block in data.get("parsing_res_list", []):
        label = block.get("block_label", "")
        content = block.get("block_content", "")
        if not content:
            continue
        if label in {"doc_title", "text", "header", "paragraph", "form"}:
            texts.append(content)
        elif label == "table":
            cleaned = content.replace("<br>", " ")
            current = []
            in_tag = False
            for ch in cleaned:
                if ch == "<":
                    in_tag = True
                    continue
                if ch == ">":
                    in_tag = False
                    continue
                if not in_tag:
                    current.append(ch)
            plain = "".join(current).strip()
            if plain:
                texts.append(plain)
    return data, texts


def run_ner_on_ocr_json(ocr_json_path, output_json_path, model_ckpt=None, hparams_file=None, bert_dir=None, query_path=None):
    repo_root = Path(__file__).resolve().parents[1]
    if not model_ckpt or not hparams_file or not bert_dir:
        ckpt_path, hparams, bert, query = auto_find_work_ticket_model(repo_root)
        if not model_ckpt:
            model_ckpt = ckpt_path
        if not hparams_file:
            hparams_file = hparams
        if not bert_dir:
            bert_dir = bert
        if not query_path:
            query_path = query
    predictor = InteractiveInference(
        str(model_ckpt),
        str(hparams_file),
        str(bert_dir),
        query_path=str(query_path) if query_path else None,
    )
    
    cleaner = TextCleaner()
    ocr_data, texts = collect_texts_from_ocr_json(ocr_json_path)
    blocks = []
    for text in texts:
        # Apply Section 2.3 Cleaning
        text_cleaned = cleaner.clean_text(text)
        if not text_cleaned:
            continue
        entities = predictor.predict(text_cleaned)
        blocks.append(
            {
                "text": text_cleaned,
                "entities": entities,
            }
        )
    result = {
        "ocr_source": str(ocr_json_path),
        "mrc_model": {
            "checkpoint": str(model_ckpt),
            "hparams_file": str(hparams_file),
            "bert_dir": str(bert_dir),
            "query_path": str(query_path) if query_path else None,
        },
        "blocks": blocks,
        "ocr_meta": {
            "input_path": ocr_data.get("input_path"),
            "width": ocr_data.get("width"),
            "height": ocr_data.get("height"),
        },
    }
    output_json_path = Path(output_json_path)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # Section 5: Knowledge Graph Construction
    kg_builder = KnowledgeGraphBuilder()
    kg_builder.process_ner_results(result)
    cypher_output_path = output_json_path.with_name(output_json_path.stem + "_graph.cypher")
    kg_builder.save_cypher(cypher_output_path)
    print(f"Knowledge Graph Import Query saved to: {cypher_output_path}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr_json", type=str, required=True)
    parser.add_argument("--output_json", type=str, required=True)
    parser.add_argument("--model_ckpt", type=str, default=None)
    parser.add_argument("--hparams_file", type=str, default=None)
    parser.add_argument("--bert_dir", type=str, default=None)
    parser.add_argument("--query_path", type=str, default=None)
    args = parser.parse_args()
    ocr_json_path = Path(args.ocr_json)
    if not ocr_json_path.exists():
        raise RuntimeError(f"ocr json not found: {ocr_json_path}")
    run_ner_on_ocr_json(
        ocr_json_path,
        Path(args.output_json),
        model_ckpt=args.model_ckpt,
        hparams_file=args.hparams_file,
        bert_dir=args.bert_dir,
        query_path=args.query_path,
    )


if __name__ == "__main__":
    main()

