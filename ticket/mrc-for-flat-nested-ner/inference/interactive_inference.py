#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import torch
import argparse
import json
import yaml
from tokenizers import BertWordPieceTokenizer
from train.mrc_ner_trainer import BertLabeling
from metrics.functional.query_span_f1 import extract_flat_spans

# 修复 PyYAML 6.0+ 的兼容性问题
if hasattr(yaml, 'FullLoader'):
    _old_load = yaml.load

    def new_load(stream, Loader=yaml.FullLoader, **kwargs):
        return _old_load(stream, Loader=Loader, **kwargs)
    yaml.load = new_load


class InteractiveInference:
    def __init__(self, model_ckpt, hparams_file, bert_dir, query_path=None, is_chinese=True):
        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu")
        print(f"正在加载模型到设备: {self.device}...")

        # 加载模型
        self.model = BertLabeling.load_from_checkpoint(
            checkpoint_path=model_ckpt,
            hparams_file=hparams_file,
            map_location=self.device
        )
        self.model.model.to(self.device)
        self.model.model.eval()

        # 加载分词器
        vocab_path = os.path.join(bert_dir, "vocab.txt")
        self.tokenizer = BertWordPieceTokenizer(vocab_path)
        if hasattr(self.tokenizer, "enable_truncation"):
            self.tokenizer.enable_truncation(512)
        self.is_chinese = is_chinese

        # 加载查询定义
        if query_path and os.path.exists(query_path):
            print(f"从 {query_path} 加载查询定义...")
            with open(query_path, 'r', encoding='utf-8') as f:
                self.queries = json.load(f)
        else:
            print("未提供查询路径或文件不存在，使用默认 MSRA 查询定义。")
            # MSRA 实体查询定义
            self.queries = {
                "PER": "人名和虚构的人物形象",
                "LOC": "按照地理位置划分的国家,城市,乡镇,大洲",
                "ORG": "组织包括公司,政府党派,学校,政府,新闻机构"
            }

    def predict(self, text):
        all_entities = []

        # 针对中文移除空格，以匹配训练时的预处理逻辑 (MRCNERDataset)
        if self.is_chinese:
            text = "".join(text.split())

        for label_cate, query in self.queries.items():
            # 编码输入: [CLS] query [SEP] context [SEP]
            encoded = self.tokenizer.encode(query, text)

            tokens = torch.tensor([encoded.ids]).to(self.device)
            token_type_ids = torch.tensor([encoded.type_ids]).to(self.device)
            attention_mask = torch.tensor(
                [encoded.attention_mask]).to(self.device)

            with torch.no_grad():
                start_logits, end_logits, span_logits = self.model.model(
                    tokens,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids
                )

            # 提取实体
            start_preds = start_logits > 0
            end_preds = end_logits > 0
            span_preds = span_logits > 0

            entities_info = extract_flat_spans(
                torch.squeeze(start_preds),
                torch.squeeze(end_preds),
                torch.squeeze(span_preds),
                torch.squeeze(attention_mask),
                pseudo_tag=label_cate
            )

            # 解析实体文本
            subtokens = encoded.tokens
            for entity_info in entities_info:
                start, end = entity_info[0], entity_info[1]
                # 注意：这里需要跳过 query 部分
                # type_ids 为 0 的是 query，为 1 的是 context
                if encoded.type_ids[start] == 1:
                    # 尝试恢复原始文本中的位置或直接拼接 subtoken
                    # 为了演示简单，这里直接解码对应的 ids
                    entity_text = self.tokenizer.decode(
                        encoded.ids[start:end], skip_special_tokens=True)
                    # 清理空格（针对中文）
                    if self.is_chinese:
                        entity_text = entity_text.replace(" ", "")

                    all_entities.append({
                        "text": entity_text,
                        "type": label_cate,
                        "start": start,
                        "end": end
                    })

        return all_entities


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_ckpt", type=str,
                        required=True, help="模型权重文件路径")
    parser.add_argument("--hparams_file", type=str,
                        required=True, help="hparams.yaml文件路径")
    parser.add_argument("--bert_dir", type=str, required=True, help="BERT模型目录")
    parser.add_argument("--query_path", type=str,
                        default=None, help="查询定义 JSON 文件路径")
    args = parser.parse_args()

    predictor = InteractiveInference(
        args.model_ckpt, args.hparams_file, args.bert_dir, query_path=args.query_path)

    print("\n" + "="*50)
    print("模型已就绪！请输入你想测试的句子 (输入 'quit' 退出)")
    print("="*50)

    while True:
        try:
            text = input("\n请输入句子: ").strip()
            if not text:
                continue
            if text.lower() == 'quit':
                break

            results = predictor.predict(text)

            if not results:
                print("未识别到任何实体。")
            else:
                print(f"识别到 {len(results)} 个实体:")
                for res in results:
                    print(f"  - [{res['type']}] {res['text']}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"发生错误: {e}")


if __name__ == "__main__":
    main()
