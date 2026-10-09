
🇬🇧 [English](./README.md) | 🇹🇼 [繁體中文](./README-zh-tw.md)

# 工地危害偵測 MCP 伺服器

一個完整的 Model Context Protocol（MCP）伺服器實作，為 AI 代理（Agent）提供工地安全監測與危害偵測的工具集合。

## 功能特色

### 🔍 物件偵測與追蹤
- `inference.detect_frame`：基於 YOLO 的物件偵測，支援可調整的信心閾值
- 即時物件追蹤能力
- 支援多種影像格式（base64、檔案路徑）

### ⚠️ 安全違規分析
- `hazard.detect_violations`：智慧化安全違規偵測
- 工作時段過濾與工地場域設定
- 以多邊形定義安全區域進行空間分析
- 可自訂違規規則與閾值

### 📊 違規紀錄管理
- `violations.search`：進階違規紀錄查詢與篩選
- `violations.get`：以 ID 取得特定違規詳細資料
- `violations.get_image`：以多種格式存取違規影像
- `violations.my_sites`：取得使用者可存取之工地清單

### 📱 多平台通知
- `notify.line_push`：整合 LINE Messaging API
- `notify.telegram_send`：支援 Telegram Bot API
- `notify.broadcast_send`：自訂對外廣播通知
- 所有平台皆支援影像附件

### 💾 資料持久化
- `record.send_violation`：上傳違規紀錄與相關中繼資料
- `record.batch_send_violations`：批次處理違規紀錄
- `record.sync_pending`：同步離線快取的待上傳紀錄
- `record.get_statistics`：監控上傳佇列與統計資料

### 🎥 直播串流
- `streaming.start_detection`：持續監控影像串流
- `streaming.stop_detection`：管理串流生命週期
- `streaming.capture_frame`：擷取單張影格
- `streaming.get_status`：查詢串流狀態

### 🤖 模型管理
- `model.fetch`：下載並快取機器學習模型
- `model.update`：更新模型至最新版本
- `model.list_available`：瀏覽可用模型清單
- `model.get_local`：管理本地快取模型

### 🔧 實用工具
- `utils.calculate_polygon_area`：幾何面積計算
- `utils.point_in_polygon`：平面幾何內外測試
- `utils.bbox_intersection`：框選區域運算
- `utils.validate_detections`：偵測資料驗證

## 安裝

### 方式一：於既有專案中使用（建議）

若您在 Construction-Hazard-Detection 專案中運行 MCP 伺服器：

```bash
# 先安裝主專案相依套件
pip install -r requirements.txt

# 再安裝 MCP 特定套件
pip install -r mcp_server/requirements.txt
```

### 方式二：獨立安裝

若僅需獨立部署 MCP 伺服器：

```bash
cd mcp_server/
# 先取消 requirements.txt 內條件式相依的註解
pip install -r requirements.txt
```

### 相依套件說明

MCP 伺服器設計上會重用主專案的套件，以避免衝突：
- 共同相依：FastAPI、Pydantic、NumPy、Pillow、python-dotenv、Redis 等
- MCP 專屬：FastMCP、httpx、jsonschema、structlog

## 設定

伺服器支援多種傳輸模式，透過環境變數設定，預設為 streamable-http：

```bash
# 傳輸設定
MCP_TRANSPORT=streamable-http  # 預設："streamable-http"；可選："stdio"、"sse"、"streamable-http"
MCP_HOST=0.0.0.0              # 適用於 HTTP 型傳輸的 Host
MCP_PORT=8000                 # 適用於 HTTP 型傳輸的 Port

# API 端點
VIOLATION_RECORD_API_URL=http://localhost:3000/api
VIOLATION_RECORDS_USERNAME=your_username
VIOLATION_RECORDS_PASSWORD=your_password

# 通知服務
LINE_CHANNEL_ACCESS_TOKEN=your_line_token
TELEGRAM_BOT_TOKEN=your_telegram_token
BROADCAST_URL=http://localhost:8080/broadcast

# 逾時
# 對外 HTTP 呼叫之單一請求逾時（秒）
API_REQUEST_TIMEOUT=30
```

## 使用方式

### 以 MCP 伺服器執行

```bash
# 預設：使用 streamable-http（適合網頁整合）
python -m mcp_server

# 使用 stdio 傳輸（適合直接接入 MCP 客戶端）
MCP_TRANSPORT=stdio python -m mcp_server

# 使用 SSE 傳輸（Server-Sent Events）
MCP_TRANSPORT=sse python -m mcp_server

# 伺服器存取（適用於 HTTP 型傳輸）
# HTTP: http://localhost:8000/mcp
# SSE: http://localhost:8000/sse
```

### 工具使用範例

```python
# 偵測工地影像中的物件
result = await inference_detect_frame(
	image_base64="data:image/jpeg;base64,/9j/4AAQ...",
	confidence_threshold=0.6,
	track_objects=True,
)

# 進行安全違規分析
violations = await hazard_detect_violations(
	detections=result["detections"],
	image_width=1920,
	image_height=1080,
	working_hour_only=True,
)

# 發送違規通知
if violations["violations_detected"]:
	await notify_line_push(
		recipient_id="user123",
		message=violations["warning_message"],
		image_base64="data:image/jpeg;base64,/9j/4AAQ...",
	)

	# 紀錄違規
	await record_send_violation(
		image_base64="data:image/jpeg;base64,/9j/4AAQ...",
		detections=result["detections"],
		warning_message=violations["warning_message"],
		site_id="construction_site_001",
	)
```

## 系統架構

本 MCP 伺服器以 FastMCP 框架建構，採用模組化架構：

```
mcp_server/
├── __init__.py          # 套件初始化
├── server.py            # MCP 伺服器與工具註冊
├── config.py            # 設定管理
├── schemas.py           # JSON Schema 驗證
└── tools/               # 工具實作
	├── inference.py     # 物件偵測工具
	├── hazard.py        # 安全違規分析
	├── violations.py    # 違規紀錄管理
	├── notify.py        # 多平台通知
	├── record.py        # 資料持久化
	├── streaming.py     # 串流處理
	├── model.py         # 模型管理
	└── utils.py         # 通用工具
```

## 系統整合

此 MCP 伺服器包裝並整合既有的 Construction-Hazard-Detection 核心模組：

- `src/live_stream_detection.py` → 推論工具（inference）
- `src/danger_detector.py` → 違規分析（hazard）
- `src/violation_sender.py` → 紀錄管理（record）
- `src/notifiers/` → 通知工具（notify）
- `src/model_fetcher.py` → 模型管理（model）
- `src/utils.py` → 實用工具（utils）

## 開發

### 新增工具流程

1. 在對應的 `tools/` 模組中建立工具類別
2. 於 `schemas.py` 新增對應的 JSON Schema
3. 在 `server.py` 註冊工具函式
4. 更新文件與使用範例

### 測試

```bash
# 執行全部測試
pytest tests/

# 測試特定工具
pytest tests/test_inference.py -v
```

## 授權條款

本專案的授權條款與上游的 Construction-Hazard-Detection 儲存庫相同。
