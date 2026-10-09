
🇬🇧 [English](./README.md) | 🇹🇼 [繁體中文](./README-zh-tw.md)

# 區域通知伺服器範例

此範例示範如何在 FastAPI 專案中整合 Firebase Cloud Messaging（FCM），以向客戶端裝置（如 Android、iOS、Web）傳送推播通知。它包含：

- 如何初始化並使用 Firebase Admin SDK 來發送 FCM 消息。
- 如何在 Redis 中儲存、管理裝置 Token（可依使用者或站點分組）。
- 如何設計 FastAPI 的端點以儲存 Token、刪除 Token、以及發送通知。
- 如何在發送前翻譯通知訊息至多種語言（範例中透過簡易的字典翻譯機制）。

## 目錄

1. [概覽](#概覽)
2. [先決條件](#先決條件)
3. [建立 Firebase 專案](#建立-firebase-專案)
4. [產生服務帳號憑證檔](#產生服務帳號憑證檔)
5. [目錄結構](#目錄結構)
6. [安裝](#安裝)
7. [設定](#設定)
8. [執行範例](#執行範例)
9. [API 使用說明](#api-使用說明)
10. [其他注意事項](#其他注意事項)

## 概覽

此區域通知伺服器用於接收請求並透過 FCM 將推播通知傳送給客戶端裝置。主要功能：

1. 在 Redis 中儲存 FCM 裝置 Token（以使用者 ID 為鍵）。
2. 根據裝置的語言設定，將違規／警告訊息翻譯為對應語系內容。
3. 以語言分組的方式批次發送通知。

當偵測到違規事件（例如「未戴安全帽」「過於靠近機具」等），伺服器可推送自訂化的通知，包含相關的文字內容與選擇性圖片。

## 先決條件

1. **Redis**：此應用程式依賴在 Redis 中儲存裝置 Token。
2. **已有可運作的 FastAPI 應用程式**：請參考本範例倉庫中的 `examples/auth` 示範，以了解身分驗證等基本結構。
3. **Firebase 專案**：必須擁有一個啟用了 Cloud Messaging 的 Firebase 專案。
4. **Python 3.9+**（建議）

## 建立 Firebase 專案

1. 前往 [Firebase Console](https://console.firebase.google.com/)。
2. 建立一個新專案（或使用既有專案）。
3. 建立完成後，至 **專案設定** -> **一般**，確認你的 **專案 ID**（例如 `construction-harzard-detection`）。
4. 在 **Cloud Messaging** 區域，確認已啟用 FCM 功能（預設已啟用）。

## 產生服務帳號憑證檔

1. 在 Firebase 專案頁面，進入 **專案設定** -> **服務帳號**。
2. 在 Firebase Admin SDK 區域中按 **產生新的私密金鑰**。
   - 系統會下載一個 `.json` 憑證檔，內含私鑰、client email 等資訊。
3. **重新命名**或保留此 `.json` 檔案名稱。範例中使用：
   ```
   construction-harzard-detection-firebase-adminsdk-fbsvc-ca9d30aff7.json
   ```
4. 將此檔案放入 `examples/local_notification_server/` 資料夾（或其他安全位置）。
   - 在生產環境中，請勿將此檔案置於公開的 Git 倉庫中，並妥善管理秘密憑證。

## 目錄結構

以下為 `examples/local_notification_server` 內的檔案概覽：

```
examples/local_notification_server/
├── app.py
├── fcm_service.py
├── lang_config.py
├── routers.py
├── schemas.py
├── construction-harzard-detection-firebase-adminsdk-fbsvc-ca9d30aff7.json  (你的 Firebase 憑證檔)
└── README-zh-tw.md                    <- 你正在閱讀的檔案
```

- **`app.py`**
  為主要的 FastAPI 應用程式檔案，使用父層（`examples/auth`）的 `global_lifespan`，並掛載通知相關的路由。

- **`fcm_service.py`**
  負責透過 Firebase Admin SDK 發送推播消息，處理批次發送與錯誤記錄。

- **`lang_config.py`**
  內含多種語言的翻譯字典，以及簡易的 `Translator` 類別，用於將違規訊息對應至正確語系。

- **`routers.py`**
  提供 FastAPI 路由以管理 Token（`/store_token`, `/delete_token`）及發送通知（`/send_fcm_notification`）。

- **`schemas.py`**
  定義 Pydantic 模型，用於請求資料的驗證（例如 `TokenRequest`, `SiteNotifyRequest`）。

- **`construction-harzard-detection-firebase-adminsdk-fbsvc-ca9d30aff7.json`**
  範例中的 Firebase 服務帳號 JSON 檔（實務上請使用你自己的檔案名稱和路徑）。

## 安裝

1. **複製此範例程式碼**（或將 `examples/local_notification_server` 資料夾放進你的專案）。
2. **建立並啟用虛擬環境**（可選但建議）：
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # macOS/Linux
   venv\Scripts\activate     # Windows
   ```
3. **安裝套件依賴**（在父層 `examples/auth` 之餘，還需要此範例的需求）：
   ```bash
   pip install -r requirements.txt
   ```
   （或手動安裝 `firebase-admin` 等必要套件，如果環境中尚未安裝。）

## 設定

1. **Firebase 憑證檔路徑**
   請確保 `fcm_service.py`（或初始化 Firebase 的地方）所使用的路徑與 `.json` 檔案名稱一致，例如：
   ```python
   cred_path = (
       "examples/local_notification_server/"
       "construction-harzard-detection-firebase-adminsdk-fbsvc-ca9d30aff7.json"
   )
   ```
   若你更改檔名或路徑，需同步在程式中更新。

2. **Redis**
   此範例依賴父層 `examples/auth` 中的 Redis 模組（`redis_pool.py` 等）。請在 `.env` 或環境變數中設定好 `REDIS_HOST`, `REDIS_PORT`, 以及（若需要）`REDIS_PASSWORD`。

3. **資料庫**
   同樣地，請在 `.env` 中設定 SQLAlchemy 資料庫連線字串，因為某些端點（例如儲存 Token 時）會查詢使用者是否存在。

## 執行範例

以下指令可用來執行此本地通知伺服器（依照 `app.py` 範例）：

```bash
python examples/local_notification_server/app.py
```

若你的專案在根目錄有一個 `main.py` 專門匯入並執行此模組，請依實際情況調整。預設會監聽 `127.0.0.1:8003`。

可使用 [HTTPie](https://httpie.io/) 或 cURL 測試其功能。

## API 使用說明

主要路由定義於 `routers.py`：

### 1. 儲存 FCM Token
```
POST /store_token
```
**Body**（`TokenRequest`）：
```json
{
  "user_id": 1,
  "device_token": "AAAA-VVVV-1234-XYZ",
  "device_lang": "en-GB"
}
```
- 會在 Redis 的 `fcm_tokens:{user_id}` 哈希表中，寫入以 device token 為欄位、語言碼為值的記錄。

### 2. 刪除 FCM Token
```
DELETE /delete_token
```
**Body**（`TokenRequest`）：
```json
{
  "user_id": 1,
  "device_token": "AAAA-VVVV-1234-XYZ"
}
```
- 會在對應使用者的 Redis 哈希表中，刪除該 Token 欄位。

### 3. 發送 FCM 通知
```
POST /send_fcm_notification
```
**Body**（`SiteNotifyRequest`）：
```json
{
  "site": "siteA",
  "stream_name": "Camera-01",
  "body": {
    "warning_no_hardhat": {"count": 2},
    "warning_close_to_machinery": {"count": 1}
  },
  "image_path": "https://example.com/image.jpg",
  "violation_id": 123
}
```
- 從資料庫中查詢對應站點，取得其關聯使用者，並在 Redis 中收集所有 Token。
- 依語言分組 Token，使用 `Translator.translate_from_dict()` 翻譯告警訊息。
- 針對不同語言分別呼叫 FCM Service 發送推播通知（可包含文字、圖片、violation_id 等附加資訊）。
- 回傳 JSON，指示是否發送成功。

## 其他注意事項

1. **裝置 Token**
   - Android 客戶端可透過 Firebase SDK 取得 FCM Token。
   - iOS 端需先啟用推播功能，並從 APNs 取得 Token，再由 Firebase SDK 轉換成 FCM Token。

2. **安全性**
   - 在生產環境中，建議對相關端點（例如 `/store_token`）進行保護。此範例依賴父層的 JWT 驗證（透過 `jwt_access`）來保護 `/send_fcm_notification`。
   - 可考慮增加速率限制或用戶身份檢查，以防止濫用。

3. **多租戶或依站點**
   - 此範例透過「站點」綁定使用者做分組。若有其他需求（如根據角色或特定使用者群組）可自行調整邏輯。

4. **翻譯（i18n）**
   - `lang_config.py` 中僅使用字典進行簡單翻譯。若需更大規模的多語系支援，可考慮使用更專業的 i18n 函式庫或翻譯管理系統（如 `gettext`、Transifex、Crowdin 等）。

5. **日誌與錯誤處理**
   - `fcm_service.py` 若發送失敗，會透過 `logging.error` 記錄錯誤。在生產環境中，建議實作更完善的錯誤處理與重試機制。
