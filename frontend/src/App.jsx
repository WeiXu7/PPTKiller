import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArchiveBoxIcon as ArchiveBox, ArrowRight, BookOpenText, CaretDown, Check,
  ClockCounterClockwise, DownloadSimple, FilePdf, Folder, GearSix, House,
  ImageSquare, MagnifyingGlass, PaperPlaneTilt, PencilSimple, Plus,
  PresentationChart, ShareNetwork, SignOut, Sparkle, SpinnerGap, UploadSimple,
  UserCircle, WarningCircle,
} from "@phosphor-icons/react";
import { api, downloadExport, getToken, protectedBlobUrl, setToken } from "./api";

const STEP_DEFINITIONS = [
  ["brief", "理解需求（理解简报）", "提取主题、受众、目标与交付约束"],
  ["parse", "解析上传内容（文档与图片）", "抽取事实、表格、图片描述与可引用信息"],
  ["research", "搜索网络与学术文献", "检索可追溯网页资料、论文与 DOI"],
  ["verify", "验证与筛选引用来源", "去重并校验作者、年份、期刊与链接"],
  ["images", "查找与筛选图片素材", "保留作者、来源和授权信息"],
  ["outline", "构建演示大纲", "将论点、证据和图片映射到每一页"],
  ["slides", "生成演示文稿（幻灯片）", "按主题系统生成可编辑页面"],
  ["notes", "生成演讲备注（可选）", "逐页生成讲述目标、转场与时间建议"],
  ["review", "最终检查与一致性优化", "检查引用、叙事、版式与内容一致性"],
  ["export", "导出与交付", "输出可编辑 PPTX 与引用清单"],
];

const LAYOUT_OPTIONS = [
  ["cover", "封面"],
  ["image_split", "图文分栏"],
  ["statement", "核心观点"],
  ["two_column", "双栏"],
  ["process", "流程"],
  ["architecture", "架构图"],
  ["evidence", "证据"],
  ["summary", "总结"],
  ["content", "内容"],
  ["data", "数据"],
  ["case", "案例"],
];

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function payloadChips(key, payload = {}) {
  if (key === "parse") {
    const summary = [
      `${payload.count || 0} 个文件`,
      `${payload.sections || 0} 个区块`,
      `${payload.tables || 0} 个表格`,
    ];
    if (payload.ocr_required) summary.push(`${payload.ocr_required} 个需 OCR`);
    return summary;
  }
  if (key === "research") {
    if (!payload.configured) return ["等待配置检索服务"];
    return [`检索 ${payload.found || 0} 条`, `学术文献 ${payload.peer_reviewed || 0} 条`];
  }
  if (key === "verify") return [`已验证 ${payload.verified || 0} 条`, `DOI ${payload.doi_checked || 0} 条`];
  if (key === "images") return [`找到 ${payload.found || 0} 张`, `筛选 ${payload.selected || 0} 张`];
  if (key === "outline") return (payload.slides || []).slice(0, 6).map((slide) => slide.title);
  return [];
}

function sessionToSteps(session) {
  if (!session) return STEP_DEFINITIONS.map(([key, title, detail]) => ({ key, title, detail, state: "waiting" }));
  const events = new Map((session.events || []).filter((event) => STEP_DEFINITIONS.some(([key]) => key === event.step_key)).map((event) => [event.step_key, event]));
  return STEP_DEFINITIONS.map(([key, title, fallbackDetail], index) => {
    const event = events.get(key);
    let state = event ? "done" : "waiting";
    if (session.status === "waiting_approval" && index === session.current_step) state = "approval";
    else if (session.status === "running" && index === session.current_step) state = "active";
    const payload = event?.payload || session.artifacts?.[key] || {};
    return {
      key,
      title,
      detail: payload.note || event?.detail || fallbackDetail,
      state,
      chips: payloadChips(key, payload),
      progress: state === "active" ? 60 : null,
    };
  });
}

