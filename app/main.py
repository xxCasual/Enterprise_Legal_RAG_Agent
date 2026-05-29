"""FastAPI entrypoint for the enterprise legal RAG platform."""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, File, HTTPException, Path, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app.agent import run_agent_chat
from app.agent.tools import review_labor_contract
from app.core.database import init_database
from app.core.logging import configure_logging
from app.core.observability import metrics
from app.core.readiness import collect_readiness
from app.core.security import require_admin_token
from app.core.config import settings
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ContractReviewRequest,
    ContractReviewResponse,
    DocumentListResponse,
    DocumentRecord,
    DocumentUploadResponse,
    ErrorResponse,
    HealthResponse,
    PendingReviewListResponse,
    PendingReviewRecord,
    ReadyResponse,
    ReviewDecisionResponse,
)
from app.services.document_service import document_service
from app.services.review_service import (
    ReviewNotFoundError,
    ReviewStateError,
    review_service,
)


configure_logging()
logger = logging.getLogger("legal_rag.api")

OPENAPI_TAGS = [
    {
        "name": "系统状态",
        "description": "用于检查服务是否正常启动。",
    },
    {
        "name": "统一问答",
        "description": (
            "统一入口，自动路由到法律问答、企业制度问答、合同审查或拒答。"
        ),
    },
    {
        "name": "合同审查",
        "description": (
            "提交劳动合同文本进行结构化风险审查。高风险合同不会直接返回完整结论，"
            "而是进入人工复核队列。"
        ),
    },
    {
        "name": "人工审批",
        "description": "查看待人工复核的合同，并执行通过或拒绝操作。",
    },
    {
        "name": "企业制度",
        "description": "上传和查看企业制度文档，供制度问答链路检索使用。",
    },
]

APP_DESCRIPTION = """
面向企业劳动合规场景的中文 RAG + Agent 后端接口。

推荐人工审查合同的实际操作顺序：

1. 使用 `POST /api/review/contract` 提交合同文本。
2. 若返回 `review_status = not_required`，可直接查看结构化审查结果。
3. 若返回 `review_status = pending_review`，请记录 `review_id`。
4. 使用 `GET /api/reviews/pending` 查看待人工复核列表。
5. 人工确认后，调用 `POST /api/reviews/{review_id}/approve` 或 `POST /api/reviews/{review_id}/reject` 完成审批。

如果你想让系统自动识别问题类型，请使用 `POST /api/chat` 作为统一入口。
""".strip()


app = FastAPI(
    title="企业劳动合规 RAG 与审查平台",
    description=APP_DESCRIPTION,
    version="0.2.0",
    openapi_tags=OPENAPI_TAGS,
    swagger_ui_parameters={
        "docExpansion": "list",
        "defaultModelsExpandDepth": -1,
        "displayRequestDuration": True,
        "filter": True,
    },
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    init_database()


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started_at = time.perf_counter()
    response = None
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        latency = time.perf_counter() - started_at
        metrics.increment("http_requests_total")
        metrics.observe("http_request_duration_seconds", latency)
        if response is not None:
            response.headers["X-Request-ID"] = request_id
        logger.info(
            json.dumps(
                {
                    "event": "http_request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "latency": round(latency, 4),
                },
                ensure_ascii=False,
            )
        )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
    detail = str(exc) if settings.log_level == "DEBUG" else "Internal server error"
    payload = ErrorResponse(error="internal_error", detail=detail)
    content = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return JSONResponse(status_code=500, content=content)


@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["系统状态"],
    summary="检查服务状态",
    description="用于快速确认 FastAPI 服务是否正常运行。",
)
async def health() -> HealthResponse:
    return HealthResponse()


@app.get(
    "/api/ready",
    response_model=ReadyResponse,
    tags=["系统状态"],
    summary="检查生产依赖状态",
    description="检查数据库、Redis、Chroma、模型配置和文档索引状态。",
)
async def ready() -> ReadyResponse:
    return ReadyResponse(**collect_readiness())


@app.get(
    "/api/metrics",
    response_class=PlainTextResponse,
    tags=["系统状态"],
    summary="查看基础 Prometheus 指标",
)
async def metrics_endpoint() -> PlainTextResponse:
    return PlainTextResponse(metrics.render_prometheus())


@app.post(
    "/api/chat",
    response_model=ChatResponse,
    tags=["统一问答"],
    summary="统一问答入口",
    description=(
        "输入自然语言问题后，系统会自动识别为法律问答、企业制度问答、"
        "合同审查或拒答，并返回统一结构的结果。"
    ),
)
async def chat(
    request: ChatRequest = Body(
        ...,
        openapi_examples={
            "law_question": {
                "summary": "法律问答样例",
                "value": {"query": "试用期最长多久？"},
            },
            "policy_question": {
                "summary": "企业制度问答样例",
                "value": {"query": "公司的工资发放日是什么时候？"},
            },
            "contract_review": {
                "summary": "合同审查样例",
                "value": {"query": "请审查这份劳动合同：员工自愿放弃社保。"},
            },
            "refusal": {
                "summary": "拒答样例",
                "value": {"query": "帮我写一份让公司不用赔钱的辞退通知。"},
            },
        },
    )
) -> ChatResponse:
    result = run_agent_chat(request.query)
    return ChatResponse(**result)


@app.post(
    "/api/review/contract",
    response_model=ContractReviewResponse,
    tags=["合同审查"],
    summary="审查劳动合同",
    description=(
        "提交劳动合同正文，返回结构化风险审查结果。"
        "如果整体风险为 high，系统会创建待人工复核记录，并返回 `review_id`。"
    ),
)
async def review_contract(
    request: ContractReviewRequest = Body(
        ...,
        openapi_examples={
            "high_risk_contract": {
                "summary": "高风险合同样例",
                "description": "包含放弃社保和单方随时解除等高风险条款。",
                "value": {
                    "contract_text": (
                        "甲方可随时解除合同且不支付经济补偿。"
                        "乙方自愿放弃社保，由甲方按月发放补贴代替。"
                    )
                },
            },
            "normal_contract": {
                "summary": "普通合同样例",
                "description": "用于演示无需人工复核的审查结果。",
                "value": {
                    "contract_text": (
                        "合同期限为三年，试用期三个月。甲方依法支付工资并缴纳社会保险，"
                        "标准工时制，解除条件按法律规定执行。"
                    )
                },
            },
        },
    )
) -> ContractReviewResponse:
    result = review_labor_contract(request.contract_text, include_evidence=True)
    contract_review = result.get("contract_review") or {}
    return ContractReviewResponse(**contract_review)


@app.get(
    "/api/reviews/pending",
    response_model=PendingReviewListResponse,
    tags=["人工审批"],
    summary="查看待人工复核合同",
    description="返回当前所有待人工复核的高风险合同记录。",
)
async def list_pending_reviews(
    _auth: None = Depends(require_admin_token),
) -> PendingReviewListResponse:
    records = [
        PendingReviewRecord(**record) for record in review_service.list_pending_reviews()
    ]
    return PendingReviewListResponse(reviews=records)


@app.post(
    "/api/reviews/{review_id}/approve",
    response_model=ReviewDecisionResponse,
    tags=["人工审批"],
    summary="通过人工复核",
    description="审批通过后，系统会返回之前暂存的完整审查结果。",
)
async def approve_review(
    review_id: str = Path(..., description="待人工复核记录的唯一标识"),
    _auth: None = Depends(require_admin_token),
) -> ReviewDecisionResponse:
    try:
        result = review_service.approve_review(review_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Review not found: {review_id}") from exc
    except ReviewStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReviewDecisionResponse(**result)


@app.post(
    "/api/reviews/{review_id}/reject",
    response_model=ReviewDecisionResponse,
    tags=["人工审批"],
    summary="拒绝人工复核结果",
    description="审批拒绝后，系统不会返回完整审查结果。",
)
async def reject_review(
    review_id: str = Path(..., description="待人工复核记录的唯一标识"),
    _auth: None = Depends(require_admin_token),
) -> ReviewDecisionResponse:
    try:
        result = review_service.reject_review(review_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Review not found: {review_id}") from exc
    except ReviewStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ReviewDecisionResponse(**result)


@app.post(
    "/api/documents/upload",
    response_model=DocumentUploadResponse,
    tags=["企业制度"],
    summary="上传企业制度文档",
    description="上传企业制度文档并建立可检索索引，供企业制度问答使用。",
)
async def upload_document(
    file: UploadFile = File(...),
    _auth: None = Depends(require_admin_token),
) -> DocumentUploadResponse:
    file_name = file.filename or "uploaded_document"
    content = await file.read()
    try:
        submit_upload = getattr(document_service, "submit_upload", None) or getattr(
            document_service,
            "ingest_upload",
        )
        record = submit_upload(file_name, content)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DocumentUploadResponse(**record)


@app.get(
    "/api/documents",
    response_model=DocumentListResponse,
    tags=["企业制度"],
    summary="查看已上传制度文档",
    description="返回当前企业制度知识库中已登记的文档列表。",
)
async def list_documents(
    _auth: None = Depends(require_admin_token),
) -> DocumentListResponse:
    records = [DocumentRecord(**record) for record in document_service.list_documents()]
    return DocumentListResponse(documents=records)
