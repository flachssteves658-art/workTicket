# 基于OCR与大型语言模型的电力工作票关键信息自动抽取研究

作者：薛远  
单位：[待填写]  
通信地址及邮箱：[待填写]

> 稿件说明：本文依据现有系统原型和少量样例验证撰写。为保证学术真实性，尚未完成的批量实验数据均以“待测”标记，不能在投稿前替换为未经实验获得的数值。

## 摘要

电力工作票记录了作业编号、作业时间、工作地点、目标设备、人员职责和安全措施等关键安全信息，是现场作业许可、过程监督和风险追溯的重要依据。然而，实际工作票普遍存在表格结构复杂、合并单元格较多、字段表达不统一、扫描质量差以及手写与印刷内容混杂等问题，传统光学字符识别方法只能获得非结构化文本，难以直接形成可用于业务系统的标准字段。针对上述问题，本文提出一种融合光学字符识别与大型语言模型的电力工作票关键信息自动抽取方法。该方法首先利用图像预处理和PPStructureV3完成文本、版面及表格内容识别；随后根据工作票领域Schema构造约束式提示词，由大型语言模型执行字段别名归一化、跨行内容关联、复合字段拆分、时间格式标准化和OCR噪声修复；进一步结合字段完整性、OCR置信度、格式约束和多模型一致性建立质量分级机制，将低可信结果转入人工复核。系统采用本地OCR与文本级语言模型解析相结合的方式，可降低敏感票面图像外传风险，并保留中间文本和置信度以支持结果追溯。原型系统已实现从工作票图像输入到结构化JSON输出，并可将地点和设备实体写入知识图谱，为摄像头自动关联和现场视频安全分析提供数据基础。初步样例验证表明，该方法能够抽取工作票编号、计划时间、电压等级和负责人等字段，但在低质量图像、复杂表格和长文本条件下仍存在字段粘连及信息缺失。后续将在统一标注的数据集上，从字段准确率、精确率、召回率、F1值、处理效率和人工复核率等方面开展对比与消融实验。

**关键词：** 电力工作票；光学字符识别；大型语言模型；信息抽取；结构化数据；人机协同

## Abstract

Electrical work tickets contain safety-critical information, including ticket identifiers, work schedules, locations, target equipment, personnel responsibilities and safety measures. In practice, automatic processing is hindered by complex tables, merged cells, inconsistent field aliases, degraded scans and mixed printed-handwritten content. Conventional optical character recognition (OCR) converts images into text but does not reliably map noisy text to standardized business fields. This paper proposes an automated key-information extraction method that integrates OCR with a large language model (LLM). Image preprocessing and PPStructureV3 are first used to recognize text, layout and table content. A schema-constrained prompt then guides the LLM to normalize aliases, associate multi-line values, split composite fields, standardize temporal expressions and repair contextually recoverable OCR errors. A quality-control mechanism combines OCR confidence, field completeness, format constraints and cross-model consistency to identify records requiring manual verification. By keeping image processing local and transmitting only text when a remote LLM is used, the architecture reduces the exposure of sensitive source images while preserving interpretable intermediate evidence. A prototype has implemented the pipeline from ticket images to structured JSON and supports downstream knowledge-graph construction and camera association. Preliminary case tests demonstrate successful extraction of ticket numbers, time ranges, voltage levels and responsible personnel, while also revealing limitations involving low-quality images, complex tables and long-text noise. Formal evaluations on an independently annotated dataset will report field-level accuracy, precision, recall, F1 score, processing efficiency and manual-review rate.

**Keywords:** electrical work ticket; optical character recognition; large language model; information extraction; structured data; human-in-the-loop

## 1 引言

电力工作票是组织检修、试验、安装和巡视等现场作业的重要业务载体。票面信息不仅用于确认“何时、何地、由谁、对何设备开展何种工作”，还用于约束停电范围、接地措施、人员职责和作业终结状态。随着电力安全管控逐步数字化，工作票信息需要进一步参与设备台账检索、摄像头选择、视频检测任务配置以及违规事件追溯。然而，大量存量工作票仍以扫描件、照片或PDF形式存在，人工录入成本高、处理速度慢，且容易出现漏填和字段不一致。

