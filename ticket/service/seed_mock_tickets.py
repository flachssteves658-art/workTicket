import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add service directory to path
_SERVICE_DIR = Path(__file__).resolve().parent
if str(_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICE_DIR))

import config

def generate_mock_tickets():
    """
    生成模拟的“OCR识别结果”JSON文件。
    这些文件通过精心构造，能够精准命中 seed_infrastructure.py 创建的虚拟设备。
    """
    print("正在生成模拟工作票数据 (Mock OCR Results)...")
    
    output_dir = Path(config.OUTPUT_DIR)
    output_dir.mkdir(exist_ok=True)

    # 基础模板：模拟 PaddleOCR + NER 的输出格式
    # 注意：我们这里直接模拟最终传入 unified_pipeline 的中间格式，或者直接模拟 unified_pipeline 的输出结果
    # 为了方便测试 pipeline，我们模拟 "OCR Output JSON" (input for NER)
    
    # 场景 1：主变检修票 (完美匹配 #2主变)
    # 这张票应该能关联到 #2主变区域 的摄像头
    ticket_1 = {
        "filename": "mock_ticket_001",
        "content": {
            "parsing_res_list": [
                {"block_label": "doc_title", "block_content": "变电站第一种工作票"},
                {"block_label": "text", "block_content": "工作票编号: 20260115001"},
                {"block_label": "text", "block_content": "工作负责人: 张三"},
                {"block_label": "text", "block_content": "工作许可人: 许可员"},
                {"block_label": "text", "block_content": "工作票签发人: 签发员"},
                {"block_label": "text", "block_content": "现场监护人: 监护员"},
                {"block_label": "text", "block_content": "工作班成员: 李四, 王五"},
                {"block_label": "text", "block_content": "工作地点: #2主变区域"}, # 精准命中 Location
                {"block_label": "text", "block_content": "工作内容: #2主变A相套管 油位检查与更换"}, # 精准命中 Device
                {"block_label": "text", "block_content": "计划工作时间: 自 2026年01月15日09时00分 至 2026年01月15日17时00分"},
                {"block_label": "text", "block_content": "安全措施: 拉开#2主变三侧开关；验电确认无电压；装设接地线；设置围栏并悬挂标示牌"},
                {"block_label": "text", "block_content": "工作票状态: 已许可"},
            ]
        }
    }

    # 场景 2：开关室作业 (完美匹配 10kV开关室)
    # 这张票应该能关联到 开关室 的摄像头
    ticket_2 = {
        "filename": "mock_ticket_002",
        "content": {
            "parsing_res_list": [
                {"block_label": "doc_title", "block_content": "变电站第二种工作票"},
                {"block_label": "text", "block_content": "工作票编号: 20260115002"},
                {"block_label": "text", "block_content": "工作负责人: 赵六"},
                {"block_label": "text", "block_content": "工作许可人: 许可员"},
                {"block_label": "text", "block_content": "工作票签发人: 签发员"},
                {"block_label": "text", "block_content": "现场监护人: 监护员"},
                {"block_label": "text", "block_content": "工作地点: 10kV开关室"}, # 精准命中 Location
                {"block_label": "text", "block_content": "工作内容: 10kV #1开关柜 保护装置调试"}, # 精准命中 Device
                {"block_label": "text", "block_content": "计划工作时间: 自 2026年01月16日10时00分 至 2026年01月16日12时00分"},
                {"block_label": "text", "block_content": "安全措施: 核对设备名称编号；悬挂标示牌；监护人全程在场；作业区隔离"},
                {"block_label": "text", "block_content": "工作票状态: 未许可"},
            ]
        }
    }

    mock_tickets = [ticket_1, ticket_2]

    for t in mock_tickets:
        # 保存为 .json 文件，模拟 run_ocr.py 的输出
        fname = t["filename"] + ".json"
        fpath = output_dir / fname
        
        # 还要创建一个空的伪造图片文件，因为 pipeline 检查文件是否存在
        # 我们创建一个 .txt 假装是图片，pipeline 里我们通过逻辑绕过图片读取
        # 或者我们直接调用 unified_pipeline 时，指定这只是 mock
        # 但为了复用现有代码，我们创建一个空文件
        img_path = output_dir / (t["filename"] + ".jpg")
        if not img_path.exists():
            with open(img_path, 'w') as f:
                f.write("mock image")
        
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(t["content"], f, ensure_ascii=False, indent=2)
            
        print(f"✅ 生成模拟 OCR 数据: {fpath}")
        print(f"   (对应虚拟图片路径: {img_path})")

    print("\n下一步提示：")
    print("请修改 unified_pipeline.py 或直接运行 pipeline，")
    print("将这些 JSON 文件作为输入，即可在图谱中生成与基础设施关联的工作票节点。")

if __name__ == "__main__":
    generate_mock_tickets()
