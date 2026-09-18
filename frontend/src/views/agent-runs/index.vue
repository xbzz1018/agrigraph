<script setup lang="tsx">
import { NButton, NTag } from 'naive-ui';
import { useWindowSize } from '@vueuse/core';
import AgentTimeline from '@/components/agent/agent-timeline.vue';
import type { AgentTraceEvent } from '@/components/agent/agent-timeline.vue';

interface AgentRun {
  id: string; ownerUsername: string; threadId: string; requestType: string; objective: string;
  cropScope: string; status: string; startedAt: string; finishedAt?: string; durationMs?: number;
  modelCalls: number; toolCalls: number;
  result?: {
    answer?: string; warnings?: string[]; modelUsed?: string; promptVersion?: string;
    modelUsage?: { inputTokens?: number; outputTokens?: number; totalTokens?: number; pricingConfigured?: boolean };
    estimatedCostUsd?: number;
  };
  steps?: Array<{ id:string; agent_id:string; status:string; label:string; duration_ms?:number }>;
}

const runs = ref<AgentRun[]>([]);
const loading = ref(false);
const status = ref('');
const drawer = ref(false);
const detail = ref<AgentRun | null>(null);
const events = ref<AgentTraceEvent[]>([]);
const detailLoading = ref(false);
const authStore = useAuthStore();
const { width: viewportWidth } = useWindowSize();
const drawerWidth = computed(() => Math.min(viewportWidth.value, 640));
const descriptionColumns = computed(() => viewportWidth.value <= 640 ? 1 : 2);
const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '运行中', value: 'RUNNING' },
  { label: '已完成', value: 'COMPLETED' },
  { label: '等待审批', value: 'WAITING_APPROVAL' },
  { label: '已取消', value: 'CANCELED' },
  { label: '失败', value: 'FAILED' }
];
const statusType = (value: string) => value === 'COMPLETED'
  ? 'success'
  : value === 'FAILED' || value === 'REJECTED' ? 'error' : value === 'RUNNING' ? 'info' : 'warning';
const time = (value?: string) => value ? dayjs(value).format('MM-DD HH:mm:ss') : '--';
const cost = (value?: number, configured?: boolean) => configured ? `$${(value || 0).toFixed(6)}` : '未配置单价';

async function load() {
  loading.value = true;
  const { data } = await request<AgentRun[]>({ url: '/agent-runs', params: { status: status.value || undefined } });
  runs.value = data || [];
  loading.value = false;
}

async function openRun(row: AgentRun) {
  drawer.value = true;
  detailLoading.value = true;
  // 详情和事件互不依赖，并行加载可以明显缩短时间线抽屉的等待时间。
  const [runResult, eventResult] = await Promise.all([
    request<AgentRun>({ url: `/agent-runs/${row.id}` }),
    request<AgentTraceEvent[]>({ url: `/agent-runs/${row.id}/events` })
  ]);
  detail.value = runResult.data || null;
  events.value = eventResult.data || [];
  detailLoading.value = false;
}

async function cancelRun(row: AgentRun) {
  const { error } = await request({ url: `/agent-runs/${row.id}/cancel`, method: 'POST' });
  if (!error) window.$message?.success('已提交取消请求');
  await load();
  if (detail.value?.id === row.id) await openRun(row);
}

async function replayRun(row: AgentRun) {
  const { data, error } = await request<{ agentRunId: string }>({
    url: `/agent-runs/${row.id}/replay`,
    method: 'POST'
  });
  if (!error) {
    window.$message?.success(`回放已完成：${data?.agentRunId || ''}`);
    await load();
  }
}
const columns=[
 {title:'目标',key:'objective',minWidth:300,render:(row:AgentRun)=><div class="objective"><b>{row.objective}</b><span>{row.requestType} · {row.cropScope} · {row.id.slice(0,8)}</span></div>},
 {title:'状态',key:'status',width:120,render:(row:AgentRun)=><NTag size="small" bordered={false} type={statusType(row.status) as any}>{row.status}</NTag>},
 {title:'调用',key:'calls',width:110,render:(row:AgentRun)=>`${row.modelCalls} 模型 / ${row.toolCalls} 工具`},
 {title:'耗时',key:'durationMs',width:90,render:(row:AgentRun)=>row.durationMs==null?'--':`${row.durationMs} ms`},
 {title:'开始时间',key:'startedAt',width:145,render:(row:AgentRun)=>time(row.startedAt)},
 {title:'操作',key:'actions',width:180,render:(row:AgentRun)=><div class="actions"><NButton text type="primary" onClick={()=>openRun(row)}>详情</NButton><NButton text type="error" disabled={!['RUNNING','WAITING_APPROVAL'].includes(row.status)} onClick={()=>cancelRun(row)}>取消</NButton>{authStore.isAdmin&&<NButton text onClick={()=>replayRun(row)}>回放</NButton>}</div>}
];
watch(status, load);
onMounted(load);
</script>