OCR技术能够识别票面字符，但从“识别文本”到“可直接使用的结构化字段”仍存在明显距离。首先，工作票通常采用多级表格，字段名称和值可能分布在不同单元格或跨页区域；其次，同一概念存在多种表述，例如“工作地点或设备”“作业地点”“站点/间隔”等均可能对应空间信息；再次，编号、设备双重名称、日期时间和安全措施中混合数字、字母、单位及专业术语，局部OCR错误会改变业务含义；最后，部分内容没有明确字段标签，需要结合上下文确定其角色。

已有研究表明，将OCR与大型语言模型结合，可以利用语言模型的上下文理解能力完成异构标签的字段归一化，并在一定程度上补偿OCR噪声[1]。与植物标本标签类似，工作票也具有版式多样、字段别名多、复合字段多、时间格式不统一和图像质量差等特征，但二者在风险等级和约束条件上存在明显区别：工作票中的设备编号、操作对象、人员职责和作业时间具有较强的安全语义，模型不能仅依据常识自由补全，必须保留来源证据并对关键字段进行严格校验。

基于此，本文将“OCR识别—语言模型结构化解析—置信度分级—人工复核”的思想迁移至电力工作票场景，主要工作如下：

1. 构建面向工作票的16字段标准Schema，将不同票种和不同模板中的字段映射为统一的数据表示；
2. 设计面向专业票据的约束式提示策略，使语言模型完成字段归一化、复合字段拆分、时间标准化和跨行语义关联，同时禁止无依据补全；
3. 提出融合OCR置信度、规则校验、字段完整性和模型一致性的质量控制机制，实现低可信样本的自动分流；
4. 实现可追溯的原型系统，并将结构化结果用于知识图谱和摄像头任务关联，为工作票与现场视频的联动提供基础。

## 2 相关研究

### 2.1 文档OCR与版面分析

现代OCR系统通常包含文本检测、方向校正和文本识别等环节。PP-OCR通过轻量化检测与识别网络兼顾精度和部署效率[2]，PaddleOCR进一步提供表格识别和版面分析能力，适合处理包含标题、段落和表格的业务文档。对于工作票而言，单纯按字符顺序输出文本容易破坏字段与单元格之间的关系，因此需要保留文本框坐标、行序和表格结构。

LayoutLM及其后续模型将文本、二维位置和视觉特征联合建模，在表单理解和票据抽取任务中表现出较强能力[3-4]。但此类模型通常需要领域标注数据和训练资源，面对企业内部多模板、小样本场景时迁移成本较高。本文选择以可部署的OCR版面分析为前端，并利用语言模型进行后端语义解析，在数据规模尚小的阶段降低专用模型训练门槛。

### 2.2 命名实体识别与字段抽取

规则和词典方法具有结果可控、便于解释的优点，但对模板变化和OCR噪声较敏感。序列标注模型可以学习上下文中的实体边界，却依赖高质量标注语料。基于机器阅读理解的命名实体识别方法把不同实体类型转化为自然语言查询，能够统一处理扁平和嵌套实体[5]，适合抽取地点、设备、人员和安全措施等领域实体。

不过，工作票字段并不都能等价为局部实体识别任务。例如，计划起止时间可能跨越多个文本块，工作内容可能对应多个设备，负责人、许可人和签发人虽然同属人员实体，但业务角色不同。因此，本文将领域实体识别作为可选的稳定抽取层，并由语言模型完成跨块关联、角色消歧和结构化映射。

### 2.3 大型语言模型驱动的信息抽取

大型语言模型具备指令理解、上下文推理和少样本泛化能力，可以通过提示词将非结构化文本转换为预定义JSON。相关研究已探索利用生成式语言模型完成命名实体识别[6]。Wen[1]将PaddleOCR与DeepSeek结合，用领域提示词从植物标本标签中提取16项元数据，并通过OCR置信度筛选低质量样本。该研究说明，语言模型不仅能完成字段解析，还可能通过上下文补偿局部OCR错误。

工作票场景对可验证性要求更高。语言模型的语义补偿如果缺少边界约束，也可能演变为事实幻觉。因此，本文采用“只从给定文本取值、保留证据片段、关键字段执行规则校验、低可信结果人工复核”的设计，将语言模型定位为受约束的结构化解析器，而非事实生成器。

## 3 数据与字段体系

### 3.1 数据来源与分层原则

