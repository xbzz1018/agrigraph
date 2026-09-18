<script setup lang="ts">
import MarkdownIt from 'markdown-it';
import { useFullscreen } from '@vueuse/core';
import GlobalSearch from '@/layouts/modules/global-search/index.vue';
import UserAvatar from '@/layouts/modules/global-header/components/user-avatar.vue';
import AgentTimeline from '@/components/agent/agent-timeline.vue';
import type { AgentTraceEvent } from '@/components/agent/agent-timeline.vue';
import { postSse } from '@/utils/sse';

interface RetrievalStats { documentCount: number; graphNodeCount: number; graphEdgeCount: number }
interface AnswerData {
  answer: string; grounded: boolean; degraded: boolean;
  warnings: string[]; workflow: string[]; modelUsed: string; generationMode: string;
  answerMode: string; coverageStatus: string;
  latencyMs: number; retrievalStats: RetrievalStats; agentRunId?: string; modelCalls?: number; toolCalls?: number;
  agentEvents?: AgentTraceEvent[];
}
interface ChatMessage { id: number; role: 'user' | 'assistant'; content: string; createdAt: string; answer?: AnswerData | null }
interface ChatSession { id: string; title: string; cropScope: string; knowledgeEnhanced: boolean; createdAt: string; updatedAt: string }

const sessions = ref<ChatSession[]>([]);
const messages = ref<ChatMessage[]>([]);
const currentSessionId = ref('');
const historyKeyword = ref('');
const question = ref('');
const cropScope = ref(localStorage.getItem('agrigraph-default-crop') || 'AUTO');
const route = useRoute();
const markdown = new MarkdownIt({ html: false, linkify: true, breaks: true });
const appStore = useAppStore();
const themeStore = useThemeStore();
const { isFullscreen, toggle: toggleFullscreen } = useFullscreen();
const loading = ref(false);
const loadingLabel = ref('正在准备农业问答');
const historyCollapsed = ref(false);
const scrollRef = ref<HTMLElement | null>(null);
const activeRequestId = ref('');
let activeController: AbortController | null = null;

const scopeOptions = [
  { label: '自动', value: 'AUTO' }, { label: '番茄', value: 'TOMATO' }, { label: '水稻', value: 'RICE' }
];
const workflowLabels: Record<string, string> = {
  REWRITE: '规范化问题', ENTITY_LINK: '识别作物与病害实体', HYBRID_RETRIEVE: '执行混合检索', GRAPH_EXPAND: '扩展图谱邻域',
  CONTEXT_BUILD: '整理回答依据', GENERATE: '调用模型生成', CITATION_VALIDATE: '校验引用完整性', DIRECT_MODEL: '直接调用模型', COMPLETE: '处理完成'
};
function answerModeLabel(mode?: string) {
  if (mode === 'KNOWLEDGE_RAG') return '知识库增强';
  if (mode === 'GENERAL_AGRICULTURE') return '农业通识';
  return '';
}
const filteredSessions = computed(() => sessions.value.filter(item => item.title.toLowerCase().includes(historyKeyword.value.trim().toLowerCase())));
const currentSession = computed(() => sessions.value.find(item => item.id === currentSessionId.value));
const suggestions = computed(() => cropScope.value === 'RICE'
  ? ['水稻纹枯病有哪些典型症状？', '水稻分蘖期有哪些管理要点？', '稻瘟病容易在什么条件下发生？']
  : cropScope.value === 'TOMATO'
    ? ['番茄晚疫病有哪些典型症状？', '番茄叶片出现同心轮纹可能是什么病？', '番茄灰霉病的发生条件是什么？']
    : ['番茄晚疫病有哪些典型症状？', '水稻纹枯病容易在什么条件下发生？', '如何区分相似的叶片病害？']);

async function loadSessions(selectFirst = true) {
  const { data } = await request<ChatSession[]>({ url: '/agriculture-chat/sessions' });
  sessions.value = data || [];
  if (selectFirst && sessions.value.length) await selectSession(sessions.value[0].id);
  if (!sessions.value.length) await createSession();
}

