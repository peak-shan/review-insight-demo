# 项目规范

- 技术栈：Python 3.12、FastAPI、uv、jieba、pandas、openpyxl；原生 HTML/CSS/JavaScript、ECharts CDN。
- 使用 `uv sync` 安装依赖，提交 pyproject.toml、uv.lock 与 .python-version，不提交 .venv。
- Python 函数必须提供参数和返回值类型注解，以及说明用途的 docstring。
- 所有主动 HTTP 请求必须指定 timeout；前端 fetch 使用 AbortController 和定时器。
- 支持 CSV / XLSX；CSV 保留 UTF-8/BOM、重复列名和行列数校验。XLSX 使用 pandas.read_excel(sheet_name=None, engine="openpyxl") 读取全部 sheet。
- 文件格式以 .csv/.xlsx 后缀优先（不区分大小写），无后缀时使用 Content-Type；不支持的后缀返回 415。
- 验证大小（2 MB）、所有 sheet 合计数据行数（10000 行）、编码和空文本；无评论类列时返回中文错误，包含所有实际 sheet 名与列名。
- 情感分类为教学用关键词规则；保持规则、比例分母与中性处理方式可解释。
- 运行 `uv run pytest` 验证分析逻辑与 API；修改前端后检查上传、错误和图表展示。
- 无用户明确要求，不发布网站，不添加真实评论或凭据。

## 列名识别与计数规范

- 规则集中在 `app/columns.py` 的 `COLUMN_RULES` 字典；新增同义词只修改此处并增加相应测试，不调用大模型。
- 归一化：Unicode NFKC、转小写，仅保留字母/数字/汉字，去掉空格、下划线、括号、标点。例如 `好评点分析（正面）` → `好评点分析正面`。
- 按归一化后的子串匹配（不是整列名相等）：
  - 好评：好评 / 好评点 / 正面 / positive / good；排除 差评 / 负面。
  - 差评：差评 / 差评点 / 负面 / negative / bad。
  - 通用：评论 / 评价 / comment / review / content / 买家留言 / feedback。
  - 需求：需求 / 建议 / expect（可选，不加入情感语料和比例分母）。
- 单列只归一个角色，冲突优先级：差评 > 好评 > 需求 > 通用；如 `Good Review` 为好评，`评论建议` 为需求。同一角色的多个列全部纳入，不覆盖、不去重。
- 逐 sheet 决定模式：存在好评/差评列即使用专用模式；专用列每个非空文本单元格直接归类，通用列只纳入中性，其余计入 ignored_general 供核对。专用列存在但单元格为空时，也不改用通用好差评分类。
- 只有通用评论列时沿用关键词分类：正负命中持平或均未命中为中性。词频全部复用 analytics.top_words，禁止分叉维护多套分词/停用词。
- total 是好评 + 差评 + 中性非空文本单元格数；比例分母为 total，范围 0–1。valid_rows 为实际贡献语料的原始行数；同一行可贡献多条。
- 合并行保留 source_sheet 与 source_row（含表头的 1-based 行号）。每个 sheet 报告列名、识别角色、有效行数、分类数量、忽略通用条数和跳过原因，包括空 sheet。
- Excel 首行作为列名；空值、纯空白和非文本单元格不计语料，保留 NA/N/A 等原始文本。Excel 重复列名按列位置分别读取。
- Excel 测试文件必须放在 pytest tmp_path；保留并跑通原 CSV 回归测试。
