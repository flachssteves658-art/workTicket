
🇬🇧 [English](./README.md) | 🇹🇼 [繁體中文](./README-zh-tw.md)

# 身分驗證與授權範例

此目錄包含一個使用 FastAPI、Redis、SQLAlchemy（非同步引擎）以及 JSON Web Tokens (JWT) 來進行使用者身分驗證與授權的範例。它示範了以下內容：

- 如何在 FastAPI 中整合非同步的 SQLAlchemy 資料庫設定。
- 如何使用 Redis 來實作類似 Session 的快取（儲存 JWT 的 jti 清單與 refresh token）。
- 如何在受保護的端點中使用 FastAPI JWT Bearer tokens。
- 如何進行使用者操作管理（例如：新增、刪除、更新使用者名稱／密碼、啟用／停用使用者）。
- 如何透過 APScheduler 實作定期自動更新 JWT secret key。

此範例主要用於示範與學習，請根據實際生產環境需求進行調整。

## 目錄

1. [專案結構](#專案結構)
2. [需求](#需求)
3. [安裝](#安裝)
4. [環境變數](#環境變數)
5. [執行範例](#執行範例)
6. [JWT Secret Key 自動更新](#jwt-secret-key-自動更新)
7. [速率限制](#速率限制)
8. [身分驗證與使用者管理 API](#身分驗證與使用者管理-api)
   - [身分驗證端點](#身分驗證端點)
   - [使用者管理端點](#使用者管理端點)
9. [程式碼解說](#程式碼解說)

## 專案結構

```
examples/auth/
├── __init__.py
├── auth.py
├── cache.py
├── config.py
├── database.py
├── jwt_config.py
├── jwt_scheduler.py
├── lifespan.py
├── models.py
├── redis_pool.py
├── routers.py
├── security.py
├── user_operation.py
├── README-zh-tw.md             <- 你正在閱讀的檔案
```

**主要檔案概要**：

- **`auth.py`**
  定義了核心的身分驗證邏輯，包括建立 access/refresh token 與驗證 refresh token。

- **`cache.py`**
  提供在 Redis 中儲存與讀取使用者資料（包含 jti 清單和 refresh token）的輔助函式。

- **`config.py`**
  內含一個 `Settings` 類別，用來讀取 JWT secret key 與資料庫設定等環境變數。

- **`database.py`**
  建立非同步的 SQLAlchemy 引擎與 Session，並提供一個基底宣告模型類別。

- **`jwt_config.py`**
  使用 `fastapi_jwt.JwtAccessBearer` 建立 `jwt_access` 與 `jwt_refresh` 實例。

- **`jwt_scheduler.py`**
  利用 APScheduler 排程，設置每 30 天更新一次 JWT secret key 的工作。

- **`lifespan.py`**
  定義一個 `global_lifespan` 上下文管理器，用於在 FastAPI 應用程式啟動與關閉時初始化和清理資源（啟動排程、連線 Redis、建立資料表）。

- **`models.py`**
  定義 SQLAlchemy ORM 模型（`User`, `Site`, `Violation`），並示範多對多（many-to-many）以及一對多（one-to-many）等關聯關係。

- **`redis_pool.py`**
  提供一個類別，用於建立與管理單一 Redis 連線池，供 HTTP 與 WebSocket 路由使用。

- **`routers.py`**
  包含與身分驗證（登入、登出、刷新 token）及使用者管理（新增、刪除、更新）相關的 FastAPI 路由。

- **`security.py`**
  內含更新 FastAPI 應用程式 JWT secret key 的函式。

- **`user_operation.py`**
  內含使用者 CRUD 操作（新增、刪除、修改使用者名稱／密碼、啟用／停用）的函式。

## 需求

所有必要的 Python 套件都列在 `requirements.txt` 中。主要依賴的套件包含：

- **FastAPI**
- **fastapi-jwt**（用於 JWT 驗證）
- **redis**（非同步用戶端）
- **SQLAlchemy**（非同步的資料庫操作）
- **asyncmy**（非同步的 MySQL 驅動程式，或可依需求替換成其他 RDBMS）
- **werkzeug**（用於密碼雜湊）
- **apscheduler**（用於排程工作）
- **python-dotenv**（用於讀取環境變數）

## 安裝

1. **複製此範例程式庫**（或將 `examples/auth` 資料夾放置於你的專案中）。

2. **建立虛擬環境**（建議但非必須）：
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # macOS/Linux
   venv\Scripts\activate     # Windows
   ```

3. **從 `requirements.txt` 安裝套件**：
   ```bash
   pip install -r requirements.txt
   ```

4. **設定 `.env`** 檔案（參考[環境變數](#環境變數)章節）。

## 環境變數

在 `examples/auth` 資料夾（或你的專案根目錄）建立 `.env` 檔案，內容範例如下（可自行調整）：

```bash
# JWT secret key
JWT_SECRET_KEY="your_super_secret_key"

# SQLAlchemy 資料庫連線 URI
# 例如 MySQL: mysql+asyncmy://<user>:<password>@<host>/<database_name>
DATABASE_URL="mysql+asyncmy://user:password@localhost/dbname"

# Redis 連線資訊
REDIS_HOST="127.0.0.1"
REDIS_PORT="6379"
REDIS_PASSWORD=""
```

這些變數會在程式執行時由 `config.py` 透過 `pydantic_settings.BaseSettings` 讀取。你也可以透過系統環境變數來提供設定，不一定要使用 `.env`。

## 執行範例

以下範例的 `main.py` 用於將所有元件整合起來：

```python
# main.py
from fastapi import FastAPI
from examples.auth.lifespan import global_lifespan
from examples.auth.routers import auth_router, user_management_router

app = FastAPI(lifespan=global_lifespan)

# 掛載路由
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])
app.include_router(user_management_router, prefix="/users", tags=["User Management"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
```

1. **啟動程式**：
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. **確認** 啟動程序後會自動在資料庫中建立所需的資料表（在 `lifespan.py` 的 startup 邏輯中）。
3. **存取 API 文件**： <http://127.0.0.1:8000/docs> 或 <http://127.0.0.1:8000/redoc>。

## JWT Secret Key 自動更新

此範例透過 APScheduler 每 30 天自動更新一次 JWT secret key，相關程式碼在 `jwt_scheduler.py` 與 `security.py`。

- **排程啟動**：在 `lifespan.py` 中，呼叫 `start_jwt_scheduler(app)` 以啟動背景工作進行密鑰更新。
- **金鑰更新**：`update_secret_key(app)` 會產生新的金鑰，並儲存在 `app.state.jwt_secret_key` 中。

> **注意**：此機制僅供範例示範。若在生產環境頻繁更新 secret key，會導致所有既存的 token 失效。建議在實務上搭配更嚴謹的金鑰管理策略。

## 速率限制

在 `cache.py` 中定義一個自訂速率限制器（`custom_rate_limiter`），它會根據使用者角色（role）來判定速率限制：

- `guest` 角色：
  - **最大請求數**：24 次
  - **限制時窗**：24 小時

- 其他角色：
  - **最大請求數**：3000 次
  - **限制時窗**：1 分鐘

若超過此速率，將回傳 HTTP `429 (Too Many Requests)`。

## 身分驗證與使用者管理 API

### 身分驗證端點

#### `POST /auth/login`
- **Body**: `{"username": "your_username", "password": "your_password"}`
- **回應**:
  ```json
  {
    "access_token": "<JWT_ACCESS_TOKEN>",
    "refresh_token": "<JWT_REFRESH_TOKEN>",
    "role": "<user_role>",
    "username": "<username>",
    "user_id": <user_id>
  }
  ```
  成功登入後會同時回傳短期有效的 `access_token` 與長期有效的 `refresh_token`。

#### `POST /auth/logout`
- **Body**: `{"refresh_token": "<JWT_REFRESH_TOKEN>"}`
- **Headers**: `Authorization: Bearer <JWT_ACCESS_TOKEN>`
- **行為**:
  - 從 Redis 移除指定的 refresh token。
  - 從 Redis 清除與 access token 對應的 `jti`。
  - 即使 access token 已失效或過期，也會進行本地端的登出流程。

#### `POST /auth/refresh`
- **Body**: `{"refresh_token": "<JWT_REFRESH_TOKEN>"}`
- **回應**:
  ```json
  {
    "access_token": "<NEW_JWT_ACCESS_TOKEN>",
    "refresh_token": "<NEW_JWT_REFRESH_TOKEN>",
    "message": "Token refreshed successfully."
  }
  ```
  - 驗證提供的 refresh token。
  - 若有效，產生新的 access token 與 refresh token。

### 使用者管理端點

以下所有端點都 **需要** 有效的 `Bearer` token，且該 token 的角色必須為 `admin`。

#### `POST /users/add_user`
- **Body**:
  ```json
  {
    "username": "new_username",
    "password": "new_password",
    "role": "user"
  }
  ```
- **用途**：建立新的使用者紀錄。可指定角色為 `admin`、`model_manager`、`user` 或 `guest`。

#### `POST /users/delete_user`
- **Body**:
  ```json
  {
    "username": "username_to_delete"
  }
  ```
- **用途**：刪除指定的使用者。

#### `PUT /users/update_username`
- **Body**:
  ```json
  {
    "old_username": "old_name",
    "new_username": "new_name"
  }
  ```
- **用途**：更新使用者的帳號名稱。

#### `PUT /users/update_password`
- **Body**:
  ```json
  {
    "username": "the_username",
    "new_password": "the_new_password"
  }
  ```
- **用途**：更新指定使用者的密碼（重新雜湊並儲存）。

#### `PUT /users/set_user_active_status`
- **Body**:
  ```json
  {
    "username": "the_username",
    "is_active": true
  }
  ```
- **用途**：啟用或停用指定使用者的帳號。

## 程式碼解說

1. **JWT 邏輯**:
   - 在 `jwt_config.py` 中，透過 `Settings` 取得 secret key，並建立 `JwtAccessBearer` 與 `JwtRefreshBearer`（即 `jwt_access`、`jwt_refresh`）。
   - 在 `auth.py` 的 `create_access_token` 函式中，會檢查使用者登入憑證是否正確，若成功則產生具備唯一 `jti` 的短期 access token（在 Redis 中追蹤），以及長期的 refresh token。

2. **Redis 儲存結構**:
   - Redis 中的使用者資料結構類似：
     ```json
     {
       "db_user": {
         "id": <int>,
         "username": "<str>",
         "role": "<str>",
         "is_active": <bool>
       },
       "jti_list": ["<list_of_jti_strings>"],
       "refresh_tokens": ["<list_of_active_refresh_tokens>"]
     }
     ```
   - `get_user_data` 和 `set_user_data` 函式負責 JSON 序列化與反序列化的細節。

3. **資料庫**:
   - `database.py` 建立非同步的 SQLAlchemy 引擎。
   - `models.py` 介紹如何定義非同步 ORM 模型，包括多對多（`User` <-> `Site`）和一對多（`Site` -> `Violation`）的關聯範例。

4. **使用者操作**:
   - `user_operation.py` 內含所有針對 `User` 模型的 CRUD 操作。

5. **Lifespan 與排程**:
   - `lifespan.py` 中的 `global_lifespan` 會在應用程式啟動時執行 APScheduler 排程以更新 JWT 金鑰，以及初始化 Redis。
   - 同時也負責在資料庫中建立資料表（若尚未存在）。