async function createSession() {
  const { data, error } = await request<ChatSession>({
    url: '/agriculture-chat/sessions', method: 'POST', data: { title: '新农业对话', cropScope: cropScope.value, knowledgeEnhanced: true }
  });
  if (error || !data) return;
  sessions.value.unshift(data);
  currentSessionId.value = data.id;
  messages.value = [];
}

async function selectSession(id: string) {
  currentSessionId.value = id;
  const { data } = await request<{ session: ChatSession; messages: ChatMessage[] }>({ url: `/agriculture-chat/sessions/${id}` });
  if (!data) return;
  messages.value = data.messages || [];
  cropScope.value = data.session.cropScope;
  await nextTick(); scrollToBottom(false);
}

async function updateSessionSettings() {
  if (!currentSessionId.value) return;
  const { data } = await request<ChatSession>({
    url: `/agriculture-chat/sessions/${currentSessionId.value}`, method: 'PATCH',
    data: { cropScope: cropScope.value, knowledgeEnhanced: true }
  });
  if (data) sessions.value = sessions.value.map(item => item.id === data.id ? data : item);
}

async function handleSessionAction(key: string, session: ChatSession) {
  if (key === 'rename') {
    const title = window.prompt('请输入新的对话名称', session.title)?.trim();
    if (!title) return;
    const { data } = await request<ChatSession>({ url: `/agriculture-chat/sessions/${session.id}`, method: 'PATCH', data: { title } });
    if (data) sessions.value = sessions.value.map(item => item.id === data.id ? data : item);
  }
  if (key === 'delete') {
    const confirmed = window.confirm(`确定删除对话“${session.title}”吗？`);
    if (!confirmed) return;
    await request({ url: `/agriculture-chat/sessions/${session.id}`, method: 'DELETE' });
    sessions.value = sessions.value.filter(item => item.id !== session.id);
    if (currentSessionId.value === session.id) {
      if (sessions.value.length) await selectSession(sessions.value[0].id); else await createSession();
    }
  }
}

async function sendQuestion(value = question.value) {
  const text = value.trim();
  if (!text || loading.value) return;
  if (!currentSessionId.value) await createSession();
  if (!currentSessionId.value) {
    window.$message?.error('新建对话失败，请稍后重试');
    return;
  }
  const optimisticId = Date.now();
  messages.value.push({ id: optimisticId, role: 'user', content: text, createdAt: new Date().toISOString() });
  const assistantId = optimisticId + 1;
  messages.value.push({ id: assistantId, role: 'assistant', content: '', createdAt: new Date().toISOString(),
    answer: { answer: '', grounded: false, degraded: false, warnings: [], workflow: [], modelUsed: '', generationMode: 'STREAMING',
      answerMode: '', coverageStatus: 'UNKNOWN',
      latencyMs: 0, retrievalStats: { documentCount: 0, graphNodeCount: 0, graphEdgeCount: 0 }, agentEvents: [] } });
  question.value = '';
  loading.value = true;
  loadingLabel.value = '正在连接农业知识服务';
  activeRequestId.value = crypto.randomUUID();
  activeController = new AbortController();
  await nextTick(); scrollToBottom();
  try {
    // 一个回调同时消费兼容事件和 agent_event，页面只展示公开轨迹，不接收模型隐藏推理。
    await postSse<any>(`/agriculture-chat/sessions/${currentSessionId.value}/messages/stream`,
      { question: text, cropScope: cropScope.value, requestId: activeRequestId.value }, activeController.signal,
      ({ event, data }) => {
        const assistant = messages.value.find(item => item.id === assistantId);
        if (event === 'connected') {
          activeRequestId.value = data.requestId;
          if (assistant?.answer) assistant.answer.agentRunId = data.agentRunId;
        }
        if (event === 'agent_event' && assistant?.answer) {
          assistant.answer.agentEvents ||= [];
          assistant.answer.agentEvents.push(data as AgentTraceEvent);
          loadingLabel.value = data.label || 'Agent 正在协作';
        }
        if (event === 'route_decision') loadingLabel.value = data.label || '正在判断问题范围';
        if (event === 'workflow' || event === 'retrieval_result') {
          loadingLabel.value = data.label || '正在处理';
          const state = data.data?.state;
          if (state && assistant?.answer && !assistant.answer.workflow.includes(state)) assistant.answer.workflow.push(state);
        }
        if (event === 'answer_chunk' && assistant) assistant.content += String(data.data || '');
        if (event === 'complete' && assistant?.answer) Object.assign(assistant.answer, data.data || {});
        if (event === 'message_saved' && assistant) Object.assign(assistant, data);
        if (event === 'error') throw new Error(data.message || '流式问答失败');
        nextTick(() => scrollToBottom());
      });
    const target = sessions.value.find(item => item.id === currentSessionId.value);
    if (target?.title === '新农业对话') target.title = text.length > 32 ? `${text.slice(0, 32)}...` : text;
  } catch (error) {
    const assistant = messages.value.find(item => item.id === assistantId);
    if (assistant && !assistant.content) assistant.content = error instanceof DOMException && error.name === 'AbortError'
      ? '生成已停止。' : '农业问答服务暂时不可用，请检查后端和模型网关状态。';
    if (assistant?.answer) assistant.answer.generationMode = error instanceof DOMException ? 'CANCELLED' : 'FAILED';
  } finally {
    loading.value = false;
    activeRequestId.value = '';
    activeController = null;
  }
  await nextTick(); scrollToBottom();
}

