Option Explicit

' 基于 PowerPoint COM 的一键生成器
' 双击本文件后，将在同目录生成：
' 电网安全智能管控项目阶段性进展汇报_生成版.pptx

Const ppLayoutBlank = 12
Const ppSaveAsOpenXMLPresentation = 24
Const msoFalse = 0
Const msoTrue = -1
Const msoTextOrientationHorizontal = 1
Const msoShapeRectangle = 1
Const msoShapeRoundedRectangle = 5
Const msoShapeOval = 9
Const msoShapeChevron = 52
Const msoShapeHexagon = 10

Dim ppt, pres, fso, outPath
Set fso = CreateObject("Scripting.FileSystemObject")
outPath = fso.BuildPath(fso.GetParentFolderName(WScript.ScriptFullName), "电网安全智能管控项目阶段性进展汇报_生成版.pptx")

On Error Resume Next
Set ppt = CreateObject("PowerPoint.Application")
If Err.Number <> 0 Then
  MsgBox "无法启动 Microsoft PowerPoint，请确认已安装桌面版 PowerPoint。" & vbCrLf & Err.Description, 16, "生成失败"
  WScript.Quit 1
End If
On Error GoTo 0

ppt.Visible = True
Set pres = ppt.Presentations.Add
pres.PageSetup.SlideWidth = 960
pres.PageSetup.SlideHeight = 540

AddCover
AddAgenda
AddProblems
AddOverallFlow
AddVideoProcess
AddVideoChallenges
AddViolations
AddFourChecks
AddOcrRoute
AddOcrAdvantages
AddOcrChallenges
AddCameraLink
AddVideoTimeline
AddLinkChallenges
AddEvidenceLoop
AddAgentPosition
AddAgentProcess
AddExplainableAlert
AddAlertLevels
AddAgentFoundation
AddAchievements
AddRoadmap
AddSummary

On Error Resume Next
If fso.FileExists(outPath) Then fso.DeleteFile outPath, True
On Error GoTo 0
pres.SaveAs outPath, ppSaveAsOpenXMLPresentation

MsgBox "PPT 已生成，共 " & pres.Slides.Count & " 页：" & vbCrLf & outPath, 64, "生成完成"

Function C(r, g, b)
  C = r + g * 256 + b * 65536
End Function

Function IIf(conditionValue, trueValue, falseValue)
  If conditionValue Then
    IIf = trueValue
  Else
    IIf = falseValue
  End If
End Function

Sub SetBackground(slide, colorValue)
  slide.FollowMasterBackground = msoFalse
  slide.Background.Fill.Solid
  slide.Background.Fill.ForeColor.RGB = colorValue
End Sub

Function AddShape(slide, shapeType, x, y, w, h, fillColor, lineColor, radius)
  Dim shp
  Set shp = slide.Shapes.AddShape(shapeType, x, y, w, h)
  shp.Fill.Solid
  shp.Fill.ForeColor.RGB = fillColor
  If lineColor < 0 Then
    shp.Line.Visible = msoFalse
  Else
    shp.Line.ForeColor.RGB = lineColor
    shp.Line.Weight = 1
  End If
  Set AddShape = shp
End Function

Function AddText(slide, txt, x, y, w, h, fontSize, colorValue, isBold, alignValue)
  Dim box, tr
  Set box = slide.Shapes.AddTextbox(msoTextOrientationHorizontal, x, y, w, h)
  box.TextFrame.MarginLeft = 4
  box.TextFrame.MarginRight = 4
  box.TextFrame.MarginTop = 2
  box.TextFrame.MarginBottom = 2
  box.TextFrame.WordWrap = msoTrue
  box.TextFrame.TextRange.Text = txt
  Set tr = box.TextFrame.TextRange
  tr.Font.Name = "Microsoft YaHei"
  tr.Font.NameFarEast = "Microsoft YaHei"
  tr.Font.Size = fontSize
  tr.Font.Color.RGB = colorValue
  tr.Font.Bold = isBold
  tr.ParagraphFormat.Alignment = alignValue
  tr.ParagraphFormat.SpaceAfter = 4
  Set AddText = box
End Function

Sub AddHeader(slide, title, sectionName, pageNo)
  Dim band
  Set band = AddShape(slide, msoShapeRectangle, 0, 0, 960, 8, C(0,193,220), -1, 0)
  AddText slide, sectionName, 46, 24, 200, 18, 11, C(0,193,220), True, 1
  AddText slide, title, 42, 50, 850, 44, 25, C(244,248,252), True, 1
  AddText slide, Right("0" & pageNo, 2), 888, 500, 35, 18, 10, C(132,151,174), False, 2
  AddText slide, "电网安全智能管控关键技术研究", 42, 500, 260, 18, 9, C(94,120,148), False, 1
