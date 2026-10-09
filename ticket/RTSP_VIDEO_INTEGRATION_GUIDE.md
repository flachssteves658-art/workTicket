# 工作票项目接入实时视频识别

本地项目关系：

- `ticket`：解析工作票，并将票号、站点、作业时间和检测开关同步到识别项目。
- `Construction-Hazard-Detection`：保存 RTSP 流配置、读取实时视频、执行 YOLO 检测并展示结果。

## 1. 首次准备

在 PowerShell 中启动 Docker Desktop，然后执行：

```powershell
docker start my-mysql my-redis
```

如果 Docker Desktop 中两个容器已经显示绿色运行状态，可跳过这条命令。当前本机端口映射应为 MySQL `13306:3306`、Redis `16379:6379`。

两个项目的环境变量 `INTEGRATION_TOKEN` 与 `HAZARD_INTEGRATION_TOKEN` 必须一致。本地目录并排部署时，`ticket` 会在自己的 `.env` 没有设置令牌时读取识别项目 `.env` 中的 `INTEGRATION_TOKEN`。

## 2. 启动识别项目

打开 PowerShell：

```powershell
conda activate construction-hazard
Set-Location 'D:\工作票项目文件\项目demo\项目demo\Construction-Hazard-Detection'
.\start_services.bat
```

再打开一个 PowerShell，启动实时识别主程序：

```powershell
conda activate construction-hazard
Set-Location 'D:\工作票项目文件\项目demo\项目demo\Construction-Hazard-Detection'
python main.py --poll 10
```

再打开一个 PowerShell，启动管理前端：

```powershell
conda activate construction-hazard
Set-Location 'D:\工作票项目文件\项目demo\项目demo\Construction-Hazard-Detection'
.\start_frontend.bat
```

## 3. 在识别项目中登记摄像头

1. 打开 `http://localhost:8888`，使用本地账号登录。
2. 在 `Sites` 中创建或确认站点，例如“未来一路变电站”。
3. 在 `Config` 中选择该站点并新增配置。
4. `Video URL` 填摄像头 RTSP 地址。
5. `Stream Name` 填一个唯一名称，例如 `camera-001`。
6. 模型先选择 `yolo11n`，勾选安全帽/反光衣和限制区域检测。
7. 建议启用 `Store in Redis`，保存配置后等待主程序下一次轮询。
8. 在 `Camera` 页面选择站点和摄像头，检查实时识别画面。

不要把包含账号密码的 RTSP 地址提交到 Git 或文档。

## 4. 启动工作票页面

```powershell
conda activate ticket-service
Set-Location 'D:\工作票项目文件\项目demo\项目demo\ticket'
python -m pip install -r .\requirements_service.txt
.\service\run_web_ui.bat
```

打开 `http://127.0.0.1:7861`：

1. 上传工作票图片。
2. 勾选“将工作票同步到实时视频识别项目”。
3. “视频识别站点名称”填写与识别项目前端 `Sites` 完全相同的名称。
4. 点击“开始解析”。
5. 在“视频识别同步”页签看到 `同步成功`，并显示被更新的流配置 ID。

同步成功后，识别项目会把工作票号、作业起止时间以及检测项目应用到该站点已有摄像头。实时画面和违规结果仍在识别项目前端查看。

## 5. 常见错误

- `Connection refused`：端口 8005 的 DB 管理 API 没有启动。
- `Invalid integration token`：两个项目的集成令牌不一致。
- `Site not found`：工作票页面填写的站点名称与 `Sites` 中名称不一致。
- `updated_stream_config_ids` 为空：站点存在，但还没有添加摄像头流配置。
- 有画面但不检测：确认 `python main.py --poll 10` 正在运行，作业时间窗有效，模型服务 8000 正常。
- 页面看不到实时帧：确认 8800 服务正常且流配置开启了 Redis 存储。
