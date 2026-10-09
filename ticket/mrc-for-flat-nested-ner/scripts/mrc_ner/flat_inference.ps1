# -*- coding: utf-8 -*-
# file: flat_inference.ps1
# Windows PowerShell 脚本 - 扁平NER推理（适用于无嵌套实体的数据集）

# ==================== 请根据实际情况修改以下路径 ====================
$REPO_PATH = "f:\project\工作票提取\mrc-for-flat-nested-ner"

# 数据集配置
$DATA_SIGN = "conll03"                                  # 数据集标识
$DATA_DIR = "f:\data\en_conll03"                        # 数据集路径
$BERT_DIR = "f:\models\bert-base-uncased"               # BERT模型路径
$MAX_LEN = 180

# 模型checkpoint路径
$MODEL_CKPT = "f:\outputs\conll03\epoch=1.ckpt"
$HPARAMS_FILE = "f:\outputs\conll03\lightning_logs\version_0\hparams.yaml"
# ==================================================================

# 设置环境变量
$env:PYTHONPATH = "$env:PYTHONPATH;$REPO_PATH"

Write-Host "开始扁平NER推理..." -ForegroundColor Green
Write-Host "数据集: $DATA_SIGN"
Write-Host "数据目录: $DATA_DIR"
Write-Host "模型Checkpoint: $MODEL_CKPT"

# 检查文件是否存在
if (!(Test-Path $MODEL_CKPT)) {
    Write-Host "错误: 模型Checkpoint不存在: $MODEL_CKPT" -ForegroundColor Red
    exit 1
}

# 运行推理
python "$REPO_PATH\inference\mrc_ner_inference.py" `
    --data_dir $DATA_DIR `
    --bert_dir $BERT_DIR `
    --max_length $MAX_LEN `
    --model_ckpt $MODEL_CKPT `
    --hparams_file $HPARAMS_FILE `
    --flat_ner `
    --dataset_sign $DATA_SIGN
