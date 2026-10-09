🇬🇧 [English](./src/README.md) | 🇹🇼 [繁體中文](./src/README-zh-tw.md)

## 概述

此存儲庫包含多個 Python 腳本，設計用於各種功能，包括即時串流檢測、繪圖管理、模型下載、日誌記錄，以及通過不同平台發送通知。該專案的結構有助於這些功能的簡易整合和使用。

## 目錄結構

```
src
├── danger_detector.py
├── drawing_manager.py
├── __init__.py
├── lang_config.py
├── live_stream_detection.py
├── live_stream_tracker.py
├── model_fetcher.py
├── monitor_logger.py
├── notifiers
│   ├── broadcast_notifier.py
│   ├── __init__.py
│   ├── line_notifier.py
│   ├── messenger_notifier.py
│   ├── telegram_notifier.py
│   └── wechat_notifier.py
├── stream_capture.py
└── stream_viewer.py
```

## 文件描述

### 主要模組

- **danger_detector.py**：包含 [`DangerDetector`](./src/danger_detector.py) 類別，用於基於檢測數據發現潛在的安全隱患。
- **drawing_manager.py**：包含 [`DrawingManager`](./src/drawing_manager.py) 類別，用於在影像上繪製檢測結果並保存它們。
- **lang_config.py**：語言設置的配置文件。
- **live_stream_detection.py**：包含 [`LiveStreamDetector`](./src/live_stream_detection.py) 類別，用於使用 YOLOv8 和 SAHI 進行即時串流檢測和追蹤。
- **live_stream_tracker.py**：包含 [`LiveStreamDetector`](./src/live_stream_tracker.py) 類別，用於使用 YOLOv8 進行即時串流檢測和追蹤。
- **model_fetcher.py**：包含下載模型文件的函數（如果模型文件尚未存在）。
- **monitor_logger.py**：包含 [`LoggerConfig`](./src/monitor_logger.py) 類別，用於設置應用日誌記錄，支援控制台和文件輸出。
- **stream_capture.py**：包含 [`StreamCapture`](./src/stream_capture.py) 類別，用於從視頻串流中捕獲影像。
- **stream_viewer.py**：包含 [`StreamViewer`](./src/stream_viewer.py) 類別，用於觀看視頻串流。

### 通知模組

- **notifiers/broadcast_notifier.py**：包含 [`BroadcastNotifier`](./src/notifiers/broadcast_notifier.py) 類別，用於向廣播系統發送訊息。
- **notifiers/line_notifier.py**：包含 [`LineNotifier`](./src/notifiers/line_notifier.py) 類別，用於通過 LINE Notify 發送通知。
- **notifiers/messenger_notifier.py**：包含 [`MessengerNotifier`](./src/notifiers/messenger_notifier.py) 類別，用於通過 Facebook Messenger 發送通知。
- **notifiers/telegram_notifier.py**：包含 [`TelegramNotifier`](./src/notifiers/telegram_notifier.py) 類別，用於通過 Telegram 發送通知。
- **notifiers/wechat_notifier.py**：包含 [`WeChatNotifier`](./src/notifiers/wechat_notifier.py) 類別，用於通過 WeChat Work 發送通知。

## 使用方式

### 設定環境變數

請確保在專案根目錄中有 `.env` 文件，並包含各通知模組所需的環境變數，例如：

```
WECHAT_CORP_ID=your_wechat_corp_id
WECHAT_CORP_SECRET=your_wechat_corp_secret
WECHAT_AGENT_ID=your_wechat_agent_id
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
FACEBOOK_PAGE_ACCESS_TOKEN=your_facebook_page_access_token
LINE_NOTIFY_TOKEN=your_line_notify_token
```

### 執行腳本

每個腳本可以單獨執行。例如，要執行 `live_stream_tracker.py` 腳本：

```bash
python live_stream_tracker.py --url <your_stream_url> --model <path_to_yolo_model>
```

### 使用範例

請參考每個腳本中的 `main` 函數以了解使用範例。
