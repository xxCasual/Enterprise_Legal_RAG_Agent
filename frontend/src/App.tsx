import {
  AlertTriangle,
  Bot,
  Building2,
  CheckCircle2,
  ClipboardCheck,
  FileArchive,
  FileText,
  Gauge,
  Gavel,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Scale,
  Send,
  ShieldAlert,
  Upload,
  XCircle
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  checkReady,
  checkHealth,
  decideReview,
  listDocuments,
  listPendingReviews,
  reviewContract,
  sendChat,
  uploadDocument
} from "./api";
import type {
  ChatResponse,
  ContractFinding,
  ContractReview,
  DocumentRecord,
  LoadingKey,
  PendingReviewRecord,
  ReadyResponse,
  ReviewDecision,
  ReviewDecisionResponse,
  RiskLevel,
  ToolTrace
} from "./types";

type ViewId = "chat" | "documents" | "contract" | "reviews" | "status";
type HealthState = "unknown" | "ok" | "bad";

const sampleContract =
  "合同期限为三年。试用期一年。工资另行约定。员工自愿放弃社保。甲方可随时解除合同且不支付经济补偿。";

const quickQueries = [
  { label: "试用期", query: "试用期最长多久？", icon: Gavel },
  { label: "制度工资日", query: "公司的工资发放日是什么时候？", icon: Building2 },
  { label: "合同社保", query: "请审查这份劳动合同：员工自愿放弃社保。", icon: ShieldAlert },
  { label: "范围外", query: "今天天气怎么样？", icon: AlertTriangle }
];

const navItems: Array<{ id: ViewId; label: string; icon: LucideIcon }> = [
  { id: "chat", label: "统一问答", icon: MessageSquareText },
  { id: "documents", label: "制度文档", icon: FileArchive },
  { id: "contract", label: "合同审查", icon: ClipboardCheck },
  { id: "reviews", label: "人工审批", icon: Scale },
  { id: "status", label: "系统状态", icon: Gauge }
];

