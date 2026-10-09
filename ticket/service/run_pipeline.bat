@echo off
setlocal EnableDelayedExpansion

REM ============================================================================
REM Work Ticket Intelligent Parsing Pipeline - Launcher Script
REM ============================================================================

REM ----------------------------------------------------------------------------
REM [CONFIGURATION]
REM ----------------------------------------------------------------------------

REM Get the directory where this script resides (service/)
set SERVICE_DIR=%~dp0
REM Go up one level to project root
pushd "%SERVICE_DIR%.."
set PROJECT_ROOT=%CD%
popd

REM 1. Path to python.exe (WARNING: These need to be configured in config.py too!)
REM    Ideally, update these to match your local environment or use config.py values.
set PADDLE_PYTHON=C:\Users\Administrator\miniconda3\envs\paddle_env\python.exe
set BERT_PYTHON=C:\Users\Administrator\miniconda3\envs\bert_env\python.exe

REM 2. Project Directories (Relative to script location)
set PADDLE_PROJECT_ROOT=%PROJECT_ROOT%\paddle_models
set BERT_PROJECT_ROOT=%PROJECT_ROOT%\mrc-for-flat-nested-ner

REM 3. Default Output Directory
set PIPELINE_OUTPUT_DIR=%PROJECT_ROOT%\pipeline_output
set OCR_ENGINE=ppstructure-v3

REM ----------------------------------------------------------------------------

REM Check if input image is provided
set INPUT_IMAGE=%~1
if "%INPUT_IMAGE%"=="" (
    echo.
    echo Usage: run_pipeline.bat [Path to Image]
    echo Example: run_pipeline.bat "%PADDLE_PROJECT_ROOT%\img\test.jpg"
    echo.
    goto :EOF
)

if not exist "%INPUT_IMAGE%" (
    echo Error: Input image file not found: %INPUT_IMAGE%
    goto :EOF
)

echo ============================================================================
echo [START] Processing Work Ticket: %INPUT_IMAGE%
echo ============================================================================

REM Create output directory
if not exist "%PIPELINE_OUTPUT_DIR%" mkdir "%PIPELINE_OUTPUT_DIR%"

REM ----------------------------------------------------------------------------
REM Step 1: Run PaddleOCR
REM ----------------------------------------------------------------------------
echo.
echo [Step 1/2] Running PaddleOCR...
echo ----------------------------------------------------------------------------

cd /d "%PADDLE_PROJECT_ROOT%"
"%PADDLE_PYTHON%" preprocess_and_ocr.py --image_path "%INPUT_IMAGE%" --output_dir "%PIPELINE_OUTPUT_DIR%" --ocr_engine "%OCR_ENGINE%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] PaddleOCR step failed!
    echo Please check PADDLE_PYTHON path in this script: %PADDLE_PYTHON%
    goto :EOF
)

REM Determine expected OCR output JSON path
for %%F in ("%INPUT_IMAGE%") do set FILENAME_NO_EXT=%%~nF
set OCR_JSON_PATH=%PIPELINE_OUTPUT_DIR%\%FILENAME_NO_EXT%.json

if not exist "%OCR_JSON_PATH%" (
    echo.
    echo [ERROR] OCR output file not found: %OCR_JSON_PATH%
    goto :EOF
)
echo [Step 1] Finished. OCR JSON generated at: %OCR_JSON_PATH%

REM ----------------------------------------------------------------------------
REM Step 2: Run BERT-MRC
REM ----------------------------------------------------------------------------
echo.
echo [Step 2/2] Running BERT-MRC Pipeline...
echo ----------------------------------------------------------------------------

set NER_OUTPUT_JSON=%PIPELINE_OUTPUT_DIR%\%FILENAME_NO_EXT%_ner.json

cd /d "%BERT_PROJECT_ROOT%"
"%BERT_PYTHON%" inference\work_ticket_ner_from_ocr_json.py ^
    --ocr_json "%OCR_JSON_PATH%" ^
    --output_json "%NER_OUTPUT_JSON%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] BERT-MRC step failed!
    echo Please check BERT_PYTHON path in this script: %BERT_PYTHON%
    goto :EOF
)

echo.
echo ============================================================================
echo [SUCCESS] Pipeline Finished!
echo Result: %NER_OUTPUT_JSON%
echo ============================================================================
pause
