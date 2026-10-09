# MRC-NER 环境配置指南

## 硬件要求

### 推荐配置

- **GPU**: NVIDIA RTX 3060 / RTX 30 系列
- **显存**: ≥ 6GB
- **内存**: ≥ 16GB
- **硬盘**: ≥ 20GB 可用空间

### 兼容性说明

- ✅ **RTX 30 系列** (3060/3070/3080/3090) - 完美支持
- ⚠️ **RTX 40 系列** (4060/4070/4080/4090) - 需要升级 PyTorch
- ✅ **RTX 20 系列** (2060/2070/2080) - 完美支持

---

## 一、环境安装（RTX 3060）

### 1.1 创建虚拟环境

```powershell
# 使用 conda 创建环境（推荐）
conda create -n mrc_ner python=3.8 -y
conda activate mrc_ner
```

或使用 venv：

```powershell
# 使用 Python 内置 venv
python -m venv mrc_ner_env
.\mrc_ner_env\Scripts\Activate.ps1
```

### 1.2 安装 PyTorch（RTX 3060）

```powershell
# CUDA 10.1 版本（与项目匹配）
pip install torch==1.7.1+cu101 torchvision==0.8.2+cu101 torchaudio==0.7.2 -f https://download.pytorch.org/whl/torch_stable.html
```

**验证安装：**

```powershell
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA Available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
```

预期输出：

```
PyTorch: 1.7.1+cu101
CUDA Available: True
GPU: NVIDIA GeForce RTX 3060
```

### 1.3 安装项目依赖

```powershell
# 进入项目目录
cd f:\project\mrc-for-flat-nested-ner

# 安装依赖
pip install -r requirements.txt
```

### 1.4 修复兼容性问题

```powershell
# 降级 protobuf（解决 tensorboard 兼容性）
pip install protobuf==3.20.0

# 降级 numpy（解决 np.object 弃用警告）
pip install "numpy<1.24"
```

---

## 二、数据准备

### 2.1 下载数据集

**中文 MSRA 数据集：**

- 下载链接: https://drive.google.com/file/d/1bAoSJfT1IBdpbQWSrZPjQPPbAsDGlN2D
- 解压到: `f:\project\mrc-for-flat-nested-ner\datasets\zh_msra`

**数据集结构：**

```
datasets\zh_msra\
├── mrc-ner.train
├── mrc-ner.dev
└── mrc-ner.test
```

### 2.2 下载预训练模型

**中文 BERT 模型（chinese-roberta-wwm-ext）：**

- HuggingFace: https://huggingface.co/hfl/chinese-roberta-wwm-ext
- 下载到: `f:\project\mrc-for-flat-nested-ner\models\chinese-roberta-wwm-ext`

**模型文件：**

```
models\chinese-roberta-wwm-ext\
├── config.json
├── pytorch_model.bin
├── tokenizer_config.json
└── vocab.txt
```

---

## 三、快速启动

### 3.1 标准训练（推荐）

```powershell
# 激活环境
conda activate mrc_ner

# 运行快捷脚本
.\quick_start.ps1
```

### 3.2 优化配置（加速训练）

创建 `quick_start_fast.ps1`:

```powershell
# MRC-NER Fast Training Script
$REPO_PATH = "f:\project\mrc-for-flat-nested-ner"
$DATA_DIR = "$REPO_PATH\datasets\zh_msra"
$BERT_DIR = "$REPO_PATH\models\chinese-roberta-wwm-ext"
$OUTPUT_DIR = "$REPO_PATH\outputs\msra_fast"

# Environment
$env:PYTHONPATH = "$REPO_PATH"
$env:TOKENIZERS_PARALLELISM = "false"
$env:CUDA_VISIBLE_DEVICES = "0"

# Optimized parameters for RTX 3060
python "$REPO_PATH\train\mrc_ner_trainer.py" `
    --gpus=1 `
    --data_dir $DATA_DIR `
    --bert_config_dir $BERT_DIR `
    --max_length 128 `
    --batch_size 16 `
    --precision=16 `
    --progress_bar_refresh_rate 1 `
    --lr 8e-6 `
    --val_check_interval 1.0 `
    --accumulate_grad_batches 1 `
    --default_root_dir $OUTPUT_DIR `
    --mrc_dropout 0.2 `
    --max_epochs 5 `
    --weight_span 0.1 `
    --span_loss_candidates "pred_and_gold" `
    --chinese `
    --workers 4 `
    --classifier_intermediate_hidden_size 1536
```

**性能对比：**

| 配置 | Batch Size | Epochs | Workers | 预计时间  |
| ---- | ---------- | ------ | ------- | --------- |
| 标准 | 4          | 20     | 0       | ~24 小时  |
| 优化 | 16         | 5      | 4       | ~1.5 小时 |

---

## 四、训练参数说明

### 4.1 核心参数

| 参数           | 默认值 | 说明         | 调优建议          |
| -------------- | ------ | ------------ | ----------------- |
| `--gpus`       | 1      | GPU 数量     | RTX 3060 单卡用 1 |
| `--batch_size` | 4      | 批次大小     | 6GB 显存用 8-16   |
| `--max_length` | 128    | 最大序列长度 | 不建议修改        |
| `--lr`         | 8e-6   | 学习率       | BERT 微调推荐     |
| `--max_epochs` | 20     | 训练轮数     | 快速测试用 3-5    |
| `--precision`  | 16     | 混合精度     | FP16 节省显存     |
| `--workers`    | 0      | 数据加载线程 | 改为 4 加速       |

### 4.2 显存优化

**如果显存不足，依次尝试：**

1. 减小 batch_size: `16 → 8 → 4`
2. 减小 max_length: `128 → 100`
3. 关闭混合精度: `--precision=32`
4. 启用梯度累积: `--accumulate_grad_batches 2`