实验数据应从脱敏后的真实工作票或经批准的内部样本中获取，并覆盖不同票种、模板、图像质量和填写方式。为考察不同难度条件下的性能，建议将样本划分为以下类别：

- 标准电子打印票：版式规则、字符清晰；
- 扫描打印票：存在压缩、倾斜、阴影或低对比度；
- 拍照票据：存在透视变形、反光和背景干扰；
- 印刷与手写混合票：签名、补充时间或执行状态为手写内容；
- 复杂长票：包含跨页表格、多条安全措施和多个设备对象。

数据划分应以票据来源或模板批次为单位，避免同一工作任务的不同页同时进入训练集和测试集。涉及人员姓名、联系方式、设备位置和企业信息的内容应在标注前脱敏。若调用云端语言模型，应仅提交必要的OCR文本，并根据单位的数据安全规定进一步执行字段替换或使用本地模型。

### 3.2 工作票核心字段Schema

参照现有工作票内容及后续视频关联需求，本文定义表1所示的16个核心字段。

**表1 工作票结构化字段及约束**

| 序号 | JSON字段 | 中文含义 | 类型 | 主要约束或示例 |
|---:|---|---|---|---|
| 1 | `ticketNo` | 工作票编号 | 字符串 | 保留前导零，不得推测 |
| 2 | `ticketType` | 工作票类型 | 枚举/字符串 | 第一种、第二种、带电作业等 |
| 3 | `workUnit` | 作业单位或班组 | 字符串 | 保留完整单位名称 |
| 4 | `station` | 变电站或作业站点 | 字符串 | 与站点标准名映射 |
| 5 | `workLocation` | 工作地点或间隔 | 字符串/数组 | 支持多个区域 |
| 6 | `equipment` | 目标设备及编号 | 对象数组 | 设备名称、编号、电压等级 |
| 7 | `workContent` | 工作内容 | 字符串/数组 | 不得改写关键操作对象 |
| 8 | `plannedStart` | 计划开始时间 | 日期时间 | 统一为`YYYY-MM-DD HH:mm` |
| 9 | `plannedEnd` | 计划结束时间 | 日期时间 | 不早于开始时间 |
| 10 | `responsiblePerson` | 工作负责人 | 字符串 | 与其他人员角色区分 |
| 11 | `permitter` | 工作许可人 | 字符串 | 无值时返回`null` |
| 12 | `issuer` | 工作票签发人 | 字符串 | 无值时返回`null` |
| 13 | `crewMembers` | 工作班成员 | 字符串数组 | 分隔多个人名，去除人数描述 |
| 14 | `safetyMeasures` | 安全措施 | 对象数组 | 措施文本、执行状态、证据 |
| 15 | `hazards` | 危险点或注意事项 | 字符串数组 | 仅提取票面明确内容 |
| 16 | `ticketStatus` | 许可、执行或终结状态 | 枚举/字符串 | 待许可、执行中、已终结等 |

每个字段除标准值外，还应保存`evidence`、`sourceBlock`和`confidence`。其中，`evidence`为支持该结果的OCR原文片段，`sourceBlock`用于回溯票面区域，`confidence`用于质量分级。

### 3.3 标注规范

由具备工作票知识的标注人员依据原图建立标准答案。对于模糊字段，不应根据常识补全，而应标记为“不可判读”。建议采用双人独立标注和第三人仲裁机制，并记录字段缺失、文字模糊、表格结构异常和跨页关联等错误类型。正式实验中还应报告标注一致性，以区分模型误差和人工解释差异。

## 4 OCR-LLM工作票抽取方法

### 4.1 总体框架

系统流程包括图像预处理、OCR与版面分析、文本重组、语言模型结构化解析、结果校验和质量分流六个阶段：

```text
工作票图像/PDF
     ↓
方向校正、去噪、二值化与透视校正
     ↓
PPStructureV3文本检测、识别和表格恢复
     ↓
按页面、表格、文本块和坐标重组OCR结果
     ↓
领域Schema约束的大型语言模型解析
     ↓
格式规则、实体一致性与置信度融合校验
     ↓
可信结果入库 / 低可信结果人工复核
```