End Sub

Sub AddAccent(slide, x, y, h, colorValue)
  AddShape slide, msoShapeRoundedRectangle, x, y, 5, h, colorValue, -1, 0
End Sub

Sub AddPanel(slide, x, y, w, h, heading, body, accentColor, headingSize, bodySize)
  Dim panel
  Set panel = AddShape(slide, msoShapeRoundedRectangle, x, y, w, h, C(19,45,73), C(43,75,107), 0)
  panel.Fill.Transparency = 0.03
  AddAccent slide, x + 14, y + 16, 28, accentColor
  AddText slide, heading, x + 30, y + 13, w - 44, 32, headingSize, C(244,248,252), True, 1
  AddText slide, body, x + 18, y + 53, w - 36, h - 66, bodySize, C(199,215,230), False, 1
End Sub

Sub AddTag(slide, txt, x, y, w, colorValue)
  AddShape slide, msoShapeRoundedRectangle, x, y, w, 28, colorValue, -1, 0
  AddText slide, txt, x + 3, y + 4, w - 6, 18, 11, C(255,255,255), True, 2
End Sub

Sub AddCover()
  Dim s, i
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(5,22,42)
  AddShape s, msoShapeRectangle, 0, 0, 16, 540, C(0,193,220), -1, 0
  AddShape s, msoShapeOval, 690, 50, 230, 230, C(8,55,86), C(0,193,220), 0
  AddShape s, msoShapeOval, 742, 102, 126, 126, C(5,22,42), C(46,211,183), 0
  For i = 0 To 4
    AddShape s, msoShapeRectangle, 708 + i * 34, 155, 18, 75 - i * 10, C(0,193,220), -1, 0
  Next
  AddText s, "基于多模态数据分析的", 62, 94, 615, 40, 22, C(0,193,220), True, 1
  AddText s, "电网安全智能管控" & vbCrLf & "关键技术研究", 58, 139, 650, 132, 42, C(248,251,255), True, 1
  AddText s, "阶段性进展与智能预警闭环方案汇报", 62, 294, 620, 38, 20, C(185,206,226), False, 1
  AddShape s, msoShapeRectangle, 62, 353, 330, 3, C(46,211,183), -1, 0
  AddText s, "以工作票为业务主线，联动摄像头与视频智能分析", 62, 373, 600, 27, 15, C(143,168,192), False, 1
  AddText s, "实现作业可感知 · 风险可识别 · 违章可预警 · 处置可闭环", 62, 404, 690, 27, 15, C(143,168,192), False, 1
  AddText s, "国网华东分部 / 项目承担单位    2026", 62, 482, 600, 22, 11, C(94,120,148), False, 1
End Sub

Sub AddAgenda()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "本次汇报重点", "OVERVIEW  汇报概览", 2
  heads = Array("问题与难点", "视频违章识别", "工作票智能识别", "票—设备—视频联动", "智能体预警闭环")
  bodies = Array("数据分散、视频量大、票面复杂、算法误报、处置难闭环", "视频如何处理，当前可识别哪些违章，怎样降低误报漏报", "采用什么技术，如何形成可驱动业务的结构化字段", "如何按地点、设备、时间自动找到摄像头及对应视频", "作业前预控、作业中预警、作业后复盘如何落地")
  For i = 0 To 4
    x = 45 + (i Mod 3) * 295
    y = 125 + Int(i / 3) * 174
    AddPanel s, x, y, 270, 144, CStr(i + 1) & "  " & heads(i), bodies(i), IIf(i = 4, C(255,154,61), C(0,193,220)), 15, 12
  Next
  AddPanel s, 635, 299, 270, 144, "核心结论", "本项目不是单独建设OCR工具或视频模型，而是把工作票、设备台账、摄像头、算法、规则与处置流程串成完整业务链。", C(46,211,183), 15, 12
End Sub

