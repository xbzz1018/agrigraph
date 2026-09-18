<script setup lang="ts">
import type { UploadFileInfo } from 'naive-ui';
import MarkdownIt from 'markdown-it';

interface DiagnosisResult {
  answer: string;
  observation?: { crop: string; plantParts: string[]; symptoms: string[]; qualityWarnings: string[] };
  candidateEntities: { name?: string; id?: string; score?: number }[];
  citations: { id: string; title: string; excerpt: string }[];
  controlOptions: { name: string; type: string }[];
  warnings: string[];
  agentRunId: string;
}

const crop = ref('番茄');
const file = ref<File | null>(null);
const preview = ref('');
const loading = ref(false);
const result = ref<DiagnosisResult | null>(null);
const router = useRouter();
const markdown = new MarkdownIt({ html: false, breaks: true });
const serviceBase = String(import.meta.env.VITE_SERVICE_BASE_URL || '').replace(/\/$/, '');

function mediaUrl(url: string) {
  return url.startsWith('/api/v1') ? `${serviceBase}${url.slice(7)}` : url;
}

function selectFile({ file: info }: { file: UploadFileInfo }) {
  file.value = info.file || null;
  if (preview.value) URL.revokeObjectURL(preview.value);
  preview.value = file.value ? URL.createObjectURL(file.value) : '';
  result.value = null;
}

async function diagnose() {
  if (!file.value) {
    window.$message?.warning('请先选择清晰的作物图片');
    return;
  }
  // 浏览器只把原图放入 multipart；后端会存储图片，但不会把字节写入 Agent state。
  loading.value = true;
  const body = new FormData();
  body.append('image', file.value);
  const { data, error } = await request<DiagnosisResult>({
    url: '/diagnosis/image',
    method: 'POST',
    params: { crop: crop.value },
    data: body,
  timeout: 300000
  });
  if (!error) result.value = data;
  loading.value = false;
}

function askWithSymptoms() {
  const symptoms = result.value?.observation?.symptoms.join('、') || '';
  router.push({
    path: '/chat',
    query: {
      question: `${crop.value}${symptoms ? `出现${symptoms}` : '图片症状不明确'}，请结合知识库分析可能病害和安全防治原则。`
    }
  });
}

const renderedAnswer = computed(() => markdown.render(result.value?.answer || ''));
</script>

<template>
  <div class="diagnosis-page">
    <header><div><h1>图片症状理解</h1><p>提取可见症状后，使用农业知识库召回候选病虫害</p></div><NTag :type="result?'success':'default'">{{ result?'分析完成':'等待图片' }}</NTag></header>
    <div class="steps"><span :class="{active:!result}">1 上传图片</span><i/><span :class="{active:loading}">2 提取可见症状</span><i/><span :class="{active:!!result}">3 检索候选与生成建议</span></div>
    <div class="diagnosis-grid">
      <section class="upload-panel"><div class="section-heading"><h2>田间图片</h2><NSelect v-model:value="crop" :options="[{label:'番茄',value:'番茄'},{label:'水稻',value:'水稻'}]"/></div><NUpload accept="image/jpeg,image/png,image/webp" :max="1" :default-upload="false" @change="selectFile"><NUploadDragger><img v-if="preview" :src="preview" alt="待分析作物图片"/><div v-else class="upload-empty"><icon-solar:camera-add-linear/><b>点击或拖入作物图片</b><span>支持 JPEG、PNG、WebP，单张不超过 10MB</span></div></NUploadDragger></NUpload><NButton type="primary" block size="large" :loading="loading" class="mt-14px" @click="diagnose">{{ loading?'正在联合分析':'开始辅助分析' }}</NButton></section>
      <section class="result-panel"><h2>结构化观察</h2><NEmpty v-if="!result" description="上传图片后显示作物部位、症状与候选病害" class="result-empty"/><template v-else><div class="observation"><span>识别作物</span><b>{{ result.observation?.crop || '未知' }}</b><span>可见部位</span><div><NTag v-for="item in result.observation?.plantParts || []" :key="item" size="small">{{ item }}</NTag></div></div><div class="result-block"><h3>可见症状</h3><div class="tag-list"><NTag v-for="item in result.observation?.symptoms || []" :key="item" type="warning" size="small">{{ item }}</NTag><span v-if="!result.observation?.symptoms.length">未提取到可靠症状</span></div></div><div class="result-block"><h3>候选病害</h3><div v-for="item in result.candidateEntities" :key="item.id || item.name" class="candidate"><b>{{ item.name }}</b><span>{{ item.score ? `${Math.round(item.score * 100)}%` : 'BM25 候选' }}</span></div><span v-if="!result.candidateEntities.length">未形成可靠候选</span></div><NAlert v-if="result.observation?.qualityWarnings.length" type="warning">{{ result.observation.qualityWarnings.join('；') }}</NAlert><NButton secondary class="mt-14px" @click="askWithSymptoms">补充症状并进入农业问答</NButton></template></section>
    </div>
    <template v-if="result"><section class="answer-panel"><div class="section-heading"><h2>知识库综合回答</h2><div class="answer-status"><NButton v-if="result.agentRunId" text type="primary" @click="router.push('/agent-runs')"><template #icon><icon-solar:branching-paths-down-linear/></template>查看运行轨迹</NButton></div></div><div class="answer-content" v-html="renderedAnswer"></div></section></template>
    <NAlert v-if="result?.warnings.length" type="warning" class="mt-14px"><p v-for="item in result.warnings" :key="item">{{ item }}</p></NAlert>
  </div>
