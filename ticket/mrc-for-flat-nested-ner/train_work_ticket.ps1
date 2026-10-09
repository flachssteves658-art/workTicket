# Work Ticket Information Extraction Model Training Script

# ============================================================
#                    PATH CONFIGURATION
# ============================================================
$REPO_PATH = "f:\project\mrc-for-flat-nested-ner"
$DATA_DIR = "$REPO_PATH\datasets\work_ticket"
$BERT_DIR = "$REPO_PATH\models\chinese-roberta-wwm-ext"
$OUTPUT_DIR = "$REPO_PATH\outputs\work_ticket_model"
# ============================================================

Write-Host "`n" -NoNewline
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "          WORK TICKET MODEL TRAINING" -ForegroundColor Cyan
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[Configuration]" -ForegroundColor Green
Write-Host "  Project Path    : " -NoNewline; Write-Host "$REPO_PATH" -ForegroundColor White
Write-Host "  Dataset         : " -NoNewline; Write-Host "$DATA_DIR" -ForegroundColor White
Write-Host "  Base Model      : " -NoNewline; Write-Host "$BERT_DIR" -ForegroundColor White
Write-Host "  Output Location : " -NoNewline; Write-Host "$OUTPUT_DIR" -ForegroundColor White
Write-Host "  GPU Device      : " -NoNewline; Write-Host "1" -ForegroundColor White
Write-Host ""

# Path validation
Write-Host "[Path Validation]" -ForegroundColor Yellow
if (!(Test-Path $DATA_DIR)) {
    Write-Host "  ✗ " -ForegroundColor Red -NoNewline
    Write-Host "Data directory not found: $DATA_DIR" -ForegroundColor Red
    Read-Host "`nPress Enter to exit"
    exit 1
}

if (!(Test-Path $BERT_DIR)) {
    Write-Host "  ✗ " -ForegroundColor Red -NoNewline
    Write-Host "BERT model not found: $BERT_DIR" -ForegroundColor Red
    Read-Host "`nPress Enter to exit"
    exit 1
}

Write-Host "  ✓ " -ForegroundColor Green -NoNewline
Write-Host "All paths validated successfully" -ForegroundColor Green
Write-Host ""

# Environment setup
Write-Host "[Environment Setup]" -ForegroundColor Yellow
$env:PYTHONPATH = "$REPO_PATH"
$env:TOKENIZERS_PARALLELISM = "false"
$env:CUDA_VISIBLE_DEVICES = "0"

Write-Host "  ✓ " -ForegroundColor Green -NoNewline
Write-Host "Environment variables configured" -ForegroundColor Green
Write-Host ""

# Output directory
if (!(Test-Path $OUTPUT_DIR)) {
    New-Item -ItemType Directory -Path $OUTPUT_DIR -Force | Out-Null
    Write-Host "  ✓ " -ForegroundColor Green -NoNewline
    Write-Host "Output directory created" -ForegroundColor Green
}

Write-Host ""
Write-Host "-----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "                   TRAINING STARTED" -ForegroundColor Yellow
Write-Host "-----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# Training parameters (optimized for work ticket dataset)
$GPUS = "1"
$BATCH_SIZE = 8
$MAX_LENGTH = 256
$LR = "3e-5"
$MAX_EPOCHS = 30
$DROPOUT = 0.1
$SPAN_WEIGHT = 0.1
$INTER_HIDDEN = 1536
$PRECISION = 16
$VAL_CHECK = 1.0

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
Write-Host "-----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "                   TRAINING COMPLETED" -ForegroundColor Green
Write-Host "-----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""
Write-Host "[Output Location]" -ForegroundColor Cyan
Write-Host "  Base Directory  : " -NoNewline; Write-Host "$OUTPUT_DIR" -ForegroundColor White
Write-Host "  Storage Strategy: " -NoNewline; Write-Host "Timestamped subdirectories" -ForegroundColor Gray
Write-Host ""
Write-Host "[Next Steps]" -ForegroundColor Cyan
Write-Host "  1. Interactive Verification  : " -NoNewline; Write-Host ".\verify_work_ticket.ps1" -ForegroundColor White
Write-Host "  2. Full Evaluation (Metrics) : " -NoNewline; Write-Host ".\evaluate_work_ticket.ps1" -ForegroundColor White
Write-Host ""
Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host ""