function Logo() {
  return <div className="logo"><span className="logoMark">P</span><b>PPTKiller</b></div>;
}

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = mode === "register"
        ? await api.register(form)
        : await api.login({ email: form.email, password: form.password });
      setToken(result.access_token);
      onAuthenticated(result.user);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function enterDemo() {
    setBusy(true);
    setError("");
    const credentials = { email: "demo@pptkiller.com", password: "pptkiller-demo", name: "演示用户" };
    try {
      let result;
      try {
        result = await api.register(credentials);
      } catch (requestError) {
        if (requestError.status !== 409) throw requestError;
        result = await api.login(credentials);
      }
      setToken(result.access_token);
      onAuthenticated(result.user);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="authPage">
      <section className="authBrand">
        <Logo />
        <div>
          <span className="authEyebrow">PROFESSIONAL PRESENTATION AGENT</span>
          <h1>从资料到可交付演示，<br />每一步都可检查。</h1>
          <p>真实文献引用、图片来源、人工审批和可编辑 PPTX，统一在透明的 Agent 工作流中完成。</p>
        </div>
        <div className="authSteps">
          <span><Check weight="bold" /> 资料与图片解析</span>
          <span><Check weight="bold" /> 文献检索和引用验证</span>
          <span><Check weight="bold" /> 逐页演讲稿与 PPTX 导出</span>
        </div>
      </section>
      <section className="authPanel">
        <div className="authCard">
          <h2>{mode === "login" ? "登录 PPTKiller" : "创建账户"}</h2>
          <p>{mode === "login" ? "继续管理你的项目和历史会话。" : "开始创建第一份可追溯的演示文稿。"}</p>
          <form onSubmit={submit}>
            {mode === "register" && <label>姓名<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="你的姓名" /></label>}
            <label>邮箱<input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="name@example.com" /></label>
            <label>密码<input required minLength={8} type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="至少 8 位" /></label>
            {error && <div className="formError"><WarningCircle />{error}</div>}
            <button className="authSubmit" disabled={busy}>{busy ? <SpinnerGap className="spin" /> : null}{mode === "login" ? "登录" : "注册并进入"}</button>
          </form>
          <button className="demoButton" disabled={busy} onClick={enterDemo}>一键进入演示账户</button>
          <button className="authSwitch" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
            {mode === "login" ? "没有账户？立即注册" : "已有账户？返回登录"}
          </button>
        </div>
      </section>
    </main>
  );
}

function Sidebar({ projects, activeProjectId, onSelect, onNewProject, user, onLogout }) {
  return (
    <aside className="sidebar">
      <div className="sideTop">
        <Logo />
        <button className="newProject" onClick={onNewProject}><Plus weight="bold" /> 新建项目</button>
        <nav>
          <button><House /> 首页</button>
          <button className="selected"><Folder weight="fill" /> 项目</button>
          <button><PresentationChart /> 模板中心</button>
          <button><BookOpenText /> 知识库</button>
          <button><Sparkle /> 智能体设置</button>
        </nav>
      </div>
      <section className="sideSection projectList">
        <div className="sectionLabel">最近项目 <Plus /></div>
        {projects.length === 0 && <p className="sideEmpty">还没有项目</p>}
        {projects.map((project) => (
          <button onClick={() => onSelect(project)} className={`projectRow ${project.id === activeProjectId ? "current" : ""}`} key={project.id}>
            <Folder /><span>{project.title}<small>{formatTime(project.updated_at)} · {project.status}</small></span>
          </button>
        ))}
      </section>
      <section className="sideSection conversations">
        <div className="sectionLabel">会话记录 <MagnifyingGlass /></div>
        {projects.slice(0, 4).map((project) => (
          <button onClick={() => onSelect(project)} className="projectRow" key={`session-${project.id}`}>
            <ClockCounterClockwise /><span>{project.title}<small>{formatTime(project.updated_at)}</small></span>
          </button>
        ))}
      </section>
      <div className="user">
        <div className="avatar">{user?.name?.slice(0, 1) || "用"}</div>
        <span><b>{user?.name || "用户"} <em>专业版</em></b><small>{user?.email}</small></span>
        <button className="iconButton" title="退出登录" onClick={onLogout}><SignOut /></button>
      </div>
    </aside>
  );
}