Sub AddProblems()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "当前安全管控面临的核心问题", "01  问题与挑战", 3
  heads = Array("数据分散", "人工看不过来", "工作票非结构化", "单一模型易误报", "结果难以闭环")
  bodies = Array("工作票、视频平台、设备台账各自掌握一部分信息，缺少统一关联。", "作业时间长、摄像头数量多，短时违章极易被人工抽查遗漏。", "扫描质量、表格样式、印章遮挡和专业写法都会影响字段提取。", "遮挡、逆光、小目标和多人交叉使单帧视觉判断不稳定。", "若没有关联工作票、证据、责任人与处置状态，告警难以产生管理价值。")
  For i = 0 To 4
    x = 44 + (i Mod 3) * 295
    y = 120 + Int(i / 3) * 174
    AddPanel s, x, y, 272, 145, heads(i), bodies(i), IIf(i = 4, C(255,154,61), C(0,193,220)), 16, 12
  Next
  AddPanel s, 634, 294, 272, 145, "关键矛盾", "“票里知道应该怎么做，视频里看到实际怎么做”，但两者尚未自动对齐。", C(46,211,183), 16, 13
End Sub

Sub AddOverallFlow()
  Dim s, steps, i, x, y, row, col, clr
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "总体解决思路：以工作票驱动作业全过程智能管控", "02  总体方案", 4
  steps = Array("工作票接入", "OCR与版面解析", "字段结构化", "设备地点标准化", "关联摄像头", "按时间取视频", "违章识别", "多模态研判", "分级预警", "处置与学习")
  For i = 0 To 9
    row = Int(i / 5)
    col = i Mod 5
    x = 46 + col * 177
    y = 140 + row * 145
    clr = IIf(i < 5, C(0,142,181), C(15,143,125))
    AddShape s, msoShapeRoundedRectangle, x, y, 145, 70, C(19,45,73), clr, 0
    AddText s, CStr(i + 1), x + 8, y + 8, 25, 22, 12, clr, True, 2
    AddText s, steps(i), x + 33, y + 23, 104, 25, 13, C(244,248,252), True, 2
    If col < 4 Then
      AddText s, "→", x + 146, y + 22, 30, 25, 17, C(94,120,148), True, 2
    End If
  Next
  AddText s, "文本 + 图像视频 + 时空信息 + 业务数据", 250, 418, 460, 33, 17, C(0,193,220), True, 2
  AddText s, "从“人去找视频、看视频”转变为“工作票自动找到相关视频，系统只推送高风险片段与证据”", 116, 458, 730, 30, 14, C(199,215,230), False, 2
End Sub

Sub AddVideoProcess()
  Dim s, steps, notes, i, x
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "违章视频是怎么处理的", "03  视频智能分析", 5
  steps = Array("视频接入", "预处理", "目标检测", "行为判定", "多模态复核", "证据生成")
  notes = Array("实时流 / 历史录像", "抽帧、切片、增强、ROI", "人员与防护用品检测跟踪", "动作、区域、持续时间", "结合工作票时空约束", "关键帧 + 前后视频 + 依据")
  For i = 0 To 5
    x = 42 + i * 151
    AddShape s, msoShapeRoundedRectangle, x, 165, 126, 110, C(19,45,73), IIf(i < 3, C(0,193,220), C(46,211,183)), 0
    AddText s, CStr(i + 1), x + 43, 179, 40, 32, 20, IIf(i < 3, C(0,193,220), C(46,211,183)), True, 2
    AddText s, steps(i), x + 8, 218, 110, 25, 14, C(244,248,252), True, 2
    AddText s, notes(i), x + 8, 287, 110, 57, 10, C(170,191,211), False, 2
    If i < 5 Then AddText s, "›", x + 126, 199, 25, 40, 25, C(94,120,148), True, 2
  Next
  AddPanel s, 90, 377, 780, 72, "判定原则", "发现人员不等于发现违章。只有目标、动作、区域关系、持续时间与工作票约束共同满足时，才形成候选事件。", C(255,154,61), 14, 12
End Sub

Sub AddVideoChallenges()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "违章视频处理遇到的难点及解决办法", "03  视频智能分析", 6
  heads = Array("小目标与遮挡", "光照环境变化", "动作具有时序性", "同一事件重复报警", "样本少且不均衡")
  bodies = Array("高分辨率切片、小目标增强、目标跟踪与多帧投票。", "扩充真实难例，采用图像增强、分场景阈值与画面质量检测。", "结合人体关键点、目标关系、轨迹和持续时间，连续多帧才触发。", "通过人员轨迹ID、事件合并窗口和告警冷却时间进行去重。", "建立脱敏、标注、复核、训练、回归测试和难例回流机制。")
  For i = 0 To 4
    x = 44 + (i Mod 3) * 295
    y = 120 + Int(i / 3) * 174
    AddPanel s, x, y, 272, 145, heads(i), bodies(i), IIf(i = 4, C(255,154,61), C(0,193,220)), 15, 12
  Next
  AddPanel s, 634, 294, 272, 145, "工程策略", "优先提高高风险类别质量；低质量画面提示人工确认，不强行输出确定结论。", C(46,211,183), 15, 12
