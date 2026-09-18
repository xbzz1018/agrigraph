"""集中装配多模态农业知识服务及外部客户端。"""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.chat_graph import MainAgentGraph
from app.agents.chat_service import AgentService
from app.agents.runtime import AgentRuntime
from app.agents.tools import ToolRegistry
from app.core.health import DependencyHealth
from app.core.security import Authenticator, TokenManager
from app.core.settings import Settings
from app.domain.agriculture import AgricultureDomain
from app.integrations.clients import ExternalClients
from app.integrations.model_gateway import ModelGateway
from app.integrations.retrieval import Bm25Retriever
from app.integrations.semantic import EmbeddingGateway, RerankerGateway
from app.integrations.vision import VisionGateway
from app.repositories import RepositoryHub
from app.repositories.memory import LayeredMemory


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    external_clients: ExternalClients
    repositories: RepositoryHub
    model: ModelGateway
    vision: VisionGateway
    embeddings: EmbeddingGateway
    reranker: RerankerGateway
    retriever: Bm25Retriever
    memory: LayeredMemory
    tools: ToolRegistry
    chat_graph: MainAgentGraph
    agent_service: AgentService
    authenticator: Authenticator
    token_manager: TokenManager
    agriculture: AgricultureDomain
    dependency_health: DependencyHealth

    @classmethod
    def build(cls, settings: Settings) -> "AppContainer":
        repositories = RepositoryHub(settings.db_path)
        external_clients = ExternalClients.build(settings)
        model = ModelGateway(settings)
        vision = VisionGateway(settings)
        embeddings = EmbeddingGateway(settings)
        reranker = RerankerGateway(settings)
        retriever = Bm25Retriever(settings, client=external_clients.es)
        memory = LayeredMemory(settings, embeddings, external_clients.es)
        tools = ToolRegistry(
            settings,
            repositories,
            retriever=retriever,
            graph_driver=external_clients.neo4j,
            reranker=reranker,
            memory=memory,
        )
        runtime = AgentRuntime(settings, repositories, tools, model)
        chat_graph = MainAgentGraph(runtime, settings.checkpoint_db_path)
        agent_service = AgentService(repositories, chat_graph, memory)
        authenticator = Authenticator(settings, repositories)
        token_manager = TokenManager(settings, repositories)
        agriculture = AgricultureDomain(settings, retriever, external_clients.neo4j)
        health = DependencyHealth(
            settings,
            model.enabled,
            vision.enabled,
            embeddings.enabled,
            reranker.enabled,
        )
        container = cls(
            settings,
            external_clients,
            repositories,
            model,
            vision,
            embeddings,
            reranker,
            retriever,
            memory,
            tools,
            chat_graph,
            agent_service,
            authenticator,
            token_manager,
            agriculture,
            health,
        )
        container._bootstrap_admin()
        return container

    def _bootstrap_admin(self) -> None:
        username = self.settings.bootstrap_admin_username
        password = self.settings.bootstrap_admin_password
        if not username or not password:
            return
        try:
            self.repositories.users.get_user(username)
        except LookupError:
            self.token_manager.register(username, password, "ADMIN")

    def close(self) -> None:
        self.chat_graph.close()
        self.memory.close()
        self.reranker.close()
        self.embeddings.close()
        self.external_clients.close()
