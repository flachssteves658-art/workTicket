# -*- coding: utf-8 -*-
# Windows PowerShell 脚本 - 交互式 NER 推理

# ==================== 配置路径 ====================
$REPO_PATH = "f:\project\mrc-for-flat-nested-ner"
$BERT_DIR = "$REPO_PATH\models\chinese-roberta-wwm-ext"

# 自动寻找输出目录下最新的 checkpoint
$OUTPUT_DIR = "$REPO_PATH\outputs\msra_train"
$CKPT = Get-ChildItem "$OUTPUT_DIR\*.ckpt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$HPARAMS = "$OUTPUT_DIR\lightning_logs\version_0\hparams.yaml"
# ================================================

if ($CKPT -eq $null) {
    Write-Host "错误: 未找到训练好的模型权重文件 (*.ckpt)" -ForegroundColor Red
    exit 1
}

Write-Host "使用模型: $($CKPT.FullName)" -ForegroundColor Cyan
Write-Host "启动交互式推理界面..." -ForegroundColor Green

# 设置 PYTHONPATH
$env:PYTHONPATH = "$REPO_PATH"

# 运行 Python 脚本
python "$REPO_PATH\inference\interactive_inference.py" `
    --model_ckpt "$($CKPT.FullName)" `
    --hparams_file "$HPARAMS" `
    --bert_dir "$BERT_DIR"