End Sub

Sub AddViolations()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "项目可识别的违章行为", "03  视频智能分析", 7
  AddPanel s, 46, 125, 415, 310, "当期核心能力（以实测标签为准）", _
    "01  未佩戴或未规范佩戴安全帽" & vbCrLf & _
    "02  未穿规定工作服 / 反光防护服【待确认】" & vbCrLf & _
    "03  高处作业未规范使用安全带【待确认】" & vbCrLf & _
    "04  作业现场吸烟" & vbCrLf & _
    "05  作业过程中使用手机或接打电话" & vbCrLf & _
    "06  进入禁区、越过电子围栏或超出允许区域", C(0,193,220), 16, 13
  AddPanel s, 498, 125, 415, 310, "后续扩展能力", _
    "01  人员倒地、长时间静止" & vbCrLf & _
    "02  明火、烟雾等环境异常" & vbCrLf & _
    "03  登高、攀爬、翻越围栏" & vbCrLf & _
    "04  无监护作业、人数不匹配" & vbCrLf & _
    "05  非工作班成员进入作业区" & vbCrLf & _
    "06  工器具使用不规范、危险距离不足", C(46,211,183), 16, 13
  AddText s, "能力边界：视觉适合识别“摄像头可见、特征明确、可由目标/动作/区域关系表达”的违章；电气状态与操作顺序需融合业务系统和物联数据。", 55, 452, 850, 35, 11, C(255,183,77), False, 2
End Sub

Sub AddFourChecks()
  Dim s, heads, bodies, i, x
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "四层校验：降低误报与漏报", "03  视频智能分析", 8
  heads = Array("视觉置信度", "时序连续性", "空间关系", "业务语义")
  bodies = Array("检测分数、目标尺寸与画面质量达到门槛。", "连续多帧或持续一定时长，过滤瞬时遮挡和抖动。", "人员、设备、围栏和预置位建立空间关系。", "结合工作票时间、地点、人员与安全措施二次判断。")
  For i = 0 To 3
    x = 55 + i * 220
    AddShape s, msoShapeOval, x + 53, 140, 84, 84, C(19,45,73), IIf(i < 2, C(0,193,220), C(46,211,183)), 0
    AddText s, CStr(i + 1), x + 70, 160, 50, 34, 23, IIf(i < 2, C(0,193,220), C(46,211,183)), True, 2
    AddPanel s, x, 245, 190, 150, heads(i), bodies(i), IIf(i < 2, C(0,193,220), C(46,211,183)), 15, 12
  Next
  AddTag s, "高置信度 / 高风险 → 立即预警", 125, 430, 265, C(218,82,76)
  AddTag s, "中等置信度 → 人工复核", 410, 430, 220, C(223,142,44)
  AddTag s, "低置信度 → 留存优化", 650, 430, 190, C(64,123,164)
End Sub

Sub AddOcrRoute()
  Dim s, steps, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "工作票识别采用的技术路线", "04  工作票智能识别", 9
  AddText s, "PaddleOCR + 图像预处理 + 版面/表格解析 + 字段规则 + 专业词典 + 业务一致性校验", 58, 108, 844, 35, 16, C(0,193,220), True, 2
  steps = Array("文档接入", "图像预处理", "文字检测", "文字识别", "版面表格解析", "关键字段抽取", "专业语义校验", "结构化输出")
  For i = 0 To 7
    x = 54 + (i Mod 4) * 220
    y = 168 + Int(i / 4) * 122
    AddShape s, msoShapeRoundedRectangle, x, y, 190, 74, C(19,45,73), IIf(i < 4, C(0,193,220), C(46,211,183)), 0
    AddText s, "0" & CStr(i + 1), x + 12, y + 11, 30, 22, 11, IIf(i < 4, C(0,193,220), C(46,211,183)), True, 1
    AddText s, steps(i), x + 42, y + 25, 137, 25, 14, C(244,248,252), True, 2
  Next
  AddPanel s, 90, 420, 780, 58, "重点字段", "工作票编号、负责人、班组成员、工作内容、站点/线路、工作地点、设备编号、起止时间、安全措施、危险点、许可状态", C(255,154,61), 13, 11
End Sub

