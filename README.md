# 亚马逊评论关键词看板

教学用最小 Web demo：Python 3.12 + FastAPI + uv + jieba + pandas/openpyxl，前端使用原生 HTML 与 ECharts 5.6.0 CDN。支持 CSV / Excel、多 sheet 合并与中英文列名智能识别。

## 本地运行（PowerShell）

```powershell
cd "D:\AI Agent\codex"
# 首次安装 uv 后，当前终端可能需要刷新 PATH；新开的终端通常不需要。
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv sync --locked
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 http://127.0.0.1:8000，选择项目根目录的 `sample_reviews.csv` 或 `sample_reviews.xlsx`，点击“分析评论”。如果旧服务没有使用 `--reload`，升级后需要重启。
接口文档：http://127.0.0.1:8000/docs 。按 Ctrl+C 停止服务。

## 验证

```powershell
uv run pytest
```

示例包含 30 条虚构服装评论：15 条好评、11 条差评、4 条中性；占比分别为 50% 和约 36.7%。

Excel 样例含 4 个 sheet：分析明细（好评点分析/差评点分析/需求建议）、简洁列名（好评/差评）、通用评论（评论内容）、商品信息（演示跳过无评论列的 sheet）。贡献语料分别为 7、5、4、0 条，共 11 个有效行、16 条语料：好评 8、差评 6、中性 2。

## API 与规则

- `GET /`：返回 `app/static/index.html`。
- `POST /api/analyze`：以 multipart/form-data 提交名为 `file` 的文件。
- 文件名后缀 `.csv` / `.xlsx` 优先（不区分大小写）；无后缀时根据 `text/csv`、`application/csv` 或标准 XLSX Content-Type 判断。不支持的后缀返回 415。
- CSV 使用 UTF-8（支持 BOM），保留重复列名与行列数校验；Excel 首行作列名，使用 `pandas.read_excel(sheet_name=None, engine="openpyxl")` 读取所有 sheet，包括隐藏 sheet。Excel 不支持加密文件或旧 `.xls`。
- 最多 2 MB、所有 sheet 合计 10000 个数据行（不含各表表头）。空白文本忽略；Excel 非文本单元格不计入评论，保留 NA/N/A 等文字。格式、编码或缺少评论列返回 400，超出文件大小返回 413，缺少文件返回 422。
- 兼容响应字段：`total`、`top_words`（`word`/`count`）、`positive`、`negative`、`neutral`、`positive_ratio`、`negative_ratio`。
- 新增 `positive_top_words` / `negative_top_words`，分别统计好差评 Top20；页面下拉框可切换全部/好评/差评语料。
- 新增 `valid_rows` 和 `rows`：每个有效原始行包含 `source_sheet`、`source_row`（含表头的 1-based 行号）、`positive` / `negative` / `neutral` 文本列表，以及可选需求文本 `requirements`。
- 新增 `sheets`：每个 sheet 的 `source_sheet`、实际 `columns`、`recognized_columns`、`mode`、`read_rows`、`valid_rows`、`total`、`positive`、`negative`、`neutral`、`ignored_general` 和 `skipped_reason`。CSV 的 sheet 名为 `CSV`。空 sheet 或无有效语料的 sheet 也保留在报告中，贡献 0 条。
- 中文用 jieba 分词；英文统一小写；过滤内置中英文停用词、数字及标点，最多返回 20 个词，按出现次数降序排列。
- 只有通用评论列的 sheet：每个非空评论单元格比较不同正负关键词命中数，多者胜出，持平或未命中归中性。英文关键词整词匹配，中文按子串匹配。
- 存在好评/差评专用列的 sheet：每个非空文本单元格直接作为该类语料，不重新判断情感。同类多个列全部合并，不去重；通用列中仅正负持平/未命中的文本加入中性，其余不重复计入并记录到 `ignored_general`。不同 sheet 可以使用不同模式。
- `total = positive + negative + neutral`，单位为语料单元格，可能大于 `valid_rows`；两项占比范围为 0–1，分母为 total。需求不参与情感计数。关键词规则不理解否定或反讽，可在 `app/analytics.py` 扩展。
- 上传内容仅在请求中处理，不保存到磁盘。首次 jieba 初始化可能略慢。
- ECharts 通过 CDN 加载，需要网络；加载失败时页面仍展示数量及文本词频。分析 fetch 使用 30 秒超时。

## 列名规则

`app/columns.py` 的 `COLUMN_RULES` 集中配置同义词，规则详见 `AGENTS.md`。列名先 NFKC 归一化、转小写并去除空格/下划线/括号/标点，再做子串匹配：

- 好评：好评、好评点、正面、positive、good；排除差评、负面。
- 差评：差评、差评点、负面、negative、bad。
- 通用：评论、评价、comment、review、content、买家留言、feedback。
- 需求：需求、建议、expect。

一列命中多类时优先级为差评 > 好评 > 需求 > 通用。`好评点分析（正面）`、`好评` 都是好评；`Review_Content` 是通用；`评论建议` 是需求。没有任何评论类列时，中文错误会列出全部实际 sheet 名和列名。

## 文件结构

```text
app/
  analytics.py       # 分词与分类
  columns.py         # 可配置列名规则
  imports.py         # CSV/Excel 读取与多 sheet 合并
  main.py            # 页面与上传接口
  static/index.html  # 单页看板
tests/test_app.py    # 逻辑与接口测试
tests/test_excel.py  # 多 sheet、同义词、错误处理测试（使用 tmp_path）
sample_reviews.csv  # 30 条示例
sample_reviews.xlsx # 多工作表样例
AGENTS.md           # 后续 Codex 开发规范
pyproject.toml      # 依赖声明
uv.lock             # 可复现依赖锁
.python-version     # Python 3.12
```

本阶段只完成本地运行，未部署。