<template>
  <div class="runs-page">
    <header><div><h1>Agent 运行</h1><p>查看多智能体协作轨迹、预算消耗和异常状态</p></div><NButton secondary :loading="loading" @click="load"><template #icon><icon-solar:refresh-linear/></template>刷新</NButton></header>
    <section class="run-table"><div class="filters"><NSelect v-model:value="status" :options="statusOptions"/><span>{{runs.length}} 次运行</span></div><NDataTable :columns="columns" :data="runs" :loading="loading" :single-line="false" :scroll-x="980"/></section>
    <NDrawer v-model:show="drawer" :width="drawerWidth"><NDrawerContent title="Agent 运行详情" closable><NSpin :show="detailLoading"><template v-if="detail"><div class="detail-head"><div><b>{{detail.objective}}</b><span>{{detail.id}}</span></div><NTag :type="statusType(detail.status)">{{detail.status}}</NTag></div><NDescriptions :column="descriptionColumns" bordered size="small"><NDescriptionsItem label="类型">{{detail.requestType}}</NDescriptionsItem><NDescriptionsItem label="作物">{{detail.cropScope}}</NDescriptionsItem><NDescriptionsItem label="模型调用">{{detail.modelCalls}}</NDescriptionsItem><NDescriptionsItem label="工具调用">{{detail.toolCalls}}</NDescriptionsItem><NDescriptionsItem label="回答模型">{{detail.result?.modelUsed || '--'}}</NDescriptionsItem><NDescriptionsItem label="Token">{{detail.result?.modelUsage?.totalTokens ?? 0}}</NDescriptionsItem><NDescriptionsItem label="估算成本">{{cost(detail.result?.estimatedCostUsd, detail.result?.modelUsage?.pricingConfigured)}}</NDescriptionsItem><NDescriptionsItem label="提示版本"><code class="prompt-version" :title="detail.result?.promptVersion">{{detail.result?.promptVersion || '--'}}</code></NDescriptionsItem><NDescriptionsItem label="开始">{{time(detail.startedAt)}}</NDescriptionsItem><NDescriptionsItem label="耗时">{{detail.durationMs??'--'}} ms</NDescriptionsItem></NDescriptions><div class="detail-actions"><NButton type="error" secondary :disabled="!['RUNNING','WAITING_APPROVAL'].includes(detail.status)" @click="cancelRun(detail)"><template #icon><icon-solar:stop-circle-linear/></template>取消运行</NButton><NButton v-if="authStore.isAdmin" secondary @click="replayRun(detail)"><template #icon><icon-solar:restart-linear/></template>重新回放</NButton></div><h3>协作 DAG</h3><div class="dag"><div class="dag-row"><span>Supervisor</span></div><div class="dag-arrow">↓</div><div class="dag-row parallel"><span>Memory</span><span>Document</span><span>Graph</span><span v-if="detail.requestType==='diagnosis'">Vision</span></div><div class="dag-arrow">↓</div><div class="dag-row"><span>Composer → Evidence → Safety</span></div></div><h3>执行时间线</h3><AgentTimeline :events="events"/><template v-if="detail.result?.answer"><h3>运行结果</h3><div class="run-result">{{detail.result.answer}}</div></template></template></NSpin></NDrawerContent></NDrawer>
  </div>
</template>

<style scoped lang="scss">
.runs-page{max-width:100%;overflow-x:hidden;color:var(--agri-text)}header{display:flex;align-items:center;justify-content:space-between}h1{margin:0;font-size:22px;letter-spacing:0}header p{margin:4px 0 18px;color:var(--agri-text-secondary)}.run-table{max-width:100%;overflow:hidden;padding:14px;border:1px solid var(--agri-border);background:var(--agri-surface)}.filters{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;color:var(--agri-text-muted);font-size:12px}.filters .n-select{width:180px}.objective{display:flex;flex-direction:column}.objective span,.detail-head span{margin-top:3px;color:var(--agri-text-muted);font-size:11px}.actions,.detail-actions{display:flex;gap:12px}.detail-head{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px}.detail-head>div{min-width:0;display:flex;flex-direction:column}.detail-head b{font-size:16px}.detail-actions{margin:14px 0}.prompt-version{display:block;max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}h3{margin:20px 0 10px;font-size:15px}.dag{padding:14px;border:1px solid var(--agri-border);background:var(--agri-surface-soft);text-align:center}.dag-row{display:flex;justify-content:center;gap:8px}.dag-row span{min-width:130px;padding:7px 10px;border:1px solid var(--agri-border);background:var(--agri-surface);font-size:12px}.dag-row.parallel{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr))}.dag-row.parallel span{min-width:0}.dag-arrow{height:24px;color:var(--agri-text-muted);line-height:24px}.run-result{padding:12px;border-left:3px solid var(--agri-primary);background:var(--agri-surface-soft);line-height:1.7;white-space:pre-wrap}@media(max-width:640px){header p{display:none}.run-table{padding:8px}.dag-row.parallel{grid-template-columns:1fr}}
</style>