function App() {
  const [activeView, setActiveView] = useState<ViewId>("chat");
  const [loading, setLoadingState] = useState<Record<LoadingKey, boolean>>({
    health: false,
    ready: false,
    chat: false,
    documents: false,
    upload: false,
    contract: false,
    reviews: false,
    approval: false
  });
  const [health, setHealth] = useState<HealthState>("unknown");
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [lastAction, setLastAction] = useState("等待操作");
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("试用期最长多久？");
  const [chatResult, setChatResult] = useState<ChatResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [contractText, setContractText] = useState(sampleContract);
  const [contractResult, setContractResult] = useState<ContractReview | null>(null);
  const [reviews, setReviews] = useState<PendingReviewRecord[]>([]);
  const [decisionResult, setDecisionResult] = useState<ReviewDecisionResponse | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const setLoading = useCallback((key: LoadingKey, value: boolean) => {
    setLoadingState((current) => ({ ...current, [key]: value }));
  }, []);

  const runHealth = useCallback(async () => {
    setLoading("health", true);
    setError(null);
    try {
      const payload = await checkHealth();
      setHealth(payload.status === "ok" ? "ok" : "bad");
      setLastAction(`健康检查：${payload.status}`);
    } catch (err) {
      setHealth("bad");
      setError(errorMessage(err));
      setLastAction("健康检查失败");
    } finally {
      setLoading("health", false);
    }
  }, [setLoading]);

  const runReady = useCallback(async () => {
    setLoading("ready", true);
    setError(null);
    try {
      const payload = await checkReady();
      setReady(payload);
      setLastAction(`生产依赖：${payload.status}`);
    } catch (err) {
      setReady(null);
      setError(errorMessage(err));
      setLastAction("生产依赖检查失败");
    } finally {
      setLoading("ready", false);
    }
  }, [setLoading]);

  const refreshDocuments = useCallback(async () => {
    setLoading("documents", true);
    setError(null);
    try {
      const payload = await listDocuments();
      setDocuments(payload.documents);
      setLastAction("制度文档已刷新");
    } catch (err) {
      setError(errorMessage(err));
      setLastAction("制度文档加载失败");
    } finally {
      setLoading("documents", false);
    }
  }, [setLoading]);

  const refreshReviews = useCallback(async () => {
    setLoading("reviews", true);
    setError(null);
    try {
      const payload = await listPendingReviews();
      setReviews(payload.reviews);
      setLastAction("审批队列已刷新");
    } catch (err) {
      setError(errorMessage(err));
      setLastAction("审批队列加载失败");
    } finally {
      setLoading("reviews", false);
    }
  }, [setLoading]);

  useEffect(() => {
    runHealth();
    runReady();
    refreshDocuments();
    refreshReviews();
  }, [refreshDocuments, refreshReviews, runHealth, runReady]);

  const runChat = async (forcedQuery?: string) => {
    const finalQuery = (forcedQuery ?? query).trim();
    if (!finalQuery) {
      setError("请输入问题");
      return;
    }
    setQuery(finalQuery);
    setLoading("chat", true);
    setError(null);
    try {
      const payload = await sendChat(finalQuery);
      setChatResult(payload);
      setLastAction("统一问答完成");
      if (payload.review_status === "pending_review") {
        await refreshReviews();
      }
    } catch (err) {
      setError(errorMessage(err));
      setLastAction("统一问答失败");
    } finally {
      setLoading("chat", false);
    }
  };

  const handleUpload = async () => {
    const file = fileInputRef.current?.files?.[0];
    if (!file) {
      setError("请选择制度文档");
      return;
    }
    setLoading("upload", true);
    setError(null);
    try {
      const record = await uploadDocument(file);
      setLastAction(`已上传：${record.file_name}`);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await refreshDocuments();
    } catch (err) {
      setError(errorMessage(err));
      setLastAction("制度文档上传失败");
    } finally {
      setLoading("upload", false);
    }
  };

  const runContractReview = async () => {
    const text = contractText.trim();
    if (!text) {
      setError("请输入合同文本");
      return;
    }
    setLoading("contract", true);
    setError(null);
    try {
      const payload = await reviewContract(text);
      setContractResult(payload);
      setLastAction("合同审查完成");
      if (payload.review_status === "pending_review") {
        await refreshReviews();
      }
    } catch (err) {
      setError(errorMessage(err));
      setLastAction("合同审查失败");
    } finally {
      setLoading("contract", false);
    }
  };

  const handleDecision = async (reviewId: string, decision: ReviewDecision) => {
    setLoading("approval", true);
    setError(null);
    try {
      const payload = await decideReview(reviewId, decision);
      setDecisionResult(payload);
      setLastAction(`审批结果：${payload.status}`);
      await refreshReviews();
    } catch (err) {
      setError(errorMessage(err));
      setLastAction("审批操作失败");
    } finally {
      setLoading("approval", false);
    }
  };

  const totalChunks = useMemo(
    () => documents.reduce((sum, doc) => sum + doc.chunk_count, 0),
    [documents]
  );
  const activeIndexingDocs = useMemo(
    () => documents.filter((doc) => doc.status === "pending" || doc.status === "indexing").length,
    [documents]
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Scale size={22} aria-hidden="true" />
          </div>
          <div>
            <h1>企业劳动合规控制台</h1>
            <p>{lastAction}</p>
          </div>
        </div>

        <nav className="nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={activeView === item.id ? "nav-item active" : "nav-item"}
              type="button"
              onClick={() => setActiveView(item.id)}
            >
              <item.icon size={18} aria-hidden="true" />
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-status">
          <StatusDot state={health} />
          <span>{health === "ok" ? "服务正常" : health === "bad" ? "服务异常" : "未检查"}</span>
          <IconButton
            label="刷新服务状态"
            icon={RefreshCw}
            loading={loading.health}
            onClick={runHealth}
          />
        </div>
      </aside>

      <main className="content">
        <header className="content-head">
          <div>
            <p className="eyebrow">Legal RAG Agent</p>
            <h2>{navItems.find((item) => item.id === activeView)?.label}</h2>
          </div>
          <div className="head-metrics">
            <Metric label="文档" value={documents.length} />
            <Metric label="Chunks" value={totalChunks} />
            <Metric label="索引中" value={activeIndexingDocs} tone={activeIndexingDocs ? "warn" : "neutral"} />
            <Metric label="待审" value={reviews.length} tone={reviews.length ? "warn" : "neutral"} />
          </div>
        </header>

        {error ? (
          <div className="alert" role="alert">
            <AlertTriangle size={18} aria-hidden="true" />
            <span>{error}</span>
          </div>
        ) : null}

        {activeView === "chat" ? (
          <ChatView
            query={query}
            setQuery={setQuery}
            result={chatResult}
            loading={loading.chat}
            onSubmit={() => runChat()}
            onQuickQuery={runChat}
          />
        ) : null}

        {activeView === "documents" ? (
          <DocumentsView
            documents={documents}
            loading={loading.documents || loading.upload}
            fileInputRef={fileInputRef}
            onRefresh={refreshDocuments}
            onUpload={handleUpload}
          />
        ) : null}

        {activeView === "contract" ? (
          <ContractView
            contractText={contractText}
            setContractText={setContractText}
            result={contractResult}
            loading={loading.contract}
            onSample={() => setContractText(sampleContract)}
            onReview={runContractReview}
          />
        ) : null}

        {activeView === "reviews" ? (
          <ReviewsView
            reviews={reviews}
            decisionResult={decisionResult}
            loading={loading.reviews || loading.approval}
            onRefresh={refreshReviews}
            onDecision={handleDecision}
          />
        ) : null}

        {activeView === "status" ? (
          <StatusView
            health={health}
            ready={ready}
            loading={loading.health}
            readyLoading={loading.ready}
            documents={documents}
            reviews={reviews}
            onRefreshHealth={runHealth}
            onRefreshReady={runReady}
            onRefreshDocuments={refreshDocuments}
            onRefreshReviews={refreshReviews}
          />
        ) : null}
      </main>
    </div>
  );
}

