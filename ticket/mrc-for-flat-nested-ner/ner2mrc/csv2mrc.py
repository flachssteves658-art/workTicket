#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将工作票 CSV 数据集（BIO格式）转换为 MRC-NER 格式
"""

import os
import csv
import json
import ast
from tokenizers import BertWordPieceTokenizer


def bio_to_token_spans(tokens, tags):
    """
    将 BIO 标签转换为 token 级别的实体跨度
    返回格式: [(start_token_idx, end_token_idx, label), ...]
    """
    spans = []
    i = 0

    while i < len(tokens):
        tag = tags[i]

        if tag.startswith('B-'):
            # 开始一个新实体
            label = tag[2:]  # 去掉 'B-' 前缀
            start_idx = i

            # 查找连续的 I- 标签
            j = i + 1
            while j < len(tokens) and tags[j] == f'I-{label}':
                j += 1

            end_idx = j - 1  # 结束位置（包含）
            spans.append((start_idx, end_idx, label))
            i = j
        else:
            i += 1

    return spans


def build_char_to_token_map(text, tokens):
    """
    构建字符位置到token位置的映射
    返回: 每个字符对应的token索引
    """
    char_to_token = []
    token_idx = 0
    pos = 0

    for char in text:
        if token_idx < len(tokens):
            token = tokens[token_idx]
            # 检查当前字符是否在当前token中
            token_start = text.find(token, pos)
            if token_start != -1 and pos >= token_start and pos < token_start + len(token):
                char_to_token.append(token_idx)
                if pos == token_start + len(token) - 1:
                    # 当前token结束，移到下一个token
                    token_idx += 1
                    pos = token_start + len(token)
                else:
                    pos += 1
            else:
                # 当前字符不在任何token中（可能是空格或标点）
                char_to_token.append(-1)
                pos += 1
        else:
            char_to_token.append(-1)
            pos += 1

    return char_to_token


def convert_csv_to_mrc(csv_path, output_path, query_map, tokenizer):
    """
    转换 CSV 文件为 MRC 格式的 JSON
    """
    mrc_samples = []
    total_rows = 0
    success_rows = 0
    skipped_entities = 0

    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            total_rows += 1
            text = row['text']

            try:
                # 解析 tokens 和 ner_tags
                tokens = ast.literal_eval(row['tokens'])
                tags = ast.literal_eval(row['ner_tags'])

                if len(tokens) != len(tags):
                    print(f"警告: 第{total_rows}行 tokens 和 tags 长度不匹配")
                    continue

                # 移除原文中的空格，避免产生双空格问题
                text_no_space = text.replace(' ', '')

                # 构建 context：每个字符用空格分隔
                spaced_context = ' '.join(list(text_no_space))

                # 使用 tokenizer 获取有效的位置映射
                # 注意：训练时会用 "".join(context.split()) 得到 text_no_space
                encoded = tokenizer.encode(text_no_space)
                valid_starts = set()
                valid_ends = set()
                for offset in encoded.offsets:
                    if offset[0] != offset[1]:  # 跳过特殊 token
                        valid_starts.add(offset[0])
                        valid_ends.add(offset[1] - 1)  # 转为包含式结束位置

                # 将 BIO 转换为 token 级别的跨度
                token_spans = bio_to_token_spans(tokens, tags)
                success_rows += 1

                # 按标签分组
                label_spans = {}
                # 为了处理同一实体多次出现的情况，我们需要按顺序寻找位置
                current_search_pos = 0

                # 注意：token_spans 已经是按顺序排列的（来自 bio_to_token_spans）
                for start_token, end_token, label in token_spans:
                    if label not in label_spans:
                        label_spans[label] = []

                    # 将 token 索引转换为字符索引
                    entity_tokens = tokens[start_token:end_token+1]
                    entity_text = ''.join(entity_tokens)
                    entity_text_no_space = entity_text.replace(' ', '')

                    # 在无空格文本中查找实体的字符位置，从上一个查找到的位置之后开始找
                    char_start = text_no_space.find(
                        entity_text_no_space, current_search_pos)
                    if char_start != -1:
                        char_end = char_start + len(entity_text_no_space) - 1
                        # 更新搜索起始位置
                        current_search_pos = char_end + 1

                        # 验证位置是否为 tokenizer 的有效边界
                        if char_start in valid_starts and char_end in valid_ends:
                            label_spans[label].append((char_start, char_end))
                        else:
                            # 尝试调整到最近的有效位置
                            adjusted_start = char_start
                            adjusted_end = char_end

                            # 如果 start 无效，向后找最近的有效位置
                            while adjusted_start <= char_end and adjusted_start not in valid_starts:
                                adjusted_start += 1

                            # 如果 end 无效，向前找最近的有效位置
                            while adjusted_end >= adjusted_start and adjusted_end not in valid_ends:
                                adjusted_end -= 1

                            if adjusted_start <= adjusted_end and adjusted_start in valid_starts and adjusted_end in valid_ends:
                                label_spans[label].append(
                                    (adjusted_start, adjusted_end))
                            else:
                                skipped_entities += 1
                                # print(f"警告: 第{total_rows}行实体 '{entity_text}' 位置无法对齐到 token 边界")
                    else:
                        skipped_entities += 1
                        # print(f"警告: 第{total_rows}行找不到实体 '{entity_text}'")

                # 为每个查询生成 MRC 样本
                for label, query in query_map.items():
                    if label in label_spans:
                        starts = [s[0] for s in label_spans[label]]
                        ends = [s[1] for s in label_spans[label]]
                        impossible = False
                    else:
                        starts = []
                        ends = []
                        impossible = True

                    mrc_samples.append({
                        "qas_id": f"{total_rows}.{list(query_map.keys()).index(label)}",
                        "context": spaced_context,
                        "query": query,
                        "start_position": starts,
                        "end_position": ends,
                        "entity_label": label,
                        "impossible": impossible
                    })

            except Exception as e:
                print(f"错误: 第{total_rows}行处理失败 - {e}")
                import traceback
                traceback.print_exc()
                continue

    # 保存为 JSON
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mrc_samples, f, ensure_ascii=False, indent=2)

    print(f"✅ 转换完成:")
    print(f"   输入: {csv_path}")
    print(f"   输出: {output_path}")
    print(f"   处理: {success_rows}/{total_rows} 行")
    print(f"   跳过实体: {skipped_entities} 个（无法对齐到 token 边界）")
    print(f"   生成: {len(mrc_samples)} 个 MRC 样本")
    return len(mrc_samples)


def main():
    # 路径配置
    data_dir = r"f:\project\mrc-for-flat-nested-ner\datasets\processed_dataset"
    output_dir = r"f:\project\mrc-for-flat-nested-ner\datasets\work_ticket"
    query_file = r"f:\project\mrc-for-flat-nested-ner\ner2mrc\queries\work_ticket.json"
    bert_dir = r"f:\project\mrc-for-flat-nested-ner\models\chinese-roberta-wwm-ext"

    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"创建输出目录: {output_dir}")

    # 加载 tokenizer
    vocab_file = os.path.join(bert_dir, "vocab.txt")
    print(f"\n加载 tokenizer: {vocab_file}")
    tokenizer = BertWordPieceTokenizer(vocab_file)

    # 加载查询映射
    with open(query_file, 'r', encoding='utf-8') as f:
        query_map = json.load(f)

    print(f"\n加载查询定义: {len(query_map)} 个实体类型")
    for label, query in query_map.items():
        print(f"  - {label}: {query[:30]}...")

    print("\n" + "="*60)

    # 转换三个数据集
    phase_map = {'train': 'train', 'val': 'dev', 'test': 'test'}
    total_samples = 0

    for split in ['train', 'val', 'test']:
        csv_file = os.path.join(data_dir, f"{split}.csv")
        output_file = os.path.join(output_dir, f"mrc-ner.{phase_map[split]}")

        if os.path.exists(csv_file):
            print(f"\n处理 {split} 数据集...")
            count = convert_csv_to_mrc(
                csv_file, output_file, query_map, tokenizer)
            total_samples += count
        else:
            print(f"⚠️  跳过 {split}: 文件不存在 {csv_file}")

    print("\n" + "="*60)
    print(f"🎉 全部完成! 总共生成 {total_samples} 个 MRC 样本")
    print(f"数据集保存在: {output_dir}")


if __name__ == "__main__":
    main()