function StepIcon({ state, index }) {
  if (state === "done") return <span className="stepIcon done"><Check weight="bold" /></span>;
  if (state === "active") return <span className="stepIcon active"><span /></span>;
  if (state === "approval") return <span className="stepIcon approval"><UserCircle weight="fill" /></span>;
  return <span className="stepIcon waiting">{index + 1}</span>;
}

function Timeline({ steps, busy, onApprove, onRevise }) {
  return (
    <div className="timeline">
      {steps.map((step, index) => (
        <article className={`step ${step.state}`} key={step.key}>
          <div className="rail"><StepIcon state={step.state} index={index} /></div>
          <div className="stepBody">
            <header>
              <div><span className="stepNumber">{index + 1}</span><h3>{step.title}</h3></div>
              <span className={`status ${step.state}`}>{step.state === "done" ? "已完成" : step.state === "active" ? "进行中" : step.state === "approval" ? "需审核" : "等待中"}</span>
            </header>
            <p>{step.detail}</p>
            {step.chips?.length > 0 && <div className="chips">{step.chips.map((chip) => <span key={chip}>{chip}</span>)}</div>}
            {step.progress && <div className="progressRow"><div className="progress"><i style={{ width: `${step.progress}%` }} /></div><span>Agent 正在执行</span></div>}
            {step.state === "approval" && (
              <div className="approvalActions">
                <button disabled={busy} onClick={onRevise}>请求修改</button>
                <button disabled={busy} className="primary" onClick={onApprove}>{busy && <SpinnerGap className="spin" />}通过并继续</button>
              </div>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

function MiniSlide({ index, active, title, thumbnail, onClick }) {
  return (
    <button onClick={onClick} className={`miniSlide ${active ? "active" : ""}`}>
      <span>{index + 1}</span>
      <div>
        {thumbnail ? <img src={thumbnail} alt={`${title} 缩略图`} /> : <><b>{title}</b><i /><i /><i /></>}
      </div>
    </button>
  );
}

function DraftSlide({ project, slide }) {
  const bullets = (slide?.bullets || []).slice(0, 4);
  const modules = (slide?.diagram_modules || []).slice(0, 5);
  const layout = slide?.layout || "content";
  return (
    <div className={`mainSlide templateDraft layout-${layout}`}>
      <span className="eyebrow">CONSULTING TEMPLATE · DRAFT</span>
      <h1>{slide?.title || project?.title}</h1>
      <h2>{slide?.key_message || project?.topic || "专业演示文稿"}</h2>
      {layout === "architecture" && modules.length > 0 ? (
        <div className="draftArchitecture">
          {modules.map((module, index) => (
            <div className="draftModule" key={module.id || module.label}>
              <b>{String(index + 1).padStart(2, "0")}</b>
              <strong>{module.label}</strong>
              {(module.children || []).slice(0, 2).map((child) => <span key={child.label}>{child.label}</span>)}
            </div>
          ))}
        </div>
      ) : (
        <ul className="draftBullets">{bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}</ul>
      )}
      <footer>{slide?.design_template || "consulting-default"}　·　{project?.slide_count || 0} 页</footer>
    </div>
  );
}

function Preview({ project, session, activeSlide, setActiveSlide, onOpenEditor, onDownload }) {
  const outline = session?.artifacts?.outline?.slides || [{ title: project?.title || "等待生成大纲" }];
  const selected = outline[activeSlide] || outline[0];
  const [exportArtifact, setExportArtifact] = useState(null);
  const [thumbnails, setThumbnails] = useState({});
  const [montageUrl, setMontageUrl] = useState("");
  const [exportPreviewState, setExportPreviewState] = useState("idle");
  const exportRevision = session?.artifacts?._export_revision || "";
  const research = session?.artifacts?.research || {};
  const verify = session?.artifacts?.verify || {};
  const citations = verify.citations || research.citations || [];
  const quality = verify.quality_summary || {};
  const images = session?.artifacts?.images?.items || [];
  const selectedImage = images[activeSlide % Math.max(images.length, 1)];
  const selectedThumb = thumbnails[activeSlide + 1];
  const outlineTemplate = session?.artifacts?.outline?.design_template;
  const visibleTemplate = exportArtifact?.design_template || outlineTemplate || "consulting-default";

  useEffect(() => {
    let cancelled = false;
    let urls = [];
    let montageObjectUrl = "";
    setExportArtifact(null);
    setThumbnails({});
    setMontageUrl("");
    setExportPreviewState(session?.status === "completed" ? "loading" : "idle");
    if (!session || session.status !== "completed") return undefined;
    (async () => {
      try {
        const artifact = await api.exportManifest(session.id);
        const pairs = await Promise.all(
          (artifact.slides || []).map(async (slide) => {
            const url = await protectedBlobUrl(slide.thumbnail_url);
            urls.push(url);
            return [slide.number, url];
          })
        );
        if (artifact.montage_url) {
          montageObjectUrl = await protectedBlobUrl(artifact.montage_url);
          urls.push(montageObjectUrl);
        }
        if (!cancelled) {
          setExportArtifact(artifact);
          setThumbnails(Object.fromEntries(pairs));
          setMontageUrl(montageObjectUrl);
          setExportPreviewState("ready");
        }
      } catch {
        if (!cancelled) setExportPreviewState("failed");
      }
    })();
    return () => {
      cancelled = true;
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [session?.id, session?.status, exportRevision]);

  return (
    <section className="preview">
      <div className="previewTabs">
        <button className="active">演示预览</button>
        <button>大纲视图</button>
        <span className={`exportBadge ${exportPreviewState}`}>
          {exportPreviewState === "loading" ? "正在渲染导出预览" : exportPreviewState === "ready" ? `真实 PPT 预览 · ${visibleTemplate}` : exportPreviewState === "failed" ? "预览生成失败" : `模板草稿 · ${visibleTemplate}`}
        </span>
      </div>
      <div className="previewWorkspace">
        <div className="filmstrip">
          {outline.slice(0, 12).map((slide, index) => (
            <MiniSlide
              key={`${slide.number}-${slide.title}`}
              index={index}
              title={slide.title}
              thumbnail={thumbnails[index + 1]}
              active={activeSlide === index}
              onClick={() => setActiveSlide(index)}
            />
          ))}
        </div>
        <div className="slideDetail">
          {selectedThumb ? (
            <div className="renderedSlide"><img src={selectedThumb} alt={`${selected?.title || project?.title} 渲染预览`} /></div>
          ) : (
            <DraftSlide project={project} slide={selected} />
          )}
          <div className="summaryBox">
            <header><h4>当前生成状态</h4><button disabled={!session?.artifacts?.outline?.slides?.length} onClick={onOpenEditor}><PencilSimple /> 编辑本页</button></header>
            <ul>
              <li>项目：{project?.title}</li>
              <li>会话状态：{session?.status || "尚未启动"}</li>
              <li>大纲页数：{session?.artifacts?.outline?.target_count || project?.slide_count || 0}</li>
              <li>模板：{visibleTemplate}{exportArtifact?.template_version ? ` / v${exportArtifact.template_version}` : ""}</li>
              <li>{exportArtifact ? `已生成 ${exportArtifact.slide_count} 页真实导出预览` : "可编辑 PPTX 将在流程完成后导出"}</li>
            </ul>
          </div>
          <div className="qaPanel">
            <header><h4>导出 QA</h4><span className={`qaStatus ${exportArtifact?.file_status || exportPreviewState}`}>{exportArtifact?.file_status === "ready" ? "文件就绪" : exportPreviewState === "failed" ? "生成失败" : exportPreviewState === "loading" ? "检查中" : "等待导出"}</span></header>
            <dl>
              <div><dt>导出时间</dt><dd>{exportArtifact ? new Date(exportArtifact.created_at).toLocaleString("zh-CN") : "等待完成"}</dd></div>
              <div><dt>页数</dt><dd>{exportArtifact?.slide_count || session?.artifacts?.outline?.target_count || project?.slide_count || 0}</dd></div>
              <div><dt>文件</dt><dd>{exportArtifact?.pptx_size_bytes ? `${Math.round(exportArtifact.pptx_size_bytes / 1024)} KB` : "未生成"}</dd></div>
            </dl>
            {exportArtifact?.warnings?.length ? (
              <ul className="qaWarnings">{exportArtifact.warnings.slice(0, 4).map((warning) => <li className={warning.severity} key={`${warning.code}-${warning.slide_number || "deck"}`}><WarningCircle />{warning.message}</li>)}</ul>
            ) : <p className="qaClean">暂无导出警告</p>}
            <div className="qaActions">
              <button disabled={!exportArtifact} onClick={onDownload}><DownloadSimple /> 下载 PPTX</button>
              <a className={!montageUrl ? "disabled" : ""} href={montageUrl || undefined} target="_blank" rel="noreferrer"><PresentationChart /> 查看总览图</a>
            </div>
          </div>
          <div className="sourceBox">
            <header><h4>资料与引用</h4><span>{verify.verified ? `已验证 ${verify.verified}` : "等待检索"}</span></header>
            {verify.quality_summary && <div className="qualityRow"><span>论文 {quality.academic_paper || 0}</span><span>报告 {quality.industry_report || 0}</span><span>新闻 {quality.news || 0}</span><span>低可信 {quality.low || 0}</span></div>}
            <ol>
              {citations.length > 0 ? citations.slice(0, 3).map((citation, index) => (
                <li key={citation.doi || citation.url || citation.title}>
                  <b>{index + 1}</b>
                  <a href={citation.url} target="_blank" rel="noreferrer">{citation.title}</a>
                  <em>{citation.quality_tier === "high" ? "高" : citation.quality_tier === "low" ? "低" : citation.doi ? "DOI" : "中"}</em>
                </li>
              )) : <li><b>1</b><span>{research.note || "等待真实文献检索结果。"}</span><em>来源</em></li>}
            </ol>
            <button>共 {citations.length} 条引用，导出时随页面保留 <ArrowRight /></button>
          </div>
          <div className="imageSource">
            {selectedImage?.thumb ? <img src={selectedImage.thumb} alt={selectedImage.description || "检索图片"} /> : <ImageSquare size={28} />}
            <span><b>图片来源与授权</b><small>{selectedImage ? `${selectedImage.author} · Unsplash` : session?.artifacts?.images?.note || "等待图片检索结果"}</small></span>
            {selectedImage?.source_url && <a href={selectedImage.source_url} target="_blank" rel="noreferrer">查看来源</a>}
          </div>
        </div>
      </div>
    </section>
  );
}

function SlideEditor({ project, session, activeSlide, busy, onClose, onSave, onSaveImage }) {
  const slides = session?.artifacts?.outline?.slides || [];
  const selected = slides[activeSlide] || slides[0];
  const fileRef = useRef(null);
  const [form, setForm] = useState({
    title: "",
    layout: "content",
    bullets: "",
    key_message: "",
    speaker_notes: "",
  });
  const [imageQuery, setImageQuery] = useState("");
  const [imageResults, setImageResults] = useState([]);
  const [imageBusy, setImageBusy] = useState(false);
  const [imageError, setImageError] = useState("");

  useEffect(() => {
    setForm({
      title: selected?.title || "",
      layout: selected?.layout || selected?.type || "content",
      bullets: (selected?.bullets || []).join("\n"),
      key_message: selected?.key_message || "",
      speaker_notes: selected?.speaker_notes || "",
    });
    setImageQuery(selected?.image_assignment?.query || selected?.image_query || selected?.title || "");
    setImageResults([]);
    setImageError("");
  }, [selected?.number, selected?.title]);

  if (!selected) return null;

  function submit(event) {
    event.preventDefault();
    onSave(selected.number || activeSlide + 1, {
      title: form.title,
      layout: form.layout,
      bullets: form.bullets.split("\n").map((item) => item.trim()).filter(Boolean),
      key_message: form.key_message,
      speaker_notes: form.speaker_notes,
    });
  }

  async function searchImages() {
    setImageBusy(true);
    setImageError("");
    try {
      setImageResults(await api.searchImages(imageQuery || selected.title, 6));
    } catch (error) {
      setImageError(error.message);
    } finally {
      setImageBusy(false);
    }
  }

  async function uploadImage(event) {
    const file = event.target.files?.[0];
    if (!file || !project) return;
    setImageBusy(true);
    setImageError("");
    try {
      const asset = await api.upload(project.id, file, `第 ${selected.number || activeSlide + 1} 页图片`);
      await onSaveImage(selected.number || activeSlide + 1, { mode: "upload", asset_id: asset.id });
    } catch (error) {
      setImageError(error.message);
    } finally {
      setImageBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const assignment = selected.image_assignment || { mode: "auto" };
  const imageModeLabel = assignment.mode === "none" ? "不使用图片" : assignment.mode === "search" ? "检索图片" : assignment.mode === "upload" ? "上传图片" : "自动轮换";

  return (
    <aside className="editorPanel">
      <form onSubmit={submit}>
        <header>
          <div><span>第 {selected.number || activeSlide + 1} 页</span><h3>逐页编辑器</h3></div>
          <button type="button" onClick={onClose}>关闭</button>
        </header>
        <label>标题<input required maxLength={240} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
        <div className="editorGrid">
          <label>版式<select value={form.layout} onChange={(event) => setForm({ ...form, layout: event.target.value })}>{LAYOUT_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label>核心结论<input maxLength={500} value={form.key_message} onChange={(event) => setForm({ ...form, key_message: event.target.value })} /></label>
        </div>
        <label>要点<textarea className="bulletsInput" value={form.bullets} onChange={(event) => setForm({ ...form, bullets: event.target.value })} /></label>
        <label>讲稿备注<textarea value={form.speaker_notes} onChange={(event) => setForm({ ...form, speaker_notes: event.target.value })} /></label>
        <section className="imageEditor">
          <header><div><span>当前图片模式</span><b>{imageModeLabel}</b></div><button type="button" disabled={busy || imageBusy} onClick={() => onSaveImage(selected.number || activeSlide + 1, { mode: "auto" })}>自动</button><button type="button" disabled={busy || imageBusy} onClick={() => onSaveImage(selected.number || activeSlide + 1, { mode: "none" })}>不用图片</button></header>
          <div className="imageSearchRow"><input value={imageQuery} onChange={(event) => setImageQuery(event.target.value)} placeholder="搜索图片关键词" /><button type="button" disabled={busy || imageBusy} onClick={searchImages}>{imageBusy ? <SpinnerGap className="spin" /> : <MagnifyingGlass />}检索</button></div>
          {imageError && <p className="imageError">{imageError}</p>}
          {imageResults.length > 0 && <div className="imageResults">{imageResults.map((image) => (
            <button type="button" key={image.id || image.url} disabled={busy || imageBusy} onClick={() => onSaveImage(selected.number || activeSlide + 1, { mode: "search", query: imageQuery, image })}>
              <img src={image.thumb || image.url} alt={image.description || "检索图片"} />
              <span>{image.author || "Unknown"}</span>
            </button>
          ))}</div>}
          <input ref={fileRef} className="fileInput" type="file" accept="image/*" onChange={uploadImage} />
          <button type="button" className="uploadImageButton" disabled={busy || imageBusy} onClick={() => fileRef.current?.click()}><UploadSimple /> 上传并用于本页</button>
        </section>
        <footer>
          <button type="button" disabled={busy} onClick={onClose}>取消</button>
          <button className="primary" disabled={busy}>{busy && <SpinnerGap className="spin" />}保存本页</button>
        </footer>
      </form>
    </aside>
  );
}

function Composer({ disabled, onSend }) {
  const [text, setText] = useState("");
  const submit = () => { if (text.trim() && !disabled) { onSend(text); setText(""); } };
  return (
    <div className={`composer ${disabled ? "disabled" : ""}`}>
      <textarea disabled={disabled} value={text} onChange={(event) => setText(event.target.value)} placeholder={disabled ? "创建项目后即可向 Agent 提交修改指令" : "告诉 PPTKiller 你想如何修改或继续…"} />
      <div><span><button disabled={disabled}><ArchiveBox /> 调整结构</button><button disabled={disabled}><Sparkle /> 扩充内容</button><button disabled={disabled}><ImageSquare /> 更换案例</button></span><button disabled={disabled} className="send" onClick={submit}><PaperPlaneTilt weight="fill" /></button></div>
    </div>
  );
}

function NewProjectModal({ busy, onClose, onCreate }) {
  const [title, setTitle] = useState("人工智能如何改变知识工作");
  const [topic, setTopic] = useState("研究行业现状、影响与行动建议");
  const [slideCount, setSlideCount] = useState("15");
  const [notes, setNotes] = useState("true");
  const [files, setFiles] = useState([]);
  const inputRef = useRef(null);
  const submit = (event) => {
    event.preventDefault();
    onCreate({ title, topic, slide_count: Number(slideCount), speaker_notes_enabled: notes === "true", files });
  };
  return (
    <div className="modalBackdrop" onMouseDown={busy ? undefined : onClose}>
      <form className="modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <span className="modalIcon"><Sparkle weight="fill" /></span><h2>创建新的 PPT Agent 项目</h2><p>创建后会上传资料并运行到第一个人工审批节点。</p>
        <label>项目标题<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
        <label className="modalTopic">研究主题与要求<textarea required value={topic} onChange={(event) => setTopic(event.target.value)} /></label>
        <div className="modalGrid">
          <label>目标页数<select value={slideCount} onChange={(event) => setSlideCount(event.target.value)}><option>10</option><option>15</option><option>20</option></select></label>
          <label>演讲稿<select value={notes} onChange={(event) => setNotes(event.target.value)}><option value="true">生成</option><option value="false">不生成</option></select></label>
        </div>
        <input ref={inputRef} className="fileInput" type="file" multiple accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.txt,.md,image/*" onChange={(event) => setFiles(Array.from(event.target.files || []))} />
        <button type="button" className="upload" onClick={() => inputRef.current?.click()}><UploadSimple size={30} /><b>{files.length ? `已选择 ${files.length} 个文件` : "选择资料或图片"}</b><small>{files.length ? files.map((file) => file.name).join("、") : "单个文件不超过 50MB"}</small></button>
        <footer><button type="button" disabled={busy} onClick={onClose}>取消</button><button disabled={busy} className="primary">{busy && <SpinnerGap className="spin" />}创建并开始</button></footer>
      </form>
    </div>
  );
}

function EmptyWorkspace({ onCreate }) {
  return <section className="emptyWorkspace"><span><PresentationChart weight="duotone" /></span><h2>创建第一份专业演示</h2><p>上传资料，PPTKiller 会在关键步骤等待你审核。</p><button onClick={onCreate}><Plus /> 新建项目</button></section>;
}

export function App() {
  const [user, setUser] = useState(null);
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [session, setSession] = useState(null);
  const [activeSlide, setActiveSlide] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [booting, setBooting] = useState(Boolean(getToken()));
  const steps = useMemo(() => sessionToSteps(session), [session]);
  const completed = steps.filter((step) => step.state === "done").length;

  const notify = (message) => { setToast(message); window.setTimeout(() => setToast(""), 3000); };

  async function loadProject(selectedProject) {
    setProject(selectedProject);
    setActiveSlide(0);
    try {
      const sessions = await api.sessions(selectedProject.id);
      setSession(sessions[0] || null);
    } catch (error) {
      notify(error.message);
    }
  }

  async function loadProjects(preferredId) {
    const items = await api.projects();
    setProjects(items);
    const selected = items.find((item) => item.id === preferredId) || items[0] || null;
    if (selected) await loadProject(selected);
    else { setProject(null); setSession(null); }
  }

  useEffect(() => {
    if (!getToken()) return;
    (async () => {
      try {
        const currentUser = await api.me();
        setUser(currentUser);
        await loadProjects();
      } catch {
        setToken(null);
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  async function authenticated(currentUser) {
    setUser(currentUser);
    setBooting(true);
    try { await loadProjects(); } finally { setBooting(false); }
  }

  async function createProject(payload) {
    setBusy(true);
    try {
      const created = await api.createProject(payload);
      for (const file of payload.files) await api.upload(created.id, file);
      setModalOpen(false);
      setProject(created);
      setProjects((items) => [created, ...items.filter((item) => item.id !== created.id)]);
      setSession(null);
      notify(`项目已创建，${payload.files.length} 个文件上传完成，Agent 正在启动`);
      const started = await api.startSession(created.id, {
        audience: "专业听众", tone: "专业、清晰", language: "中文",
        instructions: payload.topic, require_approval: true,
      });
      await loadProjects(created.id);
      setSession(started);
      notify("Agent 已运行到第一个人工审批节点");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!session) return;
    setBusy(true);
    try {
      const updated = await api.approve(session.id, { approved: true, feedback: "" });
      setSession(updated);
      await loadProjects(project.id);
      setSession(updated);
      notify(updated.status === "completed" ? "Agent 流程已完成，可以导出 PPTX" : "审批通过，已运行到下一个审批节点");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function revise(instruction = "请根据我的要求调整当前结果") {
    if (!session) return;
    setBusy(true);
    try {
      const updated = await api.revise(session.id, instruction);
      setSession(updated);
      notify("修改指令已写入当前 Agent 会话");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function exportPpt() {
    if (!session) return;
    if (session.status !== "completed") return notify("请先通过全部人工审批节点");
    try {
      await downloadExport(session.id, project.title);
      notify("PPTX 已开始下载");
    } catch (error) {
      notify(error.message);
    }
  }

  async function saveSlide(slideNumber, payload) {
    if (!session) return;
    setBusy(true);
    try {
      const updated = await api.updateSlide(session.id, slideNumber, payload);
      setSession(updated);
      notify("本页已保存，后续导出会使用最新内容");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveSlideImage(slideNumber, payload) {
    if (!session) return;
    setBusy(true);
    try {
      const updated = await api.updateSlideImage(session.id, slideNumber, payload);
      setSession(updated);
      notify("本页图片选择已保存，导出会按页应用");
    } catch (error) {
      notify(error.message);
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken(null);
    setUser(null);
    setProjects([]);
    setProject(null);
    setSession(null);
  }

  if (booting) return <div className="bootScreen"><Logo /><SpinnerGap className="spin" /><span>正在连接 PPTKiller…</span></div>;
  if (!user) return <AuthScreen onAuthenticated={authenticated} />;

  return (
    <div className="app">
      <Sidebar projects={projects} activeProjectId={project?.id} onSelect={loadProject} onNewProject={() => setModalOpen(true)} user={user} onLogout={logout} />
      <main className="main">
        {project ? <>
          <header className="topbar">
            <div><h2>{project.title} <PencilSimple /></h2><span>Agent：{session?.status || "未启动"}　·　共 10 个步骤　<b>{completed} 已完成</b></span></div>
            <div className="topActions"><button onClick={() => notify("团队分享将在后续版本接入")}><ShareNetwork /> 分享</button><button onClick={exportPpt}><DownloadSimple /> 导出PPT</button><button className="primary" disabled={!session?.artifacts?.outline?.slides?.length} onClick={() => setEditorOpen(true)}><PencilSimple /> 打开编辑器 <CaretDown /></button></div>
          </header>
          <div className="content"><section className="runPanel"><Timeline steps={steps} busy={busy} onApprove={approve} onRevise={() => revise()} /></section><Preview project={project} session={session} activeSlide={activeSlide} setActiveSlide={setActiveSlide} onOpenEditor={() => setEditorOpen(true)} onDownload={exportPpt} /></div>
          {editorOpen && <SlideEditor project={project} session={session} activeSlide={activeSlide} busy={busy} onClose={() => setEditorOpen(false)} onSave={saveSlide} onSaveImage={saveSlideImage} />}
          <Composer disabled={!session || busy} onSend={revise} />
        </> : <EmptyWorkspace onCreate={() => setModalOpen(true)} />}
      </main>
      {modalOpen && <NewProjectModal busy={busy} onClose={() => setModalOpen(false)} onCreate={createProject} />}
      {toast && <div className="toast"><Check weight="bold" />{toast}</div>}
    </div>
  );
}
