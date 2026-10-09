# 工作票智能解析与时空关联系统 (Ticket) 说明书

## 1. 项目简介

本项目旨在实现电力工作票的智能解析与知识图谱构建。通过 **PaddleOCR** 进行图像文字提取，结合 **BERT-MRC** 和 **LLM (Qwen)** 进行实体识别 (NER)，最终将结构化数据存入 **Neo4j** 构建时空关联知识图谱。

## 2. 核心技术栈

- **OCR**: PaddleOCR (版面分析 + 文字识别)
- **NER**: BERT-MRC (阅读理解式实体识别), BERT-WWM, Qwen3-VL (多模态大模型)
- **Graph DB**: Neo4j (存储时空知识图谱)
- **Backend**: FastAPI
- **UI**: Gradio

## 3. 目录结构说明

- **`mrc-for-flat-nested-ner/`**: **[核心]** BERT-MRC 模型实现目录。
  - `models/`: BERT 模型定义。
  - `inference/`: 推理脚本。
  - `train/`: 训练脚本。
  - `datasets/`: 数据集处理。
- **`paddle_models/`**: **[核心]** PaddleOCR 相关代码。
  - `preprocess_and_ocr.py`: OCR 运行入口，默认使用 PPStructureV3，并可切换 PaddleOCR-VL 1.5/1.6。
  - `run_ocr.py`: 旧版 PaddleOCR-VL 运行入口。
- **`service/`**: **[核心]** 整合服务层。
  - `api_server.py`: FastAPI 后端接口。
  - `core_pipeline.py` / `unified_pipeline.py`: 核心处理流水线。
  - `neo4j_client.py`: 图数据库交互。
  - `web_ui.py`: Gradio 演示界面。
- **`pipeline_output/`**: 流水线运行结果输出目录。

## 4. 关键脚本与启动

### 4.1 完整流水线测试

- **脚本**: `service/run_pipeline.bat [图片路径]`
- **功能**: 对指定图片执行 "OCR -> NER" 完整流程。
- **输出**: 结果保存在 `pipeline_output/` 目录下（含 JSON 结果与中间文件）。
- **OCR 引擎**: 默认 `ppstructure-v3`，可通过环境变量 `OCR_ENGINE` 或
  `preprocess_and_ocr.py --ocr_engine` 切换为 `paddleocr-vl-1.5` /
  `paddleocr-vl-1.6`。

### 4.2 Web 演示界面

- **脚本**: `service/run_web_ui.bat`
- **功能**: 启动 Gradio Web UI (默认 http://localhost:7860)。
- **交互**: 支持上传图片、查看解析结果、可视化知识图谱。

### 4.3 API 服务

- **入口**: `service/api_server.py`
- **功能**: 提供 RESTful API 供外部系统调用。

## 5. 更多文档

- 技术路线详情: `基于多模态大模型的工作票智能解析与时空关联技术——实施技术路线.md`
- Service 模块说明: `service/service_overview.md`


### tiket 项目环境ticket-service
conda create -n ticket-service python=3.11 -y
conda activate ticket-service

Set-Location 'D:\工作票项目文件\项目demo\项目demo\ticket'

python -m pip install -r '.\requirements_service.txt'
python '.\service\web_ui.py'
###