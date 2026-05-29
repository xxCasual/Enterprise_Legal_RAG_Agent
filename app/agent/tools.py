"""Tool wrappers used by the LangGraph assistant workflow."""

from __future__ import annotations

from typing import Any, Dict, List

from langchain_core.tools import StructuredTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.observability import metrics
from app.services.document_service import document_service
from app.services.rag_service import rag_service


TOOL_DESCRIPTIONS = {
    "search_law_articles": "检索中国劳动相关法律法规，并回答法律问答或法律依据问题。",
    "search_company_policy": "检索企业上传的内部制度、员工手册、考勤、请假、报销或审批规则。",
    "contract_review_rules": "审查劳动合同文本，识别试用期、工资、工时、社保、解除、竞业限制等条款风险。",
    "refuse_out_of_scope": "当问题超出中国劳动合规、企业制度或劳动合同审查范围时，生成拒答。",
}


def search_law_articles(query: str) -> Dict[str, Any]:
    result = rag_service.chat(query)
    return {
        "answer": result["answer"],
        "citations": result["citations"],
        "route": result["route"],
        "contexts": result["citations"],
        "result_type": "law_qa",
    }


def search_company_policy(query: str) -> Dict[str, Any]:
    docs = document_service.search(query, k=4)
    contexts = [doc.page_content for doc in docs]
    answer, answer_source = _answer_policy_question(query, contexts)
    return {
        "answer": answer,
        "citations": contexts,
        "route": "policy_qa",
        "contexts": contexts,
        "result_type": "policy_qa",
        "answer_source": answer_source,
        "context_count": len(contexts),
    }


def review_labor_contract(
    contract_text: str,
    include_evidence: bool = False,
) -> Dict[str, Any]:
    from app.services.contract_review_service import contract_review_service
    from app.services.review_service import review_service

    result = contract_review_service.review_contract(
        contract_text,
        include_evidence=include_evidence,
    )
    risk_level = result.get("risk_level", "low")
    if risk_level == "high":
        pending = review_service.create_pending_review(
            source_type="contract_review",
            payload=_contract_review_pending_payload(contract_text, result),
            final_answer=result,
        )
        review_id = pending["review_id"]
        summary = "高风险合同审查结果已进入人工复核队列，审批通过后再返回完整审查结果。"
        contract_review = {
            "risk_level": "high",
            "findings": [],
            "evidence": [],
            "suggestions": [summary],
            "disclaimer": result.get("disclaimer", "仅供参考，需人工复核"),
            "latency": result.get("latency", 0),
            "review_status": "pending_review",
            "review_id": review_id,
        }
        return {
            "answer": summary,
            "citations": [],
            "contexts": [],
            "route": "contract_review",
            "result_type": "contract_review",
            "risk_level": "high",
            "review_status": "pending_review",
            "review_id": review_id,
            "contract_review": contract_review,
        }

    answer = _contract_review_answer(result)
    return {
        "answer": answer,
        "citations": result.get("evidence", []),
        "contexts": result.get("evidence", []),
        "route": "contract_review",
        "result_type": "contract_review",
        "risk_level": risk_level,
        "review_status": "not_required",
        "review_id": None,
        "contract_review": {
            **result,
            "review_status": "not_required",
            "review_id": None,
        },
    }


def contract_review_rules(contract_text: str) -> Dict[str, Any]:
    return review_labor_contract(contract_text, include_evidence=False)


def refuse_out_of_scope(query: str) -> Dict[str, Any]:
    answer = (
        "超出范围，无法提供该请求的帮助。这个系统只能回答中国劳动合规、企业制度和劳动合同审查相关问题。"
        "你可以问我试用期、工资、加班、解除劳动合同或企业制度相关问题。"
    )
    return {
        "answer": answer,
        "citations": [],
        "contexts": [],
        "route": "refusal",
        "result_type": "refusal",
        "refused": True,
    }


def registered_agent_tools() -> List[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=search_law_articles,
            name="search_law_articles",
            description=TOOL_DESCRIPTIONS["search_law_articles"],
        ),
        StructuredTool.from_function(
            func=search_company_policy,
            name="search_company_policy",
            description=TOOL_DESCRIPTIONS["search_company_policy"],
        ),
        StructuredTool.from_function(
            func=contract_review_rules,
            name="contract_review_rules",
            description=TOOL_DESCRIPTIONS["contract_review_rules"],
        ),
        StructuredTool.from_function(
            func=refuse_out_of_scope,
            name="refuse_out_of_scope",
            description=TOOL_DESCRIPTIONS["refuse_out_of_scope"],
        ),
    ]


def _contract_review_answer(result: Dict[str, Any]) -> str:
    risk_level = result.get("risk_level", "low")
    findings = result.get("findings", [])
    risky_clauses = [
        finding.get("clause_name", "")
        for finding in findings
        if finding.get("risk_level") in {"medium", "high"}
    ]
    if risky_clauses:
        clauses = "、".join(clause for clause in risky_clauses if clause)
        return f"合同审查完成，整体风险等级为 {risk_level}。建议重点复核：{clauses}。"
    return f"合同审查完成，整体风险等级为 {risk_level}，暂未发现中高风险条款。"


def _contract_review_pending_payload(contract_text: str, result: Dict[str, Any]) -> Dict[str, Any]:
    high_risk_clauses = [
        finding["clause_name"]
        for finding in result.get("findings", [])
        if finding.get("risk_level") == "high"
    ]
    preview = contract_text.strip()
    return {
        "risk_level": result.get("risk_level", "high"),
        "source": "labor_contract_review",
        "summary": "高风险劳动合同审查结果待人工复核",
        "high_risk_clauses": high_risk_clauses,
        "contract_text_preview": preview[:500],
    }


def _answer_policy_question(query: str, contexts: List[str]) -> tuple[str, str]:
    if not contexts:
        return "当前企业制度文档中未检索到相关依据。", "no_context"

    if not settings.deepseek_api_key:
        return _fallback_policy_answer(contexts), "retrieval_fallback"

    prompt = ChatPromptTemplate.from_template(
        """你是企业劳动合规助手。请严格根据以下企业制度文档回答问题。

要求：
1. 只根据提供的企业制度回答，不要补充外部知识
2. 如果制度中没有明确依据，请回答“当前企业制度文档中未检索到相关依据”
3. 回答简洁清楚

企业制度文档：
{context}

用户问题：{question}"""
    )
    try:
        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )
        chain = prompt | llm | StrOutputParser()
        return (
            chain.invoke(
                {
                    "context": "\n\n".join(contexts),
                    "question": query,
                }
            ),
            "llm",
        )
    except Exception:
        metrics.increment("llm_failures_total")
        return _fallback_policy_answer(contexts), "retrieval_fallback"


def _fallback_policy_answer(contexts: List[str]) -> str:
    snippets = [
        f"{index}. {_truncate_policy_context(context)}"
        for index, context in enumerate(contexts[:4], start=1)
        if context.strip()
    ]
    if not snippets:
        return "当前企业制度文档中未检索到相关依据。"
    return "以下为检索到的企业制度片段，请以企业制度原文为准：\n" + "\n".join(
        snippets
    )


def _truncate_policy_context(context: str, limit: int = 240) -> str:
    text = " ".join(context.split())
    return text if len(text) <= limit else f"{text[:limit]}..."