图像在本地完成OCR，语言模型仅接收重组后的文本、必要的位置标签和字段约束。当采用本地语言模型时，全部数据可在内网环境中处理；当采用云端模型时，系统可先移除人员姓名等敏感内容，再提交最小必要文本。

### 4.2 图像预处理与版面保持

输入图像首先执行方向检测、灰度化、对比度增强和可选二值化。对于手机拍照图像，增加边缘定位和透视矫正；对于多页PDF，逐页转换为图像并保留页码。OCR阶段输出每条文本的内容、坐标、所属页、所属表格单元格和识别置信度。

设一张工作票包含$n$条OCR文本行，第$i$行的识别置信度为$c_i$，则图像级平均置信度为：

$$
C_{ocr}=\frac{1}{n}\sum_{i=1}^{n}c_i.
$$

仅使用平均值可能掩盖关键字段的局部低置信度，因此系统同时计算票号、设备编号、时间和人员等关键区域的最小置信度$C_{key}$。文本重组时不简单地从左到右拼接全部内容，而是先按页面和表格区域分组，再根据纵坐标和横坐标恢复阅读顺序，并用`[ROW]`、`[CELL]`等标记保留结构边界。

### 4.3 领域提示设计

参考异构标签抽取中的提示设计思想[1]，本文针对工作票提出六项提示原则：

1. **字段别名归一化。** 将“编号”“工作票号”“票号”等映射至`ticketNo`，将“工作地点或设备”“作业区域”等映射至相应标准字段；
2. **复合字段拆分。** 将同一单元格中的地点、设备、编号和工作内容拆分为独立字段，并保留它们之间的对应关系；
3. **时间格式标准化。** 将中文日期、斜杠日期和分散的年月日时分统一为规定格式，但原文缺失的年月日不得自行补全；
4. **单位与符号统一。** 统一`kV`、设备编号连接符和人员列表分隔符，同时保留原始值用于审计；
5. **跨行上下文关联。** 结合字段标题、相邻单元格和段落上下文识别跨行安全措施及无显式标签的信息；
6. **证据约束与空值策略。** 每个非空字段必须返回OCR证据；无法从原文确认时返回`null`，禁止根据常识猜测。

为降低输出随机性，推理温度设置为较低值，并要求模型仅返回符合JSON Schema的对象。解析失败时，系统从输出中截取JSON主体进行二次解析；若仍失败，则记录原始响应并进入人工复核，而不是静默丢弃。

### 4.4 OCR噪声补偿与安全边界

语言模型可根据上下文修复明显的标点错误、字段标签错字和被换行分割的文本。例如，当“计划工作时间自……至……”被OCR拆分到多行时，模型可将两处时间重组为`plannedStart`和`plannedEnd`。但是，票号、设备编号、人员姓名和时间数字属于高风险字段，不能仅凭语言概率修改。

本文将修复分为两类：

- **低风险规范化**：空格清理、全半角转换、时间格式变换和字段别名映射，可自动接受；
- **高风险语义修复**：数字替换、设备编码补全、人名纠错和缺失信息推断，必须同时满足OCR候选证据、规则约束或另一模型的一致性，否则进入人工复核。

对于已训练的BERT-MRC领域模型，可将其抽取结果与语言模型结果进行交叉校验。若两者在标准化后完全一致，则提高字段可信度；若关键字段冲突，则保留两个候选值和原文证据，不自动覆盖。

### 4.5 质量分级与人工复核

字段最终可信度由OCR置信度、格式合法性、字段完整性和模型一致性共同决定：

$$
C_f=\alpha C_{ocr,f}+\beta C_{fmt}+\gamma C_{cons}+\delta C_{evi},
$$

其中，$C_{ocr,f}$为字段证据区域的OCR置信度，$C_{fmt}$表示编号、时间和枚举值等格式是否满足约束，$C_{cons}$表示规则、BERT-MRC与LLM结果的一致程度，$C_{evi}$表示返回值能否在OCR证据中对齐；$\alpha+\beta+\gamma+\delta=1$。各权重应在验证集上确定。

系统设置三级质量状态：高可信结果自动入库，中可信结果进入快速确认，低可信结果要求逐字段核对。出现以下任一情况时强制人工复核：工作票编号缺失、开始时间晚于结束时间、关键设备无原文证据、JSON Schema校验失败，或关键字段的多个抽取器结果冲突。

