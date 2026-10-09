# -*- coding: utf-8 -*-
# file: evaluate.ps1
# Windows PowerShell 脚本 - 模型评估

# ==================== 请根据实际情况修改以下路径 ====================
$REPO_PATH = "f:\project\工作票提取\mrc-for-flat-nested-ner"
$OUTPUT_DIR = "f:\outputs\zh_msra"                      # 训练输出目录

# 最佳checkpoint路径（请在 $OUTPUT_DIR\train_log.txt 中查找dev集上的最佳epoch）
$BEST_CKPT_DEV = "$OUTPUT_DIR\epoch=8.ckpt"
$PYTORCHLIGHT_HPARAMS = "$OUTPUT_DIR\lightning_logs\version_0\hparams.yaml"

# GPU配置
$GPU_ID = "0"
# ==================================================================

# 设置环境变量
$env:PYTHONPATH = "$env:PYTHONPATH;$REPO_PATH"

Write-Host "开始评估模型..." -ForegroundColor Green
Write-Host "Checkpoint: $BEST_CKPT_DEV"
Write-Host "Hparams: $PYTORCHLIGHT_HPARAMS"

# 检查文件是否存在
if (!(Test-Path $BEST_CKPT_DEV)) {
    Write-Host "错误: Checkpoint文件不存在: $BEST_CKPT_DEV" -ForegroundColor Red
    exit 1
}

if (!(Test-Path $PYTORCHLIGHT_HPARAMS)) {
    Write-Host "错误: Hparams文件不存在: $PYTORCHLIGHT_HPARAMS" -ForegroundColor Red
    exit 1
}

# 运行评估
python "$REPO_PATH\evaluate\mrc_ner_evaluate.py" $BEST_CKPT_DEV $PYTORCHLIGHT_HPARAMS $GPU_ID
