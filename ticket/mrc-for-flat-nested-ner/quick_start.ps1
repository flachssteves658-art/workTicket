# MRC-NER Quick Start Script
# Single GPU Training

# Path Configuration
$REPO_PATH = "f:\project\mrc-for-flat-nested-ner"
$DATA_DIR = "$REPO_PATH\datasets\zh_msra"
$BERT_DIR = "$REPO_PATH\models\chinese-roberta-wwm-ext"
$OUTPUT_DIR = "$REPO_PATH\outputs\msra_train"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  MRC-NER Training - MSRA Dataset" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Green
Write-Host "  Project: $REPO_PATH"
Write-Host "  Data: $DATA_DIR"
Write-Host "  Model: $BERT_DIR"
Write-Host "  Output: $OUTPUT_DIR"
Write-Host "  GPU: 1"
Write-Host ""

# Check paths
if (!(Test-Path $DATA_DIR)) {
    Write-Host "ERROR: Data directory not found!" -ForegroundColor Red
    Write-Host "  Check: $DATA_DIR" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}

if (!(Test-Path $BERT_DIR)) {
    Write-Host "ERROR: BERT model directory not found!" -ForegroundColor Red
    Write-Host "  Check: $BERT_DIR" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit
}

Write-Host "Path check passed!" -ForegroundColor Green
Write-Host ""

# Set environment variables
$env:PYTHONPATH = "$REPO_PATH"
$env:TOKENIZERS_PARALLELISM = "false"
$env:CUDA_VISIBLE_DEVICES = "0"

# Create output directory
if (!(Test-Path $OUTPUT_DIR)) {
    New-Item -ItemType Directory -Path $OUTPUT_DIR -Force | Out-Null
    Write-Host "Output directory created: $OUTPUT_DIR" -ForegroundColor Green
}

Write-Host "Starting training..." -ForegroundColor Yellow
Write-Host ""

# Training parameters
$GPUS = "1"
$BATCH_SIZE = 4
$MAX_LENGTH = 128
$LR = "8e-6"
$MAX_EPOCHS = 20
$DROPOUT = 0.2
$SPAN_WEIGHT = 0.1
$INTER_HIDDEN = 1536
$PRECISION = 16
$VAL_CHECK = 0.25

# Run training
python "$REPO_PATH\train\mrc_ner_trainer.py" `
    --gpus=$GPUS `
    --data_dir $DATA_DIR `
    --bert_config_dir $BERT_DIR `
    --max_length $MAX_LENGTH `
    --batch_size $BATCH_SIZE `
    --precision=$PRECISION `
    --progress_bar_refresh_rate 1 `
    --lr $LR `
    --val_check_interval $VAL_CHECK `
    --accumulate_grad_batches 1 `
    --default_root_dir $OUTPUT_DIR `
    --mrc_dropout $DROPOUT `
    --max_epochs $MAX_EPOCHS `
    --weight_span $SPAN_WEIGHT `
    --span_loss_candidates "pred_and_gold" `
    --chinese `
    --workers 0 `
    --classifier_intermediate_hidden_size $INTER_HIDDEN

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Training completed!" -ForegroundColor Green
Write-Host "Models saved to: $OUTPUT_DIR" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