async function stopGeneration() {
  if (activeRequestId.value) await request({ url: `/agriculture-chat/streams/${activeRequestId.value}/cancel`, method: 'POST' });
  activeController?.abort();
}

function regenerate(index: number) {
  for (let current = index - 1; current >= 0; current -= 1) {
    if (messages.value[current].role === 'user') { sendQuestion(messages.value[current].content); return; }
  }
}

function processedContent(message: ChatMessage) {
  return message.content
    .replace(/\[D?\d+]/g, '')
    .replace(/图谱\s*\[G:[^\]]+]/g, '知识图谱')
    .replace(/\[G:[^\]]+]/g, '')
    .replace(/[（(]\s*证据来源[:：][^）)]*[）)]/g, '')
    .replace(/^\s*参考来源[:：].*$/gm, '')
    .trim();
}

function renderedContent(message: ChatMessage) {
  return markdown.render(processedContent(message));
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendQuestion(); }
}

function scrollToBottom(smooth = true) {
  scrollRef.value?.scrollTo({ top: scrollRef.value.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
}

function formatTime(value: string) {
  if (!value) return '';
  return dayjs(value).format('MM-DD HH:mm');
}

function copyAnswer(content: string) {
  navigator.clipboard.writeText(content); window.$message?.success('回答已复制');
}

watch(cropScope, updateSessionSettings);
onMounted(async () => {
  await loadSessions();
  const preset = String(route.query.question || '').trim();
  if (preset) await sendQuestion(preset);
});
onBeforeUnmount(() => activeController?.abort());
</script>

<template>
  <div class="chat-page" :class="{ 'history-collapsed': historyCollapsed }">
    <aside class="history-panel">
      <div class="history-header">
        <NButton type="primary" block @click="createSession"><template #icon><icon-solar:add-circle-linear /></template>新建对话</NButton>
        <NInput v-model:value="historyKeyword" clearable size="small" placeholder="搜索历史对话"><template #prefix><icon-solar:magnifer-linear /></template></NInput>
      </div>
      <div class="history-list">
        <div class="history-label">对话记录</div>
        <button v-for="session in filteredSessions" :key="session.id" type="button" class="history-item" :class="{ active: currentSessionId === session.id }" @click="selectSession(session.id)">
          <icon-solar:chat-round-dots-linear />
          <span><b>{{ session.title }}</b><small>{{ formatTime(session.updatedAt || session.createdAt) }}</small></span>
          <NDropdown trigger="click" :options="[{label:'重命名',key:'rename'},{label:'删除',key:'delete'}]" @select="key => handleSessionAction(String(key), session)">
            <i title="对话操作" @click.stop><icon-solar:menu-dots-linear /></i>
          </NDropdown>
        </button>
        <NEmpty v-if="!filteredSessions.length" size="small" description="暂无匹配对话" class="mt-40px" />
      </div>
      <button class="collapse-history" type="button" title="折叠历史对话" @click="historyCollapsed = true"><icon-solar:sidebar-minimalistic-linear /></button>
    </aside>

    <main class="conversation-panel">
      <header class="chat-toolbar">
        <div class="conversation-title">
          <NButton v-if="historyCollapsed" quaternary circle title="展开历史对话" @click="historyCollapsed = false"><template #icon><icon-solar:hamburger-menu-linear /></template></NButton>
          <div><h1>{{ currentSession?.title || '农业问答' }}</h1><p>农业知识库与图谱增强问答</p></div>
        </div>
        <div class="chat-controls">
          <div class="control-field"><span>知识范围</span><NSelect v-model:value="cropScope" :options="scopeOptions" size="small" /></div>
          <div class="chat-global-actions">
            <GlobalSearch />
            <FullScreen v-if="!appStore.isMobile" :full="isFullscreen" @click="toggleFullscreen" />
            <ThemeSchemaSwitch
              :theme-schema="themeStore.themeScheme"
              :is-dark="themeStore.darkMode"
              @switch="themeStore.toggleThemeScheme"
            />
            <UserAvatar />
          </div>
        </div>
      </header>

      <div ref="scrollRef" class="message-scroll">
        <div v-if="!messages.length" class="welcome-block">
          <div class="welcome-icon"><icon-solar:leaf-linear /></div>
          <h2>从一个农业问题开始</h2>
          <p>可询问病害症状、病原、发生条件、防治原则和作物生育期知识。</p>
          <div class="suggestions"><button v-for="item in suggestions" :key="item" type="button" @click="sendQuestion(item)">{{ item }}<icon-solar:arrow-right-linear /></button></div>
        </div>

        <article v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
          <template v-if="message.role === 'user'">
            <div class="user-message"><div class="message-time">你 · {{ formatTime(message.createdAt) }}</div><div class="user-bubble">{{ message.content }}</div></div>
          </template>
          <template v-else>
            <div class="assistant-avatar"><icon-solar:leaf-linear /></div>
            <div class="assistant-message">
              <div class="message-heading"><b>AgriGraph</b><NTag v-if="answerModeLabel(message.answer?.answerMode)" size="tiny" :bordered="false" :type="message.answer?.answerMode === 'KNOWLEDGE_RAG' ? 'success' : 'warning'">{{ answerModeLabel(message.answer?.answerMode) }}</NTag><span>{{ formatTime(message.createdAt) }}</span></div>
              <div class="answer-content" v-html="renderedContent(message)"></div>
              <div v-if="loading && message.id === messages[messages.length-1]?.id && !message.content" class="loading-step"><icon-eos-icons:three-dots-loading />{{ loadingLabel }}</div>
              <NCollapse v-if="message.answer?.workflow?.length" arrow-placement="right" class="process-collapse">
                <NCollapseItem name="process">
                  <template #header><span class="process-title"><icon-solar:branching-paths-down-linear />处理过程</span></template>
                  <div class="process-grid"><span v-for="step in message.answer.workflow" :key="step"><icon-solar:check-circle-linear />{{ workflowLabels[step] || step }}</span></div>
                </NCollapseItem>
              </NCollapse>
              <NCollapse v-if="message.answer?.agentEvents?.length" arrow-placement="right" class="process-collapse agent-process">
                <NCollapseItem name="agents">
                  <template #header><span class="process-title"><icon-solar:cpu-linear />Agent 协作轨迹</span></template>
                  <AgentTimeline :events="message.answer.agentEvents" compact />
                  <div class="trace-meta"><span>运行 ID {{ message.answer.agentRunId?.slice(0, 8) }}</span><span>{{ message.answer.modelCalls || 0 }} 次模型调用 · {{ message.answer.toolCalls || 0 }} 次工具调用</span><RouterLink to="/agent-runs">查看全部运行</RouterLink></div>
                </NCollapseItem>
              </NCollapse>
              <div v-if="message.answer" class="answer-footer">
                <div class="answer-actions">
                  <button type="button" title="复制回答" @click="copyAnswer(message.content)"><icon-solar:copy-linear /></button>
                  <button v-if="!loading" type="button" title="重新生成" @click="regenerate(messages.indexOf(message))"><icon-solar:restart-linear />重新生成</button>
                </div>
              </div>
            </div>
          </template>
        </article>

      </div>

      <div class="composer-wrap">
        <div class="composer">
          <textarea v-model="question" rows="2" placeholder="描述作物、部位、症状和发生环境，问题会更容易准确检索" @keydown="handleKeydown" />
          <div class="composer-footer"><span><icon-solar:shield-check-linear />不会在缺少来源时生成具体农药用量</span><div><small>{{ loading ? loadingLabel : 'Enter 发送' }}</small><NButton v-if="loading" type="error" circle title="停止生成" @click="stopGeneration"><template #icon><icon-solar:stop-circle-linear /></template></NButton><NButton v-else type="primary" circle :disabled="!question.trim()" title="发送问题" @click="sendQuestion()"><template #icon><icon-solar:arrow-up-linear /></template></NButton></div></div>
        </div>
      </div>
    </main>

  </div>
</template>

<style scoped lang="scss">
.chat-page{position:relative}
.chat-page{height:calc(100vh - 112px);min-height:640px;display:grid;grid-template-columns:252px minmax(0,1fr);overflow:hidden;border:1px solid #dce5df;border-radius:6px;background:#fff;color:#1d2922}.chat-page.history-collapsed{grid-template-columns:0 minmax(0,1fr)}.history-panel{position:relative;min-width:0;display:flex;flex-direction:column;overflow:hidden;border-right:1px solid #dce5df;background:#f6f8f6;transition:width .2s}.history-collapsed .history-panel{visibility:hidden}.history-header{display:flex;flex-direction:column;gap:10px;padding:14px;border-bottom:1px solid #e0e7e2}.history-list{min-height:0;flex:1;overflow-y:auto;padding:10px}.history-label{padding:4px 8px 8px;color:#849087;font-size:12px}.history-item{width:100%;display:grid;grid-template-columns:22px minmax(0,1fr) 24px;align-items:center;gap:7px;margin-bottom:3px;padding:10px 8px;border:0;border-radius:5px;background:transparent;color:#4e5b53;text-align:left;cursor:pointer}.history-item:hover,.history-item.active{background:#e5eee8;color:#205f3b}.history-item>span{min-width:0;display:flex;flex-direction:column}.history-item b{overflow:hidden;font-size:13px;font-weight:600;text-overflow:ellipsis;white-space:nowrap}.history-item small{margin-top:3px;color:#8a958e;font-size:11px}.history-item i{display:grid;place-items:center;font-style:normal}.collapse-history{position:absolute;right:10px;bottom:10px;border:0;background:transparent;color:#718078;cursor:pointer}.conversation-panel{min-width:0;display:flex;flex-direction:column;background:#fff}.chat-toolbar{min-height:64px;display:flex;align-items:center;justify-content:space-between;padding:8px 18px;border-bottom:1px solid #dce5df}.conversation-title{min-width:0;display:flex;align-items:center;gap:8px}.conversation-title h1{max-width:390px;overflow:hidden;margin:0;font-size:16px;text-overflow:ellipsis;white-space:nowrap}.conversation-title p{margin:3px 0 0;color:#7b8780;font-size:11px}.chat-controls{display:flex;align-items:center;gap:14px}.control-field{display:flex;align-items:center;gap:7px;color:#6c7971;font-size:12px}.control-field .n-select{width:112px}.switch-field{padding-left:14px;border-left:1px solid #e0e6e2}.settings-popover{width:260px}.settings-popover p{margin:8px 0 0;color:#637068;line-height:1.6}.message-scroll{min-height:0;flex:1;overflow-y:auto;padding:26px max(26px,calc((100% - 820px)/2)) 120px;background:#fbfcfb}.welcome-block{max-width:720px;margin:90px auto 0;text-align:center}.welcome-icon{width:48px;height:48px;display:grid;place-items:center;margin:auto;border-radius:50%;background:#e5efe8;color:#286a43;font-size:26px}.welcome-block h2{margin:15px 0 6px;font-size:22px}.welcome-block>p{color:#718078}.suggestions{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:24px}.suggestions button{display:flex;align-items:center;justify-content:space-between;min-height:64px;padding:10px 12px;border:1px solid #dce5df;border-radius:6px;background:#fff;color:#45534a;text-align:left;cursor:pointer}.suggestions button:hover{border-color:#4a7e5c;color:#205f3b}.message-row{display:flex;margin-bottom:28px}.message-row.user{justify-content:flex-end}.user-message{max-width:min(72%,680px)}.message-time{margin:0 4px 6px;text-align:right;color:#8b958f;font-size:11px}.user-bubble{padding:11px 15px;border-radius:8px 8px 2px 8px;background:#e8eeea;color:#26342b;line-height:1.7;white-space:pre-wrap}.assistant-avatar{width:34px;height:34px;flex:0 0 34px;display:grid;place-items:center;margin-right:12px;border-radius:50%;background:#e4eee7;color:#276a44;font-size:19px}.assistant-message{min-width:0;max-width:820px;flex:1}.message-heading{display:flex;align-items:center;gap:8px;margin-bottom:8px}.message-heading b{font-size:13px}.message-heading span{color:#8a958e;font-size:11px}.answer-content{font-size:15px;line-height:1.82}.answer-content :deep(p:first-child){margin-top:0}.answer-content :deep(.inline-citation){display:inline;padding:0 3px;border:0;background:transparent;color:#247149;font-weight:700;cursor:pointer}.answer-content :deep(.inline-citation:hover){text-decoration:underline}.process-collapse{margin-top:12px;padding:0 10px;border:1px solid #e2e8e4;border-radius:5px;background:#fafbfa}.process-title{display:inline-flex;align-items:center;gap:6px;color:#58675e;font-size:12px}.process-grid{display:flex;flex-wrap:wrap;gap:8px;padding-bottom:10px}.process-grid span{display:inline-flex;align-items:center;gap:4px;color:#66746b;font-size:12px}.process-grid svg{color:#3d7b53}.answer-footer{display:flex;align-items:center;justify-content:space-between;margin-top:10px;padding-top:8px;border-top:1px solid #edf1ee}.answer-status,.answer-actions{display:flex;align-items:center;gap:9px}.answer-status>span{color:#87928b;font-size:11px}.answer-actions button{display:inline-flex;align-items:center;gap:5px;border:0;background:transparent;color:#68766d;font-size:12px;cursor:pointer}.answer-actions button:hover{color:#276b43}.loading-step{display:flex;align-items:center;gap:8px;color:#65736a;font-size:13px}.loading-step svg{font-size:24px;color:#2f7048}.composer-wrap{position:absolute;right:max(26px,calc((100% - 252px - 820px)/2));bottom:16px;left:calc(252px + max(26px,calc((100% - 252px - 820px)/2)));z-index:3}.history-collapsed .composer-wrap{left:max(26px,calc((100% - 820px)/2));right:max(26px,calc((100% - 820px)/2))}.composer{padding:11px 13px;border:1px solid #bfcfc4;border-radius:8px;background:#fff;box-shadow:0 6px 22px rgba(35,62,44,.12)}.composer textarea{width:100%;resize:none;border:0;outline:0;background:transparent;color:#26332b;line-height:1.55}.composer-footer{display:flex;align-items:center;justify-content:space-between;color:#7f8b83;font-size:11px}.composer-footer>span,.composer-footer>div{display:flex;align-items:center;gap:7px}.source-summary{display:grid;grid-template-columns:repeat(3,1fr);margin-bottom:16px;border:1px solid #e0e7e2;border-radius:5px}.source-summary span{display:flex;flex-direction:column;padding:10px;text-align:center;color:#7b8780;font-size:11px}.source-summary b{color:#276842;font-size:18px}.source-card,.graph-source{margin-bottom:10px;padding:13px;border:1px solid #dfe7e1;border-radius:6px;background:#fff}.source-card.active{border-color:#2f7048;box-shadow:0 0 0 2px rgba(47,112,72,.1)}.source-card-heading{display:flex;gap:8px}.source-card-heading>b{color:#2a6e46}.source-card p,.graph-source p{color:#5e6d64;font-size:13px;line-height:1.65}.source-card>div:last-child{display:flex;justify-content:space-between;color:#8a958e;font-size:11px}.source-card a{display:inline-flex;align-items:center;gap:3px;color:#286b44}.graph-source>div{display:flex;flex-wrap:wrap;gap:6px}.graph-source>div span{padding:3px 7px;border-radius:3px;background:#e7efe9;color:#326345;font-size:12px}.graph-source small{color:#87928b}
@media(max-width:900px){.chat-page{grid-template-columns:0 1fr}.history-panel{visibility:hidden}.composer-wrap,.history-collapsed .composer-wrap{left:18px;right:18px}.conversation-title .n-button{display:flex}.chat-controls .control-field>span{display:none}.suggestions{grid-template-columns:1fr}.message-scroll{padding-left:18px;padding-right:18px}.history-collapsed .history-panel{visibility:hidden}}@media(max-width:560px){.chat-page{height:calc(100vh - 72px);min-height:520px}.conversation-title p,.switch-field{display:none}.chat-toolbar{padding:8px 10px}.control-field .n-select{width:105px}.message-scroll{padding-top:18px}.user-message{max-width:88%}.answer-status>span{display:none}.answer-footer{align-items:flex-start}.composer-footer>span{display:none}}
.chat-page{height:calc(100vh - 32px);min-height:0}
.conversation-panel{min-height:0}
.chat-toolbar{min-height:60px;padding:6px 14px}
.chat-controls{gap:10px}
.chat-global-actions{display:flex;align-items:center;gap:2px;padding-left:10px;border-left:1px solid #e0e6e2}
.message-scroll{padding-bottom:24px}
.composer-wrap,.history-collapsed .composer-wrap{position:static;left:auto;right:auto;bottom:auto;z-index:auto;flex:0 0 auto;padding:12px max(26px,calc((100% - 820px)/2)) 14px;background:#fbfcfb}
.answer-footer{justify-content:flex-end}
@media(max-width:900px){.composer-wrap,.history-collapsed .composer-wrap{padding:10px 18px 12px}.chat-global-actions{padding-left:5px}}
@media(max-width:560px){.chat-page{height:calc(100vh - 32px);min-height:0}.chat-global-actions>*:not(:last-child){display:none}.composer-wrap,.history-collapsed .composer-wrap{padding:8px 10px 10px}}
.chat-page,.conversation-panel,.composer,.suggestions button{background:var(--agri-surface);color:var(--agri-text);border-color:var(--agri-border)}
.history-panel,.message-scroll,.composer-wrap,.process-collapse{background:var(--agri-surface-soft);border-color:var(--agri-border)}
.chat-toolbar,.history-header,.answer-footer{border-color:var(--agri-border)}
.history-item{color:var(--agri-text-secondary)}.history-item:hover,.history-item.active{background:var(--agri-surface-active);color:var(--agri-primary)}
.conversation-title p,.message-heading span,.history-item small,.composer-footer{color:var(--agri-text-muted)}
.user-bubble{background:var(--agri-surface-active);color:var(--agri-text)}.assistant-avatar,.welcome-icon{background:var(--agri-primary-soft);color:var(--agri-primary)}
.composer textarea{color:var(--agri-text)}
.trace-meta{display:flex;flex-wrap:wrap;gap:12px;padding:9px 0;border-top:1px solid var(--agri-border);color:var(--agri-text-muted);font-size:11px}.trace-meta a{margin-left:auto;color:var(--agri-primary)}
</style>