### 4.6 批处理与可追溯存储

批处理模块按文件逐张处理，并在每张票完成后立即写入结果和检查点，记录文件哈希、处理时间、OCR引擎版本、模型名称、提示词版本、原始OCR结果、结构化结果及质量状态。发生接口中断时，可依据文件哈希从未完成样本继续运行，避免重复调用。输出采用JSON Lines或数据库表保存，并可进一步写入Neo4j，形成“工作票—实体—设备—区域—摄像头”的关联结构。

## 5 实验设计与原型验证

### 5.1 实验环境

当前原型使用Python实现，默认采用PPStructureV3完成OCR与版面分析，并支持切换PaddleOCR-VL。结构化解析可选择本地Ollama模型或云端兼容接口；图谱数据库采用Neo4j，演示接口采用FastAPI和Gradio。正式论文应在实验完成后补充CPU、GPU、内存、操作系统、软件版本、模型精确名称和提示词版本，以保证结果可复现。

### 5.2 数据集构成

正式实验建议采用表2所示方式报告数据，所有数值须由实际清点获得。

**表2 工作票实验数据集构成（待实测填写）**

| 数据来源/票种 | 标准打印 | 扫描退化 | 拍照变形 | 手写混合 | 合计 |
|---|---:|---:|---:|---:|---:|
| 变电第一种工作票 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 变电第二种工作票 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 配电工作票 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 其他票种 | 待填 | 待填 | 待填 | 待填 | 待填 |
| 合计 | 待填 | 待填 | 待填 | 待填 | 待填 |

### 5.3 对比方法与消融设置

为验证各模块的实际贡献，设置以下对比方法：

- **OCR+规则**：OCR后使用正则表达式和领域词典抽取；
- **OCR+BERT-MRC**：OCR后使用领域标注数据训练的MRC实体模型；
- **OCR+通用LLM**：不提供领域规则，仅给出目标字段；
- **OCR+领域提示LLM**：使用本文的别名、拆分、标准化和证据约束；
- **本文完整方法**：领域提示LLM与规则校验、可选BERT-MRC一致性和质量分级结合。

消融实验依次移除版面结构标记、字段别名表、证据约束、时间及设备规则、多模型一致性和人工复核触发机制，以观察字段准确率、错误接受率和复核工作量的变化。

### 5.4 评价指标

字段结果与人工标准答案比较。沿用细粒度字段评分思想[1]，完全正确记为1，主体正确但存在非关键缺失或格式偏差记为0.5，错误或无依据生成记为0。仅对原票面中实际存在的字段计算平均字段准确率：

$$
A_{field}=\frac{\sum_{j=1}^{m}s_j}{m},\quad s_j\in\{0,0.5,1\}.
$$

同时报告严格完全匹配率，避免0.5分掩盖关键数字错误。对可转化为实体边界的字段，计算Precision、Recall和F1：

$$
P=\frac{TP}{TP+FP},\quad R=\frac{TP}{TP+FN},\quad F_1=\frac{2PR}{P+R}.
$$

工程指标包括单页OCR时间、语言模型解析时间、端到端处理时间、JSON合法率、自动通过率和人工复核率。为研究语言模型是否补偿OCR误差，计算图像级OCR置信度$C_{ocr}$与字段准确率$A_{field}$之间的Pearson相关系数$r$。若相关性较弱且低置信OCR样本仍能获得较高字段准确率，可说明语言模型具有一定补偿作用；但该结论还需结合消融实验和具体错误案例，不能仅凭相关性推断因果关系。

### 5.5 初步样例结果

当前原型已在少量工作票图像上完成流程验证。一份配电第一种工作票经OCR和规则兜底后，能够识别工作票编号`201501290001`、计划时间范围和`10 kV`电压等级；另一份样例能够识别工作负责人。结果证明了“图像—OCR文本—标准字段—JSON”的基本链路可运行。

与此同时，样例中也出现了结束时间尾部粘连、长串重复字符以及地点、设备和安全措施抽取不完整等问题。由于当前运行结果在缺少BERT-MRC模型检查点时采用规则兜底，这些结果只能作为功能性验证，不能作为本文完整方法的性能结论。

**表3 不同方法的字段抽取结果（待正式实验填写）**

