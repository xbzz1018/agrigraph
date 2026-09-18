<script setup lang="ts">
export interface AgentTraceEvent {
  sequence?: number;
  agentId?: string;
  agent_id?: string;
  eventType?: string;
  event_type?: string;
  status: string;
  label: string;
  timestamp: string;
  durationMs?: number | null;
  duration_ms?: number | null;
}

const props = withDefaults(defineProps<{ events: AgentTraceEvent[]; compact?: boolean }>(), { compact: false });

const roles: Record<string, { label: string; icon: string }> = {
  supervisor: { label: '任务规划', icon: 'solar:branching-paths-down-linear' },
  triage: { label: '问题分诊', icon: 'solar:filter-linear' },
  memory: { label: '会话记忆', icon: 'solar:history-linear' },
  'document-research': { label: '文档检索', icon: 'solar:documents-linear' },
  'graph-reasoning': { label: '图谱推理', icon: 'solar:share-circle-linear' },
  'vision-diagnosis': { label: '视觉诊断', icon: 'solar:camera-linear' },
  'answer-composer': { label: '回答生成', icon: 'solar:pen-new-square-linear' },
  'evidence-verifier': { label: '证据核验', icon: 'solar:verified-check-linear' },
  'safety-reviewer': { label: '安全审查', icon: 'solar:shield-check-linear' },
  finalizer: { label: '完成', icon: 'solar:check-circle-linear' }
};

function agentId(event: AgentTraceEvent) {
  return event.agentId || event.agent_id || 'agent';
}

function eventType(event: AgentTraceEvent) {
  return event.eventType || event.event_type || '';
}

const visibleEvents = computed(() => {
  // 同一 Agent 通常先 started 后 completed；列表保留最新状态，避免显示成两个重复节点。
  const byStep = new Map<string, AgentTraceEvent>();
  for (const event of props.events) {
    const id = agentId(event);
    const current = byStep.get(id);
    if (!current || eventType(event) !== 'started') byStep.set(id, event);
  }
  return [...byStep.values()].sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
});

function statusType(status: string) {
  if (['COMPLETED', 'SUCCESS', 'PUBLISHED'].includes(status)) return 'success';
  if (['FAILED', 'REJECTED', 'BLOCKED'].includes(status)) return 'error';
  if (['RUNNING', 'STARTED'].includes(status)) return 'info';
  return 'warning';
}

function duration(event: AgentTraceEvent) {
  const value = event.durationMs ?? event.duration_ms;
  return value == null ? '' : `${value} ms`;
}
</script>

<template>
  <div class="agent-timeline" :class="{ compact }">
    <div v-for="event in visibleEvents" :key="`${agentId(event)}-${event.sequence || event.timestamp}`" class="agent-node">
      <div class="node-icon">
        <SvgIcon :icon="roles[agentId(event)]?.icon || 'solar:cpu-linear'" />
      </div>
      <div class="node-copy">
        <b>{{ roles[agentId(event)]?.label || agentId(event) }}</b>
        <span>{{ event.label }}</span>
      </div>
      <div class="node-status">
        <NTag :type="statusType(event.status)" size="tiny" :bordered="false">{{ event.status }}</NTag>
        <small>{{ duration(event) }}</small>
      </div>
    </div>
    <NEmpty v-if="!visibleEvents.length" size="small" description="暂无 Agent 执行事件" />
  </div>
</template>

<style scoped lang="scss">
.agent-timeline{display:flex;flex-direction:column}.agent-node{position:relative;min-height:54px;display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:10px;padding:7px 0}.agent-node:not(:last-child)::after{position:absolute;top:39px;bottom:-15px;left:15px;width:1px;background:var(--agri-border);content:''}.node-icon{z-index:1;width:30px;height:30px;display:grid;place-items:center;border:1px solid var(--agri-border);border-radius:50%;background:var(--agri-surface);color:var(--agri-primary);font-size:17px}.node-copy{min-width:0;display:flex;flex-direction:column}.node-copy b{font-size:13px}.node-copy span{overflow:hidden;margin-top:2px;color:var(--agri-text-muted);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.node-status{display:flex;align-items:flex-end;flex-direction:column;gap:3px}.node-status small{color:var(--agri-text-muted);font-size:10px}.compact{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:7px}.compact .agent-node{min-height:48px;padding:7px;border:1px solid var(--agri-border);background:var(--agri-surface-soft)}.compact .agent-node::after{display:none}@media(max-width:640px){.compact{grid-template-columns:1fr}.agent-node{grid-template-columns:30px minmax(0,1fr)}}
</style>