Sub AddOcrAdvantages()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "工作票识别的技术优势", "04  工作票智能识别", 10
  heads = Array("中文与复杂票面", "本地化部署", "输出结构化业务字段", "规则可解释可追溯", "专业场景可优化", "准确率与效率兼顾")
  bodies = Array("适配中文、数字、字母与常见复杂背景。", "内网完成识别，减少敏感生产数据外传风险。", "不仅返回全文，还输出地点、设备、时间、人员等字段。", "保留原文、位置、置信度和校验结果，便于复核。", "通过电力词典、设备台账、模板与专项样本持续提升。", "通用OCR识别，规则台账纠错，低置信度人工确认。")
  For i = 0 To 5
    x = 44 + (i Mod 3) * 295
    y = 120 + Int(i / 3) * 174
    AddPanel s, x, y, 272, 145, heads(i), bodies(i), IIf(i < 3, C(0,193,220), C(46,211,183)), 15, 12
  Next
End Sub

Sub AddOcrChallenges()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "工作票识别的难点及解决办法", "04  工作票智能识别", 11
  heads = Array("票面质量不稳定", "模板多、表格复杂", "专业词易混淆", "时间地点必须可靠", "手写签名与印章")
  bodies = Array("自动方向、清晰度检测、旋转矫正与图像增强。", "版面/表格解析与模板配置结合，字段名和空间位置共同定位。", "站点、设备台账与上下文联合校验，多候选时转人工。", "字段置信度、格式逻辑与设备存在性校验；不确定则阻断联动。", "签名印章区域与核心字段分开处理，手写内容专模或人工确认。")
  For i = 0 To 4
    x = 44 + (i Mod 3) * 295
    y = 120 + Int(i / 3) * 174
    AddPanel s, x, y, 272, 145, heads(i), bodies(i), IIf(i = 3, C(255,154,61), C(0,193,220)), 15, 12
  Next
  AddPanel s, 634, 294, 272, 145, "关键控制点", "时间与地点直接决定联动哪台摄像头、调取哪段视频，低置信度时必须人工确认。", C(46,211,183), 15, 12
End Sub

Sub AddCameraLink()
  Dim s, steps, bodies, i, x
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "从工作票到摄像头：建立自动关联", "05  票—设备—视频联动", 12
  steps = Array("字段标准化", "建立三类映射", "分层匹配摄像头", "检查可用性")
  bodies = Array("站点、电压等级、间隔、设备名称与编号转换为统一编码。", "设备台账；摄像头台账；设备/区域—摄像头—预置位关联表。", "设备编码精确匹配；站点间隔模糊匹配；无法唯一时人工确认。", "检查在线、画质、时钟与遮挡，优选最佳视角，多路交叉验证。")
  For i = 0 To 3
    x = 55 + i * 220
    AddShape s, msoShapeHexagon, x + 45, 128, 100, 86, IIf(i < 2, C(0,142,181), C(15,143,125)), -1, 0
    AddText s, CStr(i + 1), x + 77, 150, 36, 34, 23, C(255,255,255), True, 2
    AddPanel s, x, 235, 190, 154, steps(i), bodies(i), IIf(i < 2, C(0,193,220), C(46,211,183)), 14, 11
  Next
  AddPanel s, 125, 420, 710, 60, "输出", "每张工作票形成“作业监控任务”：工作票ID、时间、设备、区域、摄像头、预置位、关注风险和待调用算法。", C(255,154,61), 13, 11
End Sub

Sub AddVideoTimeline()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "按工作时间获取视频并自动分析", "05  票—设备—视频联动", 13
  AddShape s, msoShapeRectangle, 120, 257, 720, 4, C(52,92,128), -1, 0
  AddShape s, msoShapeOval, 180, 235, 48, 48, C(0,142,181), -1, 0
  AddShape s, msoShapeOval, 456, 225, 68, 68, C(218,82,76), -1, 0
  AddShape s, msoShapeOval, 732, 235, 48, 48, C(15,143,125), -1, 0
  AddPanel s, 72, 120, 260, 96, "作业前｜准备", "解析票面，检查摄像头在线与视角；计划开始前5—10分钟预热。", C(0,193,220), 15, 11
  AddPanel s, 350, 315, 260, 115, "作业中｜实时监护", "以实际许可开始时间接入实时流；短片段流式分析，高风险即时预警。", C(255,100,91), 15, 11
  AddPanel s, 628, 120, 260, 96, "作业后｜补检复盘", "按实际终结时间停止；链路中断则补调历史录像离线分析。", C(46,211,183), 15, 11
  AddText s, "计划时间用于提前准备；实际许可/终结时间决定监控起止。所有系统必须统一时钟。", 180, 463, 600, 25, 12, C(255,183,77), True, 2