| 方法 | 字段准确率 | 严格匹配率 | Precision | Recall | F1 | JSON合法率 | 平均耗时/页 |
|---|---:|---:|---:|---:|---:|---:|---:|
| OCR+规则 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| OCR+BERT-MRC | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| OCR+通用LLM | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| OCR+领域提示LLM | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |
| 本文完整方法 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 |

**表4 分字段结果（待正式实验填写）**

| 字段 | 样本数 | 完全正确 | 部分正确 | 错误/遗漏 | 字段准确率 |
|---|---:|---:|---:|---:|---:|
| 工作票编号 | 待填 | 待填 | 待填 | 待填 | 待测 |
| 计划时间 | 待填 | 待填 | 待填 | 待填 | 待测 |
| 工作地点 | 待填 | 待填 | 待填 | 待填 | 待测 |
| 设备 | 待填 | 待填 | 待填 | 待填 | 待测 |
| 人员角色 | 待填 | 待填 | 待填 | 待填 | 待测 |
| 安全措施 | 待填 | 待填 | 待填 | 待填 | 待测 |

## 6 讨论

### 6.1 OCR与语言模型的协同作用

OCR和语言模型承担不同角色。OCR负责把图像转换为带位置和置信度的可追溯文本；语言模型负责把异构文本映射到统一Schema，并利用上下文处理跨行和隐式关系。这种分阶段架构相较直接使用端到端多模态模型，具有中间结果可检查、单模块可替换和文本调用成本较低等优点。

参考研究在植物标本标签上观察到OCR置信度与最终字段准确率之间仅呈弱相关，并据此讨论了语言模型的补偿作用[1]。工作票场景是否具有相同现象，需要通过本文设计的相关性分析和消融实验验证。尤其应区分“修复标点或字段标签”与“改写设备编号”两类行为：前者可能提升可用性，后者即使语义看似合理，也可能造成高风险错误。

### 6.2 质量控制的实际意义

安全关键文档不宜只追求平均准确率。即使整体指标较高，少量票号、时间或设备编号错误仍可能影响任务调度和摄像头关联。因此，系统除报告平均性能外，还需单独统计关键字段错误接受率，并通过证据对齐和人工复核控制风险。

置信度分级的目标不是简单拒绝低质量图像，而是优化人工资源：高可信字段自动通过，中可信字段只核对模型标出的局部证据，低可信票据返回原图逐项复核。实际应用中还可记录人工修订结果，用于更新字段别名、规则和后续训练数据。

### 6.3 与下游安全管控的衔接

结构化工作票不是流程终点。标准化后的站点、地点、设备和时间可与基础设施图谱对齐，查询覆盖目标区域的摄像头，并在工作时间窗内启动相应检测项目。视频系统返回的安全帽、反光衣或限制区域告警可以与票号关联，形成可追溯的作业上下文。

本文将这一过程作为应用验证，而不把视频目标检测性能归入工作票抽取算法本身。后续应分别评价字段抽取准确率、设备实体链接准确率、摄像头Top-k召回率和端到端任务延迟，避免用系统演示替代算法实验。

### 6.4 局限性

本文当前仍有以下限制：

1. 原型验证样本数量较少，尚不能得出完整方法优于基线的统计结论；
2. 手写签名、模糊印章、复杂合并单元格和跨页安全措施仍可能导致OCR失败；
3. 语言模型输出受模型版本、提示词和推理参数影响，必须记录版本并控制随机性；
4. OCR置信度与字段可信度并不等价，需要通过标注数据校准融合权重和阈值；
5. 不同单位的票面模板和设备命名规则存在差异，跨单位泛化能力仍需验证；
6. 涉及真实工作票时，需要进一步评估本地部署、脱敏、访问控制和审计策略。

## 7 结论

本文提出了一种面向电力工作票的OCR与大型语言模型协同抽取方法。该方法使用本地OCR识别并保留版面、表格、坐标和置信度信息，通过领域Schema约束的大型语言模型完成字段归一化、复合字段拆分、跨行关联和时间标准化，再利用格式规则、证据对齐和多模型一致性实现质量分级。原型系统已具备从工作票图像到结构化JSON、知识图谱写入和摄像头任务关联的基本能力。