</template>

<style scoped lang="scss">
.diagnosis-page{color:var(--agri-text)}header,.section-heading{display:flex;align-items:center;justify-content:space-between}header h1{margin:0;font-size:22px}header p{margin:5px 0 18px;color:var(--agri-text-secondary)}.steps{display:flex;align-items:center;justify-content:center;padding:12px;border:1px solid var(--agri-border);background:var(--agri-surface);color:var(--agri-text-muted)}.steps span.active{color:var(--agri-primary);font-weight:700}.steps i{width:70px;height:1px;margin:0 16px;background:var(--agri-border)}.diagnosis-grid{display:grid;grid-template-columns:minmax(360px,.8fr) minmax(420px,1.2fr);gap:14px;margin-top:14px}.diagnosis-grid>section,.answer-panel,.similar-panel{padding:18px;border:1px solid var(--agri-border);background:var(--agri-surface)}h2{margin:0 0 14px;font-size:17px}.section-heading .n-select{width:110px}.upload-empty{height:280px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:var(--agri-text-muted)}.upload-empty svg{font-size:42px;color:var(--agri-primary)}.upload-empty span{font-size:12px}.n-upload-dragger img{width:100%;height:280px;object-fit:contain}.result-empty{margin-top:110px}.observation{display:grid;grid-template-columns:75px 1fr;align-items:center;gap:9px;margin:12px 0;padding:13px;background:var(--agri-surface-soft)}.observation>span{color:var(--agri-text-muted);font-size:12px}.observation>div,.tag-list{display:flex;flex-wrap:wrap;gap:6px}.result-block{margin-top:12px;padding:13px;border-left:3px solid var(--agri-primary);background:var(--agri-surface-soft)}.result-block h3{margin:0 0 9px;font-size:14px}.candidate{display:grid;grid-template-columns:120px 1fr;align-items:center;gap:10px;margin:8px 0}.observation-note{color:var(--agri-text-secondary);line-height:1.65}.answer-panel,.similar-panel{margin-top:14px}.answer-content{max-width:900px;line-height:1.8}.image-list{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.image-list figure{margin:0;border:1px solid var(--agri-border)}.image-list img{width:100%;aspect-ratio:4/3;display:block;object-fit:cover}.image-list figcaption{overflow:hidden;padding:7px;color:var(--agri-text-secondary);font-size:11px;text-overflow:ellipsis;white-space:nowrap}.n-alert p{margin:2px 0}@media(max-width:800px){header p{display:none}.steps{justify-content:flex-start;overflow-x:auto;white-space:nowrap}.steps i{width:22px;margin:0 8px}.diagnosis-grid{grid-template-columns:1fr}.image-list{grid-template-columns:repeat(2,1fr)}}
.answer-status{display:flex;align-items:center;gap:10px}
</style>