interface ChatViewProps {
  query: string;
  setQuery: (query: string) => void;
  result: ChatResponse | null;
  loading: boolean;
  onSubmit: () => void;
  onQuickQuery: (query: string) => void;
}

function ChatView({ query, setQuery, result, loading, onSubmit, onQuickQuery }: ChatViewProps) {
  return (
    <section className="workbench">
      <div className="input-panel">
        <div className="toolbar">
          <div className="quick-actions">
            {quickQueries.map((item) => (
              <button
                key={item.label}
                type="button"
                className="tool-button"
                onClick={() => onQuickQuery(item.query)}
              >
                <item.icon size={16} aria-hidden="true" />
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        </div>
        <textarea
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="输入法律问题、企业制度问题或合同审查请求"
          rows={7}
        />
        <div className="actions">
          <button className="primary" type="button" disabled={loading} onClick={onSubmit}>
            {loading ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <Send size={17} aria-hidden="true" />}
            <span>发送</span>
          </button>
        </div>
      </div>

      <div className="output-panel">
        {result ? <ChatResult result={result} /> : <EmptyState icon={Bot} title="暂无问答结果" />}
      </div>
    </section>
  );
}

function ChatResult({ result }: { result: ChatResponse }) {
  return (
    <div className="result-stack">
      <div className="answer-block">{result.answer || "无回答"}</div>
      <div className="meta-grid">
        <StatusPill label="intent" value={result.intent} />
        <StatusPill label="route" value={result.route} />
        <StatusPill label="type" value={result.result_type} />
        <StatusPill label="latency" value={`${result.latency}s`} />
        <RiskPill risk={result.risk_level} />
        <ReviewPill status={result.review_status} reviewId={result.review_id} />
      </div>
      <CitationList items={result.citations} />
      <ToolTraceList trace={result.tool_trace} />
      {result.contract_review ? <ContractReviewDetails review={result.contract_review} /> : null}
      <JsonDetails title="原始响应" payload={result} />
    </div>
  );
}

interface DocumentsViewProps {
  documents: DocumentRecord[];
  loading: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onRefresh: () => void;
  onUpload: () => void;
}

function DocumentsView({ documents, loading, fileInputRef, onRefresh, onUpload }: DocumentsViewProps) {
  return (
    <section className="split-layout">
      <div className="input-panel">
        <div className="section-head">
          <div>
            <h3>制度文档</h3>
            <p>{documents.length ? `${documents.length} 个文档` : "暂无文档"}</p>
          </div>
          <IconButton label="刷新制度文档" icon={RefreshCw} loading={loading} onClick={onRefresh} />
        </div>
        <div className="upload-box">
          <input ref={fileInputRef} type="file" accept=".txt,.md,.pdf,.docx" />
          <button className="primary" type="button" disabled={loading} onClick={onUpload}>
            {loading ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <Upload size={17} aria-hidden="true" />}
            <span>上传</span>
          </button>
        </div>
      </div>

      <div className="output-panel">
        {documents.length ? (
          <div className="list-stack">
            {documents.map((document) => (
              <DocumentItem key={document.doc_id} document={document} />
            ))}
          </div>
        ) : (
          <EmptyState icon={FileText} title="暂无制度文档" />
        )}
      </div>
    </section>
  );
}

function DocumentItem({ document }: { document: DocumentRecord }) {
  const statusTone = document.status === "ready" ? "ok" : document.status === "failed" ? "danger" : "warn";
  return (
    <article className="list-item">
      <div className={`item-icon ${statusTone}`}>
        <FileText size={18} aria-hidden="true" />
      </div>
      <div>
        <h4>{document.file_name}</h4>
        <div className="item-meta">
          <span>{document.source_type}</span>
          <span>{document.chunk_count} chunks</span>
          <span>{formatDate(document.created_at)}</span>
        </div>
        <div className="meta-grid document-status">
          <StatusPill label="status" value={document.status} tone={statusTone} />
          <StatusPill label="task" value={document.task_id} />
          <StatusPill label="indexed" value={document.indexed_at ? formatDate(document.indexed_at) : null} />
        </div>
        {document.error_message ? <p className="trace-error">{document.error_message}</p> : null}
      </div>
    </article>
  );
}

interface ContractViewProps {
  contractText: string;
  setContractText: (value: string) => void;
  result: ContractReview | null;
  loading: boolean;
  onSample: () => void;
  onReview: () => void;
}

function ContractView({
  contractText,
  setContractText,
  result,
  loading,
  onSample,
  onReview
}: ContractViewProps) {
  return (
    <section className="workbench">
      <div className="input-panel">
        <div className="toolbar right">
          <button type="button" className="tool-button" onClick={onSample}>
            <FileText size={16} aria-hidden="true" />
            <span>样例</span>
          </button>
        </div>
        <textarea
          value={contractText}
          onChange={(event) => setContractText(event.target.value)}
          placeholder="粘贴劳动合同文本"
          rows={12}
        />
        <div className="actions">
          <button className="primary" type="button" disabled={loading} onClick={onReview}>
            {loading ? <Loader2 className="spin" size={17} aria-hidden="true" /> : <ClipboardCheck size={17} aria-hidden="true" />}
            <span>审查合同</span>
          </button>
        </div>
      </div>

      <div className="output-panel">
        {result ? <ContractReviewDetails review={result} /> : <EmptyState icon={ClipboardCheck} title="暂无审查结果" />}
      </div>
    </section>
  );
}

interface ReviewsViewProps {
  reviews: PendingReviewRecord[];
  decisionResult: ReviewDecisionResponse | null;
  loading: boolean;
  onRefresh: () => void;
  onDecision: (reviewId: string, decision: ReviewDecision) => void;
}

function ReviewsView({ reviews, decisionResult, loading, onRefresh, onDecision }: ReviewsViewProps) {
  return (
    <section className="split-layout">
      <div className="input-panel">
        <div className="section-head">
          <div>
            <h3>待人工复核</h3>
            <p>{reviews.length ? `${reviews.length} 条记录` : "暂无待审记录"}</p>
          </div>
          <IconButton label="刷新审批队列" icon={RefreshCw} loading={loading} onClick={onRefresh} />
        </div>
        {decisionResult ? <DecisionResult result={decisionResult} /> : null}
      </div>

      <div className="output-panel">
        {reviews.length ? (
          <div className="list-stack">
            {reviews.map((review) => (
              <ReviewItem
                key={review.review_id}
                review={review}
                loading={loading}
                onDecision={onDecision}
              />
            ))}
          </div>
        ) : (
          <EmptyState icon={Scale} title="暂无待审批记录" />
        )}
      </div>
    </section>
  );
}

function ReviewItem({
  review,
  loading,
  onDecision
}: {
  review: PendingReviewRecord;
  loading: boolean;
  onDecision: (reviewId: string, decision: ReviewDecision) => void;
}) {
  return (
    <article className="list-item approval-item">
      <div className="item-icon warn">
        <ShieldAlert size={18} aria-hidden="true" />
      </div>
      <div>
        <h4>{review.review_id}</h4>
        <div className="item-meta">
          <span>{review.source_type}</span>
          <span>{review.status}</span>
          <span>{formatDate(review.created_at)}</span>
        </div>
        <PayloadPreview payload={review.payload} />
        <div className="row-actions">
          <button type="button" disabled={loading} onClick={() => onDecision(review.review_id, "approve")}>
            <CheckCircle2 size={16} aria-hidden="true" />
            <span>通过</span>
          </button>
          <button className="danger" type="button" disabled={loading} onClick={() => onDecision(review.review_id, "reject")}>
            <XCircle size={16} aria-hidden="true" />
            <span>拒绝</span>
          </button>
        </div>
      </div>
    </article>
  );
}

function DecisionResult({ result }: { result: ReviewDecisionResponse }) {
  return (
    <div className="decision-box">
      <div className="meta-grid">
        <StatusPill label="review_id" value={result.review_id} />
        <StatusPill label="status" value={result.status} tone={result.status === "approved" ? "ok" : "danger"} />
      </div>
      <p>{result.message}</p>
      {result.final_answer ? <JsonDetails title="审批结果" payload={result.final_answer} /> : null}
    </div>
  );
}

interface StatusViewProps {
  health: HealthState;
  ready: ReadyResponse | null;
  loading: boolean;
  readyLoading: boolean;
  documents: DocumentRecord[];
  reviews: PendingReviewRecord[];
  onRefreshHealth: () => void;
  onRefreshReady: () => void;
  onRefreshDocuments: () => void;
  onRefreshReviews: () => void;
}

function StatusView({
  health,
  ready,
  loading,
  readyLoading,
  documents,
  reviews,
  onRefreshHealth,
  onRefreshReady,
  onRefreshDocuments,
  onRefreshReviews
}: StatusViewProps) {
  const dependencies = Object.entries(ready?.dependencies ?? {});
  return (
    <section className="status-grid">
      <StatusTile
        icon={Gauge}
        label="FastAPI"
        value={health === "ok" ? "ok" : health === "bad" ? "error" : "unknown"}
        tone={health === "ok" ? "ok" : health === "bad" ? "danger" : "neutral"}
        actionLabel="刷新"
        loading={loading}
        onAction={onRefreshHealth}
      />
      <StatusTile
        icon={Gauge}
        label="Ready"
        value={ready?.status ?? "unknown"}
        tone={readyTone(ready?.status)}
        actionLabel="检查"
        loading={readyLoading}
        onAction={onRefreshReady}
      />
      <StatusTile
        icon={FileArchive}
        label="制度文档"
        value={`${documents.length}`}
        tone="neutral"
        actionLabel="刷新"
        onAction={onRefreshDocuments}
      />
      <StatusTile
        icon={Scale}
        label="待审批"
        value={`${reviews.length}`}
        tone={reviews.length ? "warn" : "ok"}
        actionLabel="刷新"
        onAction={onRefreshReviews}
      />
      {dependencies.map(([name, dependency]) => (
        <StatusTile
          key={name}
          icon={dependency.status === "ok" ? CheckCircle2 : dependency.status === "error" ? XCircle : AlertTriangle}
          label={name}
          value={dependency.status}
          detail={dependency.detail}
          tone={readyTone(dependency.status)}
          actionLabel="检查"
          loading={readyLoading}
          onAction={onRefreshReady}
        />
      ))}
    </section>
  );
}

function StatusTile({
  icon: Icon,
  label,
  value,
  detail,
  tone,
  actionLabel,
  loading,
  onAction
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  detail?: string;
  tone: "ok" | "warn" | "danger" | "neutral";
  actionLabel: string;
  loading?: boolean;
  onAction: () => void;
}) {
  return (
    <article className="status-tile">
      <div className={`item-icon ${tone}`}>
        <Icon size={20} aria-hidden="true" />
      </div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
        {detail ? <span className="status-detail">{detail}</span> : null}
      </div>
      <button type="button" disabled={loading} onClick={onAction}>
        {loading ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <RefreshCw size={16} aria-hidden="true" />}
        <span>{actionLabel}</span>
      </button>
    </article>
  );
}

function ContractReviewDetails({ review }: { review: ContractReview }) {
  const pending = review.review_status === "pending_review";
  return (
    <div className="result-stack">
      <div className={pending ? "review-banner pending" : "review-banner"}>
        <div>
          <p>整体风险</p>
          <strong>{review.risk_level}</strong>
        </div>
        <RiskPill risk={review.risk_level} />
        {pending ? <StatusPill label="review" value="待人工复核" tone="warn" /> : <StatusPill label="review" value="无需复核" tone="ok" />}
        {review.review_id ? <StatusPill label="review_id" value={review.review_id} /> : null}
      </div>

      {review.findings.length ? (
        <div className="finding-list">
          {review.findings.map((finding) => (
            <FindingItem key={`${finding.clause_type}-${finding.clause_name}`} finding={finding} />
          ))}
        </div>
      ) : (
        <EmptyState icon={ClipboardCheck} title={pending ? "完整结果待复核后返回" : "暂无风险明细"} compact />
      )}

      <SuggestionList suggestions={review.suggestions} />
      <CitationList items={review.evidence} title="法律依据" />
      <div className="disclaimer">{review.disclaimer}</div>
      <JsonDetails title="结构化结果" payload={review} />
    </div>
  );
}

function FindingItem({ finding }: { finding: ContractFinding }) {
  return (
    <article className="finding">
      <div className="finding-head">
        <h4>{finding.clause_name}</h4>
        <RiskPill risk={finding.risk_level} />
      </div>
      <div className="meta-grid">
        <StatusPill label="status" value={finding.status} />
        <StatusPill label="type" value={finding.clause_type} />
      </div>
      {finding.extracted_text ? <blockquote>{finding.extracted_text}</blockquote> : null}
      <p>{finding.analysis}</p>
      <p>{finding.suggestion}</p>
      <CitationList items={finding.evidence} title="依据" compact />
    </article>
  );
}

function ToolTraceList({ trace }: { trace: ToolTrace[] }) {
  if (!trace.length) return null;
  return (
    <div className="trace-list">
      <h3>工具调用</h3>
      {trace.map((item, index) => (
        <div className="trace-item" key={`${item.name}-${index}`}>
          <div className="trace-name">
            <Bot size={16} aria-hidden="true" />
            <span>{item.name}</span>
          </div>
          <div className="meta-grid">
            <StatusPill label="status" value={item.status} tone={item.status === "ok" ? "ok" : "danger"} />
            <StatusPill label="latency" value={`${item.latency}s`} />
            <StatusPill label="source" value={item.answer_source} />
            <StatusPill label="contexts" value={item.context_count} />
            <RiskPill risk={item.risk_level ?? null} />
          </div>
          {item.error ? <p className="trace-error">{item.error}</p> : null}
        </div>
      ))}
    </div>
  );
}

function CitationList({
  items,
  title = "引用依据",
  compact = false
}: {
  items: string[];
  title?: string;
  compact?: boolean;
}) {
  const cleanItems = items.filter(Boolean);
  if (!cleanItems.length) return null;
  return (
    <details className={compact ? "details compact" : "details"} open={!compact}>
      <summary>{title} {cleanItems.length}</summary>
      <div className="citation-list">
        {cleanItems.map((item, index) => (
          <div className="citation" key={`${index}-${item.slice(0, 20)}`}>
            {item}
          </div>
        ))}
      </div>
    </details>
  );
}

function SuggestionList({ suggestions }: { suggestions: string[] }) {
  const cleanSuggestions = suggestions.filter(Boolean);
  if (!cleanSuggestions.length) return null;
  return (
    <div className="suggestions">
      <h3>审查建议</h3>
      {cleanSuggestions.map((suggestion, index) => (
        <p key={`${index}-${suggestion.slice(0, 20)}`}>{suggestion}</p>
      ))}
    </div>
  );
}

function PayloadPreview({ payload }: { payload: Record<string, unknown> }) {
  const summary = typeof payload.summary === "string" ? payload.summary : "";
  const risk = typeof payload.risk_level === "string" ? payload.risk_level : "";
  const clauses = Array.isArray(payload.high_risk_clauses)
    ? payload.high_risk_clauses.filter((item) => typeof item === "string").join("、")
    : "";
  return (
    <div className="payload-preview">
      {summary ? <p>{summary}</p> : null}
      <div className="meta-grid">
        <StatusPill label="risk" value={risk} tone={risk === "high" ? "danger" : "neutral"} />
        <StatusPill label="clauses" value={clauses} tone="warn" />
      </div>
      <JsonDetails title="payload" payload={payload} />
    </div>
  );
}

function JsonDetails({ title, payload }: { title: string; payload: unknown }) {
  return (
    <details className="details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(payload, null, 2)}</pre>
    </details>
  );
}

function Metric({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "warn";
}) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function IconButton({
  label,
  icon: Icon,
  loading,
  onClick
}: {
  label: string;
  icon: LucideIcon;
  loading?: boolean;
  onClick: () => void;
}) {
  return (
    <button className="icon-button" type="button" aria-label={label} title={label} disabled={loading} onClick={onClick}>
      {loading ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Icon size={16} aria-hidden="true" />}
    </button>
  );
}

function StatusDot({ state }: { state: HealthState }) {
  return <span className={`status-dot ${state}`} aria-hidden="true" />;
}

function RiskPill({ risk }: { risk: RiskLevel | null }) {
  if (!risk) return null;
  const tone = risk === "high" ? "danger" : risk === "medium" ? "warn" : "ok";
  return <StatusPill label="risk" value={risk} tone={tone} />;
}

function ReviewPill({ status, reviewId }: { status: string | null; reviewId: string | null }) {
  if (!status) return null;
  return (
    <>
      <StatusPill label="review" value={status} tone={status === "pending_review" ? "warn" : "ok"} />
      {reviewId ? <StatusPill label="review_id" value={reviewId} /> : null}
    </>
  );
}

function readyTone(status: string | null | undefined): "ok" | "warn" | "danger" | "neutral" {
  if (status === "ok" || status === "not_configured") return "ok";
  if (status === "error") return "danger";
  if (status === "degraded") return "warn";
  return "neutral";
}

function StatusPill({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: string | number | null | undefined;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <span className={`pill ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </span>
  );
}

function EmptyState({
  icon: Icon,
  title,
  compact = false
}: {
  icon: LucideIcon;
  title: string;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "empty compact" : "empty"}>
      <Icon size={compact ? 20 : 28} aria-hidden="true" />
      <span>{title}</span>
    </div>
  );
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "请求失败";
}

function formatDate(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export default App;
