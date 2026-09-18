"""农业对话会话、同步问答、SSE 流和取消接口。"""

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.dependencies import current_principal, get_container
from app.api.responses import envelope, sse
from app.api.schemas import ChatRequest, CreateSessionRequest, UpdateSessionRequest
from app.core.container import AppContainer
from app.core.security import Principal

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.get("/agriculture-chat/sessions")
def list_sessions(
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.repositories.chats.list_sessions(principal.username))


@router.post("/agriculture-chat/sessions")
def create_session(
    body: CreateSessionRequest,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(
        container.repositories.chats.create_session(
            principal.username, body.title, body.cropScope, body.knowledgeEnhanced
        )
    )


@router.get("/agriculture-chat/sessions/{session_id}")
def get_session(
    session_id: str,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.repositories.chats.get_session(principal.username, session_id))


@router.patch("/agriculture-chat/sessions/{session_id}")
def update_session(
    session_id: str,
    body: UpdateSessionRequest,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(
        container.repositories.chats.update_session(
            principal.username,
            session_id,
            title=body.title,
            crop_scope=body.cropScope,
            enhanced=body.knowledgeEnhanced,
        )
    )


@router.delete("/agriculture-chat/sessions/{session_id}")
def delete_session(
    session_id: str,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    container.repositories.chats.delete_session(principal.username, session_id)
    container.agent_service.forget_session(principal.username, session_id)
    return envelope({"deleted": True})


@router.post("/agriculture-chat/sessions/{session_id}/messages")
def ask(
    session_id: str,
    body: ChatRequest,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    chats = container.repositories.chats
    chats.get_session_summary(principal.username, session_id)
    chats.add_message(session_id, "user", body.question.strip())
    container.agent_service.remember_message(principal.username, session_id, "user", body.question)
    result = container.agent_service.run(principal.username, session_id, body)
    saved = chats.add_message(session_id, "assistant", result["answer"], result)
    container.agent_service.remember_message(principal.username, session_id, "assistant", result["answer"])
    container.agent_service.remember_interaction(principal.username, session_id, body.question, result)
    return envelope(saved)


@router.post("/agriculture-chat/sessions/{session_id}/messages/stream")
def ask_stream(
    session_id: str,
    body: ChatRequest,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    container.repositories.chats.get_session_summary(principal.username, session_id)

    def generate():
        # 只序列化公开事件；Agent 内部提示词和推理不会进入 SSE。
        for event, payload in container.agent_service.stream_chat(principal.username, session_id, body):
            yield sse(event, payload)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/agriculture-chat/streams/{run_id}/cancel")
def cancel_stream(
    run_id: str,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agent_service.cancel(run_id, principal.username, principal.is_admin))


@router.post("/chat/graph-rag")
def graph_rag(
    body: ChatRequest,
    principal: Principal = Depends(current_principal),
    container: AppContainer = Depends(get_container),
):
    return envelope(container.agent_service.run(principal.username, str(uuid.uuid4()), body))
