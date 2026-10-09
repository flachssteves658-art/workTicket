# -*- coding: utf-8 -*-
# Windows PowerShell 脚本 - 交互式验证工作票模型
$REPO_PATH = "f:\project\mrc-for-flat-nested-ner"
$BERT_DIR = "$REPO_PATH\models\chinese-roberta-wwm-ext"
$QUERY_PATH = "$REPO_PATH\ner2mrc\queries\work_ticket.json"

# Auto-detect latest training folder (excluding lightning_logs)
$BASE_OUTPUT_DIR = "$REPO_PATH\outputs\work_ticket_model"
$LATEST_RUN = Get-ChildItem $BASE_OUTPUT_DIR | Where-Object { $_.PSIsContainer -and $_.Name -ne "lightning_logs" } | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# If no timestamped folder found, use the base directory itself (legacy structure)
if ($LATEST_RUN -eq $null) {
    Write-Host "No timestamped folders found, using base directory" -ForegroundColor Yellow
    $OUTPUT_DIR = $BASE_OUTPUT_DIR
} else {
    $OUTPUT_DIR = $LATEST_RUN.FullName
    Write-Host "Latest training directory detected: $OUTPUT_DIR" -ForegroundColor Yellow
}

# 在该文件夹内寻找最新的 checkpoint
$CKPT_FILE = Get-ChildItem "$OUTPUT_DIR\*.ckpt" -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($CKPT_FILE -eq $null) {
    Write-Host "Error: No checkpoint files (*.ckpt) found in $OUTPUT_DIR" -ForegroundColor Red
    exit 1
}

$CKPT = $CKPT_FILE.FullName

# 在该文件夹内寻找最新的 hparams.yaml
$HPARAMS_FILE = Get-ChildItem "$OUTPUT_DIR\hparams.yaml" -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1

if ($HPARAMS_FILE -eq $null) {
    Write-Host "Error: No hparams.yaml config file found in $OUTPUT_DIR" -ForegroundColor Red
    exit 1
}

$HPARAMS = $HPARAMS_FILE.FullName

Write-Host "Using model checkpoint: $CKPT" -ForegroundColor Cyan
Write-Host "Using config file: $HPARAMS" -ForegroundColor Cyan
Write-Host "Loading query templates: $QUERY_PATH" -ForegroundColor Cyan
Write-Host "Starting interactive inference interface..." -ForegroundColor Green

# 设置 PYTHONPATH
$env:PYTHONPATH = "$REPO_PATH"

# Run Python inference script
python "$REPO_PATH\inference\interactive_inference.py" `
    --model_ckpt "$CKPT" `
    --hparams_file "$HPARAMS" `
    --bert_dir "$BERT_DIR" `
    --query_path "$QUERY_PATH"