End Sub

Sub AddLinkChallenges()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "票—设备—视频联动的主要难点", "05  票—设备—视频联动", 14
  heads = Array("名称不统一", "附近不等于可见", "计划与实际不一致", "并发与算力压力", "跨系统接口稳定性")
  bodies = Array("建立设备主数据与别名词典，以唯一设备编码为关联主键。", "维护摄像头覆盖设备、有效预置位、画质和优先级并现场校验。", "以许可、间断、复工、终结事件驱动任务状态，计划时间仅兜底。", "按风险选择算法；人员/运动先过滤；任务队列和GPU池弹性调度。", "统一数据服务与适配层解耦，支持重试、补调、断点与全程审计。")
  For i = 0 To 4
    x = 44 + (i Mod 3) * 295
    y = 120 + Int(i / 3) * 174
    AddPanel s, x, y, 272, 145, heads(i), bodies(i), IIf(i = 2, C(255,154,61), C(0,193,220)), 15, 11
  Next
  AddPanel s, 634, 294, 272, 145, "落地抓手", "设备主数据、摄像头覆盖台账、作业状态事件、任务编排与审计日志。", C(46,211,183), 15, 12
End Sub

Sub AddEvidenceLoop()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "违章事件如何形成可核查的证据闭环", "06  事件与处置闭环", 15
  AddPanel s, 48, 122, 430, 294, "每条事件至少包含", _
    "• 工作票编号与作业任务" & vbCrLf & _
    "• 站点、间隔、设备与作业区域" & vbCrLf & _
    "• 摄像头、预置位与事件时间" & vbCrLf & _
    "• 违章类型、风险等级、置信度、触发规则" & vbCrLf & _
    "• 标注关键帧、前后视频和原始索引" & vbCrLf & _
    "• 制度依据、通知对象、确认与处置结果", C(0,193,220), 16, 12
  AddPanel s, 515, 122, 397, 294, "闭环流程", _
    "算法发现疑似事件" & vbCrLf & "        ↓" & vbCrLf & _
    "多模态规则复核" & vbCrLf & "        ↓" & vbCrLf & _
    "分级推送 → 人工确认 → 处置反馈" & vbCrLf & "        ↓" & vbCrLf & _
    "证据归档 → 难例回流 → 模型与规则优化", C(46,211,183), 16, 13
  AddText s, "每次预警都能回答：为什么报警？证据是什么？关联哪项工作？谁应处理？是否已经闭环？", 90, 450, 780, 32, 14, C(255,183,77), True, 2
End Sub

Sub AddAgentPosition()
  Dim s, heads, bodies, i, x
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "下一阶段智能体预警的定位", "07  智能体预警", 16
  AddText s, "智能体不是只会聊天的界面，而是安全管控流程的“任务协调与辅助决策中枢”", 74, 108, 812, 35, 17, C(0,193,220), True, 2
  heads = Array("理解任务", "自动规划", "调用工具", "综合研判", "推动闭环")
  bodies = Array("读取工作票，提取时间、地点、设备、人员、措施和危险点。", "选择摄像头、算法、阈值、时间窗和巡检频率。", "查询台账资质、控制预置位、调视频、调用模型与消息服务。", "融合票面约束、视觉结果、设备状态与规则库，形成风险解释。", "通知正确人员、跟踪确认、超时升级、归档并持续学习。")
  For i = 0 To 4
    x = 36 + i * 184
    AddPanel s, x, 178, 166, 218, CStr(i + 1) & "  " & heads(i), bodies(i), IIf(i < 3, C(0,193,220), C(46,211,183)), 14, 11
  Next
  AddText s, "视频模型负责“看见了什么”  ｜  工作票负责“应该怎么做”  ｜  智能体负责“是否有风险、通知谁、怎么办”", 65, 440, 830, 30, 13, C(255,183,77), True, 2
End Sub

