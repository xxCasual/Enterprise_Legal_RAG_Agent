"""Shared constants for the legal assistant agent workflow."""

from __future__ import annotations


PUBLIC_TOOL_NAMES = (
    "search_law_articles",
    "search_company_policy",
    "contract_review_rules",
    "refuse_out_of_scope",
)

TOOL_BY_INTENT = {
    "law_qa": "search_law_articles",
    "policy_qa": "search_company_policy",
    "contract_review": "contract_review_rules",
    "refusal": "refuse_out_of_scope",
}

PLANNER_SYSTEM_PROMPT = """你是企业劳动合规 Agent 的工具规划器。

你只能处理中国劳动法律、企业内部制度、劳动合同风险审查和范围外拒答。
请根据用户问题选择一个或多个工具：
- 法律法规、劳动法、劳动合同法、仲裁、社保、加班费等问题，用 search_law_articles。
- 公司制度、员工手册、考勤、请假、报销、审批流程等问题，用 search_company_policy。
- 用户提交劳动合同文本或要求审查合同风险，用 contract_review_rules。
- 明显超出劳动合规范围或涉及违法违规、歧视、破解、股票天气闲聊等，用 refuse_out_of_scope。

如果问题同时比较法律要求和公司制度，请同时调用 search_company_policy 与 search_law_articles。
不要直接回答，只选择工具。"""

POLICY_ONLY_HINTS = (
    "主要想确认公司制度",
    "主要要查公司内部",
    "先按我们制度",
    "先查一下我们公司",
    "不是问劳动法",
    "我不是问劳动法",
    "我主要要查公司内部",
    "我主要想确认公司制度",
    "主要想确认公司制度怎么写",
)
