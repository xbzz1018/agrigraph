import pytest

from app.agents.tools import ToolPermissionError, ToolRegistry


def test_tool_allowlist_blocks_unknown_agent(settings, repository):
    registry = ToolRegistry(settings, repository)
    with pytest.raises(ToolPermissionError):
        registry.call("supervisor", "elasticsearch.bm25", query="test", crop_scope="AUTO")


def test_memory_excludes_current_user_message(settings, repository):
    session = repository.chats.create_session("tester", "水稻咨询", "RICE", True)
    repository.chats.add_message(session["id"], "user", "水稻叶片有病斑")
    repository.chats.add_message(session["id"], "assistant", "请补充田间湿度")
    repository.chats.add_message(session["id"], "user", "田间湿度很高")

    registry = ToolRegistry(settings, repository)
    memory = registry.call(
        "session-context",
        "session.load",
        owner="tester",
        thread_id=session["id"],
        current_objective="田间湿度很高",
        limit=6,
    )

    assert isinstance(memory, list)
    assert len(memory) == 2
    assert "水稻叶片有病斑" in memory[0]["content"]
    assert "请补充田间湿度" in memory[1]["content"]
    assert all("田间湿度很高" not in item["content"] for item in memory)


"""Agent 工具白名单和越权阻断测试。"""
