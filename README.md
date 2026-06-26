# PPTKiller

PPTKiller 是一个前后端分离的专业 PPT Agent MVP。它围绕可观察、可暂停、可审批的 Harness 工作流组织资料解析、联网研究、真实文献验证、图片检索、大纲生成、幻灯片生成和演讲稿生成。

## 技术栈

- Web：React 19、Vite、Phosphor Icons
- API：FastAPI、Pydantic v2、SQLAlchemy、SQLite
- Agent：异步 Harness，能力通过 provider 接口注入；外部服务失败会记录为 artifact 并安全降级
- 模型：DeepSeek OpenAI-compatible API，默认模型名 `deepseek-v4-flash`
- PPT：`@oai/artifact-tool` 专业版式引擎，输出 PPTX、逐页 PNG、布局检查结果与演讲者备注
- 资料解析：pypdf、python-docx、python-pptx、openpyxl、xlrd、Pillow
- 可选基础设施：Redis（任务事件与缓存接口预留）

## 本地运行

```bash
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

另开终端：

```bash
cd frontend
npm install
npm run dev
```

前端配置 `VITE_API_URL=http://127.0.0.1:8000/api/v1` 后连接 API。

## 第三方服务与 Key

- `DEEPSEEK_API_KEY`：必需，用于真实模型生成。
- `TAVILY_API_KEY`：推荐，用于网页资料检索。
- `SEMANTIC_SCHOLAR_API_KEY`：可选，提高学术检索额度；无 Key 时可使用 Crossref。
- `UNSPLASH_ACCESS_KEY` 或 `PEXELS_API_KEY`：推荐，用于可授权图片检索。
- `REDIS_URL`：可选，用于生产环境事件流、任务队列和缓存。

当前 Harness 已实际编排 Tavily、Crossref、Unsplash 和 DeepSeek。没有 Key 或服务调用失败时，系统会保留错误信息并使用本地可编辑大纲降级，不伪造联网结果。

上传资料会优先使用原生解析：

- PDF：逐页文本、图片数量、扫描页检测
- Word：段落样式、表格、内嵌图片
- PowerPoint：逐页文本、表格、备注、图片
- Excel/CSV：工作表、行列与表格数据
- 图片：尺寸、格式，并标记需要视觉理解或 OCR

OCR 只作为无文本层页面和纯图片内容的后续兜底，不会对所有文件重复执行。

## 专业 PPT 导出

导出引擎会根据大纲自动选择封面、图文分栏、核心观点、双栏、流程、证据和总结等版式，并将真实文献引用、图片署名及可选演讲稿写入 PPTX。每次导出同时在 `backend/generated/<导出ID>/qa/` 生成逐页渲染图和布局 JSON；只有页数、渲染结果和文件完整性检查通过后才返回下载文件。

完成态会话还会生成受登录保护的导出 manifest 与缩略图 API：

- `GET /api/v1/sessions/{session_id}/export/manifest`
- `GET /api/v1/sessions/{session_id}/export/thumbnails/{slide_number}`
- `GET /api/v1/sessions/{session_id}/export/montage`

Web 工作台会在 Agent 完成后自动加载这些真实渲染缩略图，filmstrip 和主预览区显示的就是最终 PPTX 的页面效果；未完成时仍显示可编辑草稿预览。

## 设计资料与待办

- UI 设计图与对比截图位于 `docs/design/`。
- 当前未完成事项维护在 `todo.md`。

启动后访问 Swagger UI：`http://127.0.0.1:8000/docs`。