Sub AddAgentProcess()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "智能体预警的完整运行过程", "07  智能体预警", 17
  AddPanel s, 48, 132, 270, 293, "作业前｜风险预控", _
    "1. 读取工作票及资料" & vbCrLf & _
    "2. 检查字段、时间、设备与人员资质" & vbCrLf & _
    "3. 提取重点风险" & vbCrLf & _
    "4. 生成摄像头与算法监控计划" & vbCrLf & _
    "5. 提前提示离线、无法匹配等问题", C(0,193,220), 17, 12
  AddPanel s, 345, 132, 270, 293, "作业中｜实时监护", _
    "1. 按实际许可启动视频任务" & vbCrLf & _
    "2. 接收模型候选事件" & vbCrLf & _
    "3. 结合票、区域、人员、设备二次判断" & vbCrLf & _
    "4. 去重、合并、分级并生成解释" & vbCrLf & _
    "5. 高风险即时通知，疑似事件人工复核", C(255,100,91), 17, 12
  AddPanel s, 642, 132, 270, 293, "作业后｜复盘学习", _
    "1. 检查未闭环事件与视频中断" & vbCrLf & _
    "2. 自动生成安全摘要和事件清单" & vbCrLf & _
    "3. 回流确认违章、误报与处置结果" & vbCrLf & _
    "4. 更新样本库、规则库与知识库" & vbCrLf & _
    "5. 形成站点、班组、类型趋势分析", C(46,211,183), 17, 12
End Sub

Sub AddExplainableAlert()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "智能体如何做到“预警准确、解释清楚”", "07  智能体预警", 18
  AddPanel s, 48, 120, 340, 300, "组合式判定机制", _
    "专用视觉模型" & vbCrLf & "＋ 确定性业务规则" & vbCrLf & "＋ 权威知识库" & vbCrLf & "＋ 人工把关" & vbCrLf & vbCrLf & _
    "大模型负责归纳、解释和流程编排；关键生产判断必须受规则、权威数据和专用模型约束。", C(0,193,220), 17, 14
  AddPanel s, 420, 120, 492, 300, "风险评分考虑五类因素", _
    "01  违章严重程度：可能造成的人身与设备后果" & vbCrLf & _
    "02  视觉置信度：是否持续、稳定检测到行为" & vbCrLf & _
    "03  作业对象风险：电压等级、邻近带电体、高处作业" & vbCrLf & _
    "04  时间持续性：持续多久、是否重复发生" & vbCrLf & _
    "05  多源一致性：多帧、多摄像头、工作票、设备状态互证", C(46,211,183), 17, 12
  AddText s, "预警示例：10:23，CAM-03连续8秒检测到未戴安全帽，关联工作票WP-2026-XXX，置信度0.92，判定橙色预警，请负责人3分钟内确认。", 70, 447, 820, 42, 11, C(255,183,77), False, 2
End Sub

Sub AddAlertLevels()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "智能体预警分级及处置机制", "07  智能体预警", 19
  AddPanel s, 48, 125, 270, 270, "红色｜立即制止并升级", _
    "适用：误入带电间隔、高风险越界、高处未系安全带、人员倒地、明火烟雾。" & vbCrLf & vbCrLf & _
    "处置：现场声光/语音提醒；负责人、管理人员和指挥中心同步通知；超时自动升级。", C(235,78,72), 16, 12
  AddPanel s, 345, 125, 270, 270, "橙色｜限时纠正", _
    "适用：未戴安全帽、现场吸烟、持续使用手机、重复一般违章。" & vbCrLf & vbCrLf & _
    "处置：推送关键帧和短视频，要求负责人限时确认整改；逾期升级。", C(242,148,45), 16, 12
  AddPanel s, 642, 125, 270, 270, "黄色｜复核或关注", _
    "适用：置信度中等、部分遮挡、防护用品疑似不规范、摄像头质量下降。" & vbCrLf & vbCrLf & _
    "处置：进入监控中心复核队列，不直接对现场作出违章结论。", C(221,190,63), 16, 12
  AddText s, "抑制预警疲劳：多帧确认 ｜ 事件合并 ｜ 告警冷却 ｜ 风险变化才重复提醒 ｜ 人工反馈校准阈值", 75, 438, 810, 32, 13, C(46,211,183), True, 2
End Sub

Sub AddAgentFoundation()
  Dim s, heads, bodies, i, x
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "智能体建设需要的能力底座", "07  智能体预警", 20
  heads = Array("工具层", "知识层", "规则层", "状态层", "安全治理层")
  bodies = Array("工作票、台账、资质、摄像头、视频、模型、通知与归档接口。", "安全规程、违章库、制度、设备风险、历史案例与处置预案。", "字段校验、设备映射、违章判定、风险分级、通知与升级规则。", "保存票任务状态、事件、通知、反馈与未完成事项，持续跟踪。", "最小权限、人工审批、脱敏、审计、工具调用防护与故障降级。")
  For i = 0 To 4
    x = 36 + i * 184
    AddPanel s, x, 145, 166, 236, heads(i), bodies(i), IIf(i < 3, C(0,193,220), C(46,211,183)), 15, 11
  Next
  AddPanel s, 100, 415, 760, 62, "故障降级", "OCR不确定转人工；摄像头不可用提示换机位或补调；模型异常保留视频并生成补检任务；智能体异常不影响原有人工管控。", C(255,154,61), 13, 11