现阶段结果证明了技术链路的可行性，同时暴露出复杂表格、OCR噪声和专用模型缺失等问题。后续工作将构建覆盖不同票种和质量条件的脱敏标注数据集，完成规则、BERT-MRC、通用LLM和领域提示LLM的对比实验，并通过消融、相关性和错误类型分析验证各模块的实际贡献。在真实应用中，还将进一步完善人机协同复核和内网部署机制，使工作票结构化结果在保持可追溯性的前提下服务于现场视频安全管控。

## 参考文献

[1] WEN J. Automated information extraction from plant specimen labels using OCR and large language models[J]. Biodiversity Data Journal, 2026, 14: e177202. DOI: 10.3897/BDJ.14.e177202.

[2] DU Y, LI C, GUO R, et al. PP-OCR: A practical ultra lightweight OCR system[EB/OL]. arXiv:2009.09941, 2020.

[3] XU Y, LI M, CUI L, et al. LayoutLM: Pre-training of text and layout for document image understanding[C]//Proceedings of the 26th ACM SIGKDD International Conference on Knowledge Discovery & Data Mining. 2020: 1192-1200.

[4] XU Y, XU Y, LV T, et al. LayoutLMv2: Multi-modal pre-training for visually-rich document understanding[C]//Proceedings of the 59th Annual Meeting of the Association for Computational Linguistics. 2021: 2579-2591.

[5] LI X, FENG J, MENG Y, et al. A unified MRC framework for named entity recognition[C]//Proceedings of the 58th Annual Meeting of the Association for Computational Linguistics. 2020: 5849-5859.

[6] WANG S, SUN X, LI X, et al. GPT-NER: Named entity recognition via large language models[EB/OL]. arXiv:2304.10428, 2023.

[7] BROWN T B, MANN B, RYDER N, et al. Language models are few-shot learners[C]//Advances in Neural Information Processing Systems. 2020, 33: 1877-1901.

[8] SHI B, BAI X, YAO C. An end-to-end trainable neural network for image-based sequence recognition and its application to scene text recognition[J]. IEEE Transactions on Pattern Analysis and Machine Intelligence, 2017, 39(11): 2298-2304.

## 附录A 结构化输出示例

```json
{
  "ticketNo": {
    "value": "201501290001",
    "evidence": "单位……编号201501290001",
    "sourceBlock": "page_1_block_2",
    "confidence": 0.96
  },
  "ticketType": {
    "value": "配电第一种工作票",
    "evidence": "国网安徽省电力公司配电第一种工作票",
    "sourceBlock": "page_1_title",
    "confidence": 0.98
  },
  "plannedStart": {
    "value": "2015-02-05 07:00",
    "evidence": "计划工作时间自2015年2月5日7时00分",
    "sourceBlock": "page_1_block_6",
    "confidence": 0.93
  },
  "plannedEnd": {
    "value": "2015-02-05 19:00",
    "evidence": "至2015年2月5日19时00分",
    "sourceBlock": "page_1_block_6",
    "confidence": 0.91
  },
  "equipment": [],
  "workLocation": [],
  "responsiblePerson": null,
  "permitter": null,
  "issuer": null,
  "crewMembers": [],
  "safetyMeasures": [],
  "hazards": [],
  "ticketStatus": null,
  "reviewRequired": true,
  "reviewReasons": ["设备字段需要人工确认", "安全措施未完整抽取"]
}
```

## 附录B 领域提示词模板

```text
你是电力工作票信息抽取助手。请仅依据给定OCR文本抽取字段，不得使用常识补写原文没有的信息。

任务：
1. 按给定JSON Schema返回结果；
2. 识别字段别名并映射为标准字段；
3. 拆分同一行或同一单元格中的地点、设备、编号和工作内容；
4. 将能够确定的时间统一为YYYY-MM-DD HH:mm；缺少年、月、日时不得推测；
5. 区分工作负责人、许可人、签发人、监护人和工作班成员；
6. 每个非空字段必须返回OCR原文证据和来源块编号；
7. 无法确认时返回null或空数组；
8. 只输出合法JSON，不输出解释或Markdown。

高风险约束：
- 不得补全、改写或猜测票号、设备编号、人名和时间数字；
- 发现多个冲突候选时全部保留，并将reviewRequired设为true；
- 返回值必须能与OCR证据对应。

OCR文本：
{{ocr_text_with_layout_tags}}
```
