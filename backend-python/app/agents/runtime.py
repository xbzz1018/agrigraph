"""番茄/水稻病虫害固定工作流节点。"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.agents.schemas import AgentEvent, AgentState, utc_now
from app.agents.tools import ToolRegistry
from app.core.settings import Settings
from app.domain.control import asks_for_restricted_usage, sanitize_answer
from app.domain.models import AgricultureQuery, AnswerDraft, VisionObservation
from app.integrations.model_gateway import ModelGateway
from app.repositories import Repository


def _event(state: AgentState, agent_id: str, label: str, duration: int, **summary: Any) -> dict[str, Any]:
    return AgentEvent(
        run_id=state["run_id"],
        step_id=str(uuid.uuid4()),
        agent_id=agent_id,
        event_type="completed",
        status="COMPLETED",
        label=label,
        duration_ms=duration,
        data_summary=summary,
    ).model_dump()


@dataclass(slots=True)
class AgentRuntime:
    settings: Settings
    repository: Repository
    tools: ToolRegistry
    model: ModelGateway

    def query_router(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        observation = (
            VisionObservation.model_validate(state["vision_observation"])
            if state.get("vision_observation")
            else None
        )
        usage: dict[str, Any] = {}
        calls = 0
        if observation is not None:
            query = observation.to_query()
        else:
            context = [
                {
                    "role": str(item.get("role", "context")),
                    "content": str(item.get("content", ""))[:600],
                }
                for item in state.get("memory_context", [])[-6:]
                if item.get("content")
            ]
            user_input = state["objective"]
            if context:
                user_input = (
                    f"历史上下文：{json.dumps(context, ensure_ascii=False)}\n"
                    f"当前问题：{state['objective']}"
                )
            query, usage = self.model.structured(
                "将当前农业问题整理为 AgricultureQuery。历史上下文只用于理解省略与指代，"
                "不能作为农业事实。只识别番茄或水稻，不回答问题，不补充事实。",
                user_input,
                AgricultureQuery,
            )
            if query is None:
                query = self._fallback_query(state["objective"], state.get("crop_scope", "AUTO"))
            else:
                calls = 1
        duration = int((time.perf_counter() - started) * 1000)
        return {
            "agriculture_query": query.model_dump(),
            "retrieval_query": query.retrieval_text(state["objective"]) or state["objective"],
            "restricted_usage_request": asks_for_restricted_usage(state["objective"]),
            "model_calls": calls,
            "model_usage": usage,
            "workflow": ["QUERY_ROUTER"],
            "events": [_event(state, "query-router", "农业问题结构化完成", duration, taskType=query.taskType)],
        }

    def session_context(self, state: AgentState) -> dict[str, Any]:
        return self._tool(
            state,
            "session-context",
            "session.load",
            "读取会话上下文",
            "memory_context",
            owner=state["owner_username"],
            thread_id=state["thread_id"],
            current_objective=state["objective"],
            project_scope=self.settings.memory_project_scope,
            limit=6,
        )

    def document_research(self, state: AgentState) -> dict[str, Any]:
        crop = str(state.get("agriculture_query", {}).get("crop") or state.get("crop_scope") or "AUTO")
        return self._tool(
            state,
            "document-research",
            "elasticsearch.bm25",
            "BM25 候选检索完成",
            "document_evidence",
            query=state.get("retrieval_query") or state["objective"],
            crop_scope=crop,
            query_type=str(state.get("agriculture_query", {}).get("taskType") or "ENTITY"),
            limit=10,
        )

    def graph_reasoning(self, state: AgentState) -> dict[str, Any]:
        ids = [
            str(item.get("metadata", {}).get("entity", {}).get("id", ""))
            for item in state.get("document_evidence", [])
        ]
        return self._tool(
            state,
            "graph-reasoning",
            "neo4j.relations",
            "图谱关系补充完成",
            "graph_evidence",
            query=str(state.get("agriculture_query", {}).get("diseaseName") or state["objective"]),
            entity_ids=[item for item in ids if item],
            limit=20,
        )

    def answer(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        documents = state.get("document_evidence", [])
        graph = state.get("graph_evidence", [])
        candidates = [item.get("metadata", {}).get("entity", {}) for item in documents]
        controls = self._control_options(documents, candidates)
        draft: AnswerDraft | None = None
        usage: dict[str, Any] = state.get("model_usage", {})
        calls = 0
        if not state.get("restricted_usage_request") and (documents or graph):
            draft, answer_usage = self.model.structured(
                "你是农业病虫害知识助手。只回答问题直接要求的事实，优先选择与问题原句重合度最高的证据。"
                "问题按症状、病原、发生条件或防治原则分类；回答只覆盖提问的类别，不要追加其他类别。"
                "尽量原样引用证据中的关键短语，并为每个事实 Claim 标注证据 ID。"
                "可说明候选病虫害、症状、病原、发生条件、农业/生物防治和有效成分名称。"
                "禁止输出剂量、浓度、倍液、亩用量、混配、施药次数或安全间隔期。",
                f"问题：{state['objective']}\n证据：{self.model.evidence_payload(documents + graph)}",
                AnswerDraft,
            )
            if draft is not None:
                calls = 1
                usage = answer_usage
        if draft is None:
            draft = self._fallback_answer(state, documents, controls)
        duration = int((time.perf_counter() - started) * 1000)
        return {
            "candidate_entities": candidates,
            "control_options": controls,
            "draft_answer": draft.answer,
            "draft_claims": [claim.model_dump() for claim in draft.claims],
            "model_calls": calls,
            "model_usage": usage,
            "workflow": ["ANSWER"],
            "events": [_event(state, "answer", "农业知识回答生成完成", duration, claimCount=len(draft.claims))],
        }

    def evidence_check(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        evidence = {str(item["id"]): item for item in state.get("document_evidence", []) + state.get("graph_evidence", [])}
        claims = []
        for claim in state.get("draft_claims", []):
            ids = [str(item) for item in claim.get("evidenceIds", []) if str(item) in evidence]
            supported = [item for item in ids if self._supported(str(claim.get("text", "")), evidence[item]["excerpt"])]
            if supported:
                claims.append({"text": str(claim["text"]), "evidenceIds": supported, "supported": True})
        citation_ids = list(dict.fromkeys(item for claim in claims for item in claim["evidenceIds"]))
        attempted = len(state.get("draft_claims", []))
        coverage = len(claims) / attempted if attempted else 0.0
        warnings = [] if attempted == len(claims) else ["已移除缺少直接证据支持的陈述"]
        verified_answer = self._verified_answer(claims)
        duration = int((time.perf_counter() - started) * 1000)
        return {
            "draft_answer": verified_answer,
            "draft_claims": claims,
            "citation_ids": citation_ids,
            "citation_coverage": coverage,
            "warnings": warnings,
            "workflow": ["EVIDENCE_CHECK"],
            "events": [_event(state, "evidence-check", "Claim 与引用核验完成", duration, coverage=coverage)],
        }

    def output_boundary(self, state: AgentState) -> dict[str, Any]:
        started = time.perf_counter()
        answer, changed = sanitize_answer(state.get("draft_answer", ""), state["objective"])
        warnings = ["已应用农药信息输出边界"] if changed else []
        duration = int((time.perf_counter() - started) * 1000)
        return {
            "final_answer": answer,
            "warnings": warnings,
            "workflow": ["OUTPUT_BOUNDARY"],
            "events": [_event(state, "output-boundary", "防治知识边界检查完成", duration, filtered=changed)],
        }

    def finalize(self, state: AgentState) -> dict[str, Any]:
        return {
            "workflow": ["COMPLETE"],
            "events": [_event(state, "workflow", "多模态知识工作流完成", 0)],
        }

    def _tool(self, state: AgentState, agent_id: str, tool: str, label: str, key: str, **kwargs: Any) -> dict[str, Any]:
        step, start_at, started = str(uuid.uuid4()), utc_now(), time.perf_counter()
        try:
            values = self.tools.call(agent_id, tool, **kwargs)
            duration = int((time.perf_counter() - started) * 1000)
            self.repository.runs.save_tool_call(
                state["run_id"], step, agent_id, tool, "COMPLETED", self._safe_args(kwargs),
                {"resultCount": len(values)}, start_at, utc_now(), duration,
            )
            return {
                key: values,
                "tool_calls": 1,
                "workflow": [agent_id.upper().replace("-", "_")],
                "events": [_event(state, agent_id, label, duration, resultCount=len(values))],
            }
        except Exception as exc:
            duration = int((time.perf_counter() - started) * 1000)
            self.repository.runs.save_tool_call(
                state["run_id"], step, agent_id, tool, "FAILED", self._safe_args(kwargs), None,
                start_at, utc_now(), duration, type(exc).__name__,
            )
            return {
                key: [],
                "tool_calls": 1,
                "warnings": [f"{label}暂不可用，已降级继续"],
                "workflow": [agent_id.upper().replace("-", "_")],
                "events": [_event(state, agent_id, f"{label}暂不可用", duration, errorCode=type(exc).__name__)],
            }

    @staticmethod
    def _fallback_query(text: str, crop_scope: str) -> AgricultureQuery:
        crop = "番茄" if "番茄" in text or crop_scope.upper() == "TOMATO" else (
            "水稻" if "水稻" in text or crop_scope.upper() == "RICE" else "未知"
        )
        task = "CONTROL" if any(term in text for term in ("防治", "药剂", "有效成分")) else (
            "PATHOGEN" if "病原" in text else "CONDITION" if "条件" in text else "SYMPTOM"
        )
        return AgricultureQuery(crop=crop, taskType=task, target=text[:120])

    @staticmethod
    def _fallback_answer(
        state: AgentState, documents: list[dict[str, Any]], controls: list[dict[str, Any]]
    ) -> AnswerDraft:
        if state.get("restricted_usage_request"):
            return AnswerDraft(answer="具体用量和施用方式应以当地现行农药登记标签及农技人员指导为准。")
        if not documents:
            return AnswerDraft(answer="当前知识库没有找到足够依据，请补充作物、部位和可见症状。")
        first = documents[0]
        name = first.get("metadata", {}).get("entity", {}).get("name") or first["title"]
        excerpt = str(first.get("excerpt", "")).split("\n")[0][:220]
        answer = f"候选病虫害为{name}。{excerpt}"
        if controls:
            answer += " 可参考的防治方向包括：" + "、".join(item["name"] for item in controls[:6]) + "。"
        return AnswerDraft(
            answer=answer,
            claims=[{"text": excerpt or f"候选病虫害为{name}", "evidenceIds": [str(first["id"])]}],
        )

    @staticmethod
    def _control_options(documents: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        candidate_ids = {str(item.get("id", "")) for item in candidates}
        values: list[dict[str, Any]] = []
        for document in documents:
            for raw in document.get("metadata", {}).get("controlOptions", []):
                if not isinstance(raw, dict) or raw.get("type") not in {"AGRICULTURAL", "BIOLOGICAL", "ACTIVE_INGREDIENT"}:
                    continue
                if raw.get("targetDiseaseId") and str(raw["targetDiseaseId"]) not in candidate_ids:
                    continue
                values.append(dict(raw))
        return list({(item["name"], item["type"], item.get("targetDiseaseId", "")): item for item in values}.values())

    @staticmethod
    def _supported(claim: str, excerpt: str) -> bool:
        normalized_claim = re.sub(r"\s+", "", claim)
        normalized_evidence = re.sub(r"\s+", "", excerpt)
        if not normalized_claim or not normalized_evidence:
            return False
        if normalized_claim in normalized_evidence or normalized_evidence[:80] in normalized_claim:
            return True
        grams = {normalized_claim[index : index + 2] for index in range(max(0, len(normalized_claim) - 1))}
        return bool(grams) and sum(gram in normalized_evidence for gram in grams) / len(grams) >= 0.65

    @staticmethod
    def _verified_answer(claims: list[dict[str, Any]]) -> str:
        if not claims:
            return "当前证据不足，无法形成可靠的农业知识回答。"
        return "\n".join(
            f"{str(claim['text']).rstrip('。')}。 [{', '.join(claim['evidenceIds'])}]" for claim in claims
        )

    @staticmethod
    def _safe_args(values: dict[str, Any]) -> dict[str, Any]:
        return {key: str(value)[:160] for key, value in values.items() if key not in {"api_key", "password"}}