End Sub

Sub AddAchievements()
  Dim s, labels, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "阶段性成果：以可验证数据说话", "08  阶段成果", 21
  labels = Array("接入工作票类型", "关键字段数量", "关键字段准确率", "设备—摄像头关联", "接入摄像头", "已验证违章类别", "视频算法指标", "平均预警时延")
  For i = 0 To 7
    x = 48 + (i Mod 4) * 220
    y = 125 + Int(i / 4) * 145
    AddShape s, msoShapeRoundedRectangle, x, y, 192, 112, C(19,45,73), IIf(i < 4, C(0,193,220), C(46,211,183)), 0
    AddText s, "【填实测】", x + 18, y + 20, 156, 32, 21, IIf(i < 4, C(0,193,220), C(46,211,183)), True, 2
    AddText s, labels(i), x + 16, y + 68, 160, 24, 12, C(199,215,230), False, 2
  Next
  AddText s, "正式汇报前请注明测试集、样本量和统计口径；未验证能力统一放入“下一阶段计划”。", 130, 435, 700, 30, 12, C(255,183,77), True, 2
End Sub

Sub AddRoadmap()
  Dim s, heads, bodies, i, x, y
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(7,27,48)
  AddHeader s, "下一阶段实施计划", "09  推进计划", 22
  heads = Array("能力核实与数据治理", "打通最小业务闭环", "提升识别质量", "上线智能体辅助预警", "规模化推广")
  bodies = Array("梳理字段、标签、设备主数据和摄像头覆盖关系。", "选择典型站点，完成票解析—联动—识别—复核—归档。", "补充小目标、遮挡、夜间样本，建立难例回流和回归测试。", "先做编排、解释与处置跟踪，关键操作保持规则约束和人工确认。", "形成接口、映射、算法、预警和运营评价标准，向更多站点复制。")
  For i = 0 To 4
    x = 50 + i * 180
    y = 135 + (i Mod 2) * 42
    AddShape s, msoShapeOval, x + 52, y, 58, 58, IIf(i < 2, C(0,142,181), C(15,143,125)), -1, 0
    AddText s, CStr(i + 1), x + 64, y + 12, 34, 30, 18, C(255,255,255), True, 2
    AddPanel s, x, 225, 160, 190, heads(i), bodies(i), IIf(i < 2, C(0,193,220), C(46,211,183)), 13, 10
    If i < 4 Then AddText s, "→", x + 157, 285, 25, 30, 18, C(94,120,148), True, 2
  Next
End Sub

Sub AddSummary()
  Dim s
  Set s = pres.Slides.Add(pres.Slides.Count + 1, ppLayoutBlank)
  SetBackground s, C(5,22,42)
  AddHeader s, "汇报总结", "10  总结", 23
  AddPanel s, 58, 124, 390, 102, "视频：从人工抽查到自动发现", "视频切片、目标跟踪、动作/区域规则和多模态复核，自动生成证据片段。", C(0,193,220), 15, 11
  AddPanel s, 510, 124, 390, 102, "工作票：从文档到业务数据", "PaddleOCR、版面/表格解析、专业词典和业务校验形成结构化字段。", C(0,193,220), 15, 11
  AddPanel s, 58, 250, 390, 102, "联动：解决工作票与视频“两张皮”", "以地点、设备编码和实际作业时间为纽带，自动调摄像头和算法。", C(46,211,183), 15, 11
  AddPanel s, 510, 250, 390, 102, "智能体：从识别结果到处置闭环", "连接票、视频、算法、知识和流程，实现事前预控、事中预警、事后复盘。", C(46,211,183), 15, 11
  AddShape s, msoShapeRoundedRectangle, 90, 393, 780, 72, C(0,112,145), -1, 0
  AddText s, "最终目标：形成“票、设备、人、视频、风险、处置”六要素贯通的智能管控体系", 115, 408, 730, 28, 17, C(255,255,255), True, 2
  AddText s, "推动电网作业安全管理从事后抽查向全过程主动防控转变", 180, 442, 600, 22, 13, C(194,230,237), False, 2
End Sub
