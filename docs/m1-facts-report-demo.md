# M1 本地演示：600760 披露事实报告

演示目标：在本地看到一份只包含**已核对披露事实**的研究报告，并验证它对来源、
PIT、发布范围与失败情形的处理。全程不联网、不调用模型、不对外发布。

## 1. 准备（不把 PDF 提交进仓库）

```bash
# 复现获取指令来自 data/manifests/corpus.v1.json
mkdir -p data/raw/600760/2026H1
curl -fL -o data/raw/600760/2026H1/source.pdf \
  https://static.cninfo.com.cn/finalpage/2026-08-28/1225517994.PDF

# 校验来源哈希与正典哈希（离线）
.venv/bin/python scripts/verify_corpus.py --canonical
```

期望：`OK 600760-2026H1 … 1/1 declared document(s) verified.`

## 2. 启动后端（仅监听回环地址）

```bash
cd services/api
FRP_LOCAL_FACTS_REPORT=1 \
FRP_LOCAL_LLM_ACCESS_TOKEN="$(openssl rand -hex 32)" \
FRP_LOCAL_SOURCE_PDF_600760="$PWD/../../data/raw/600760/2026H1/source.pdf" \
../../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

把同一个 token 记下来，前端必须使用相同的值。

## 3. 启动前端（绑定 127.0.0.1，不暴露到局域网）

```bash
cd apps/web
FRP_LOCAL_FACTS_REPORT=1 \
FRP_LOCAL_LLM_ACCESS_TOKEN="<上一步的 token>" \
npm run dev:facts
```

`dev:facts` 等价于 `next dev -H 127.0.0.1`；`npm run dev` 会监听所有网卡，请勿用于本演示。

## 4. 打开报告

<http://127.0.0.1:3000/research/reports/600760-2026H1>

首次加载约 30–60 秒（每次请求都会重新核验 207 页原始 PDF，不缓存）。

应看到：

- 研究请求：合并利润表中「其中：营业收入」在「2026 年半年度」列的金额；
- 已核对事实：`6,191,107,217.36`，第 46 页，附原文上下文；
- 引用：`…1225517994.PDF#page=46`，可直接打开原始披露第 46 页；
- 逐条核验：`ADMIT` / `native-pdf-cell-literal-reviewer-v1` /
  `LITERAL_CELL_AND_HEADING_SOURCE_CHECK_ONLY`；
- 发布范围：`FACTS_ONLY`，`financial_semantic_review = NOT_PERFORMED`；
- 未发布：`PERIOD_COMPARISON`、`CROSS_ENTITY_COMPARISON`、`ANALYST_INFERENCE` 等；
- 顶部标注「本地开发预览 · 非对外发布」。

## 5. 失败情形（都应不显示任何金额）

```bash
# 文档缺失
FRP_LOCAL_SOURCE_PDF_600760=/tmp/absent.pdf   # 重启后端 → 页面显示“未取得可核验的披露事实”，API 返回 503

# 文档被篡改（哈希不符）
cp data/raw/600760/2026H1/source.pdf /tmp/altered.pdf
printf '\xff' | dd of=/tmp/altered.pdf bs=1 seek=2048 conv=notrunc
# 指向 /tmp/altered.pdf 重启后端 → 同样 503，且不泄露路径或哈希

# 未授权访问
# 不设置 token 或 token 少于 32 字符启动前端 → 页面显示“本报告未开放”
```

## 6. 自动化检查

```bash
cd services/api && ../../.venv/bin/python -m pytest -q
cd apps/web && node --test src/app/research/lib/dev-access.test.ts
```
