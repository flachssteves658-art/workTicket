# -*- coding: utf-8 -*-
# file: msra.ps1
# Windows PowerShell 脚本 - 中文 MSRA 数据集训练

# ==================== 请根据实际情况修改以下路径 ====================
$REPO_PATH = "f:\project\工作票提取\mrc-for-flat-nested-ner"
$DATA_DIR = "f:\data\zh_msra"                           # 数据集路径
$BERT_DIR = "f:\models\chinese_roberta_wwm_large_ext_pytorch"  # BERT模型路径
$OUTPUT_DIR = "f:\outputs\zh_msra"                      # 输出目录
# ==================================================================

# 设置环境变量
$env:PYTHONPATH = "$env:PYTHONPATH;$REPO_PATH"
$env:TOKENIZERS_PARALLELISM = "false"

# 超参数配置
$SPAN_WEIGHT = 0.1
$DROPOUT = 0.2
$LR = "8e-6"
$MAXLEN = 128
$INTER_HIDDEN = 1536

$BATCH_SIZE = 4
$PREC = 16
$VAL_CKPT = 0.25
$ACC_GRAD = 1
$MAX_EPOCH = 20
$SPAN_CANDI = "pred_and_gold"
$PROGRESS_BAR = 1

# GPU配置（如果只有一块GPU，改为 "0" 和 gpus="1"）
$env:CUDA_VISIBLE_DEVICES = "0,1"
$GPUS = "2"

# 创建输出目录
if (!(Test-Path $OUTPUT_DIR)) {
    New-Item -ItemType Directory -Path $OUTPUT_DIR -Force | Out-Null
}

Write-Host "开始训练 MSRA 数据集..." -ForegroundColor Green
Write-Host "数据目录: $DATA_DIR"
Write-Host "BERT目录: $BERT_DIR"
Write-Host "输出目录: $OUTPUT_DIR"

# 运行训练
python "$REPO_PATH\train\mrc_ner_trainer.py" `
    --gpus="$GPUS" `
    --distributed_backend=ddp `
    --data_dir $DATA_DIR `
    --bert_config_dir $BERT_DIR `
    --max_length $MAXLEN `
    --batch_size $BATCH_SIZE `
    --precision=$PREC `
    --progress_bar_refresh_rate $PROGRESS_BAR `
    --lr $LR `
    --val_check_interval $VAL_CKPT `
    --accumulate_grad_batches $ACC_GRAD `
    --default_root_dir $OUTPUT_DIR `
    --mrc_dropout $DROPOUT `
    --max_epochs $MAX_EPOCH `
    --weight_span $SPAN_WEIGHT `
    --span_loss_candidates $SPAN_CANDI `
    --chinese `
    --workers 0 `
    --classifier_intermediate_hidden_size $INTER_HIDDEN