---

## 五、模型评估

### 5.1 找到最佳模型

训练完成后，查看日志找到最佳 checkpoint：

```powershell
# 查看训练日志
cat outputs\msra_train\train_log.txt
```

### 5.2 评估模型

```powershell
python evaluate\mrc_ner_evaluate.py `
    "outputs\msra_train\best_model.ckpt" `
    "outputs\msra_train\lightning_logs\version_0\hparams.yaml"
```

---

## 六、模型推理

### 6.1 Flat NER 推理

```powershell
python inference\mrc_ner_inference.py `
    --data_dir datasets\zh_msra `
    --bert_dir models\chinese-roberta-wwm-ext `
    --max_length 128 `
    --model_ckpt "outputs\msra_train\best_model.ckpt" `
    --hparams_file "outputs\msra_train\lightning_logs\version_0\hparams.yaml" `
    --flat_ner `
    --dataset_sign "msra"
```

---

## 七、常见问题

### 7.1 显卡不兼容警告

**问题：** `CUDA capability sm_XX is not compatible`

**解决方案：**

- RTX 30 系列：使用 PyTorch 1.7.1+cu101（推荐）
- RTX 40 系列：升级到 PyTorch 1.13+ with CUDA 11.7+

```powershell
# RTX 40系列升级方案
pip install torch==1.13.1 torchvision==0.14.1 --index-url https://download.pytorch.org/whl/cu117
pip install transformers==4.18.0
```

### 7.2 protobuf 错误

**错误：** `Descriptors cannot be created directly`

**解决：**

```powershell
pip install protobuf==3.20.0
```

### 7.3 numpy 属性错误

**错误：** `module 'numpy' has no attribute 'object'`

**解决：**

```powershell
pip install "numpy<1.24"
```

### 7.4 训练速度慢

**优化措施：**

1. 增大 batch_size: `4 → 16`
2. 启用多线程: `--workers 4`
3. 减少验证频率: `--val_check_interval 1.0`
4. 减少训练轮数: `--max_epochs 5`

### 7.5 显存不足 (OOM)

**解决方案：**

```powershell
# 方案1：减小batch size
--batch_size 8

# 方案2：梯度累积（模拟大batch）
--batch_size 4 --accumulate_grad_batches 4

# 方案3：关闭混合精度
--precision=32
```

---

## 八、完整环境检查清单

### 安装验证脚本

创建 `check_env.ps1`:

```powershell
Write-Host "=== MRC-NER Environment Check ===" -ForegroundColor Cyan
Write-Host ""

# Check Python
Write-Host "[1/6] Python Version:" -ForegroundColor Green
python --version

# Check PyTorch
Write-Host "`n[2/6] PyTorch & CUDA:" -ForegroundColor Green
python -c "import torch; print(f'  PyTorch: {torch.__version__}'); print(f'  CUDA: {torch.cuda.is_available()}'); print(f'  GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"

# Check Dependencies
Write-Host "`n[3/6] Key Packages:" -ForegroundColor Green
python -c "import pytorch_lightning; print(f'  pytorch-lightning: {pytorch_lightning.__version__}')"
python -c "import transformers; print(f'  transformers: {transformers.__version__}')"
python -c "import tokenizers; print(f'  tokenizers: {tokenizers.__version__}')"

# Check Paths
Write-Host "`n[4/6] Data Directory:" -ForegroundColor Green
if (Test-Path "datasets\zh_msra") {
    Write-Host "  ✓ datasets\zh_msra exists" -ForegroundColor Green
} else {
    Write-Host "  ✗ datasets\zh_msra NOT found" -ForegroundColor Red
}

Write-Host "`n[5/6] Model Directory:" -ForegroundColor Green
if (Test-Path "models\chinese-roberta-wwm-ext") {
    Write-Host "  ✓ models\chinese-roberta-wwm-ext exists" -ForegroundColor Green
} else {
    Write-Host "  ✗ models\chinese-roberta-wwm-ext NOT found" -ForegroundColor Red
}

# Check GPU Memory
Write-Host "`n[6/6] GPU Memory:" -ForegroundColor Green
python -c "import torch; print(f'  Total: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB') if torch.cuda.is_available() else print('  No GPU')"

Write-Host "`n=== Check Complete ===" -ForegroundColor Cyan
```

运行检查：

```powershell
.\check_env.ps1
```

---

## 九、项目结构

```
mrc-for-flat-nested-ner/
├── datasets/              # 数据集目录
│   └── zh_msra/          # MSRA中文数据
├── models/               # 预训练模型
│   └── chinese-roberta-wwm-ext/
├── outputs/              # 训练输出（自动创建）
│   └── msra_train/
├── train/                # 训练脚本
│   └── mrc_ner_trainer.py
├── evaluate/             # 评估脚本
│   └── mrc_ner_evaluate.py
├── inference/            # 推理脚本
│   └── mrc_ner_inference.py
├── quick_start.ps1       # 快捷启动脚本
├── check_env.ps1         # 环境检查脚本
└── requirements.txt      # 依赖清单
```

---

## 十、参考资源

- **论文**: [A Unified MRC Framework for Named Entity Recognition (ACL 2020)](https://arxiv.org/abs/1910.11476)
- **PyTorch**: https://pytorch.org/
- **Transformers**: https://huggingface.co/docs/transformers
- **PyTorch Lightning**: https://lightning.ai/docs/pytorch/

---

## 技术支持

遇到问题请提供：

1. 错误信息截图
2. 环境检查结果（运行 `check_env.ps1`）
3. GPU 型号和驱动版本
4. 使用的训练参数

---

**最后更新**: 2026-01-12
**适用显卡**: NVIDIA RTX 3060 / RTX 30 系列
