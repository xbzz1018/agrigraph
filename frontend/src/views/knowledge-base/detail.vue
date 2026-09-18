<script setup lang="ts">
interface ImageItem { id:string;name:string;url:string;sourceDatasetId:string;stage:string;artist:string;license:string;licenseUrl:string;sourcePage:string }
interface Entity { id:string;name:string;crop:string;category:string;categoryLabel:string;summary:string;symptoms:string;pathogen:string;occurrenceFactors:string;controlOptions:{name:string;type:string}[];affectedParts:string[];aliases:string[];images:ImageItem[];doi:string;sourceDatasetId:string }
interface Similar { id:string;name:string;categoryLabel:string;summary:string;score:number;sharedSymptoms:string[];sharedParts:string[];sharedPathogens:string[] }
interface RelationGroup { type:string;label:string;count:number;entities:{id:string;name:string;type:string;typeLabel:string}[] }

const route=useRoute();const router=useRouter();
const entity=ref<Entity|null>(null);const similar=ref<Similar[]>([]);const relations=ref<RelationGroup[]>([]);
const loading=ref(true);const imageIndex=ref(0);const imageFailed=ref(false);
const serviceBase=String(import.meta.env.VITE_SERVICE_BASE_URL||'').replace(/\/$/,'');
const currentImage=computed(()=>entity.value?.images?.[imageIndex.value]);
function mediaUrl(url?:string){return url?.startsWith('/api/v1')?`${serviceBase}${url.slice(7)}`:url}

async function load(){
  loading.value=true;const id=String(route.params.id||'');
  const [detailResult,similarResult,relationResult]=await Promise.all([
    request<Entity>({url:`/agriculture/entities/${id}`}),
    request<Similar[]>({url:`/agriculture/entities/${id}/similar`,params:{limit:6}}),
    request<RelationGroup[]>({url:`/agriculture/entities/${id}/relations`})
  ]);
  entity.value=detailResult.data||null;similar.value=similarResult.data||[];relations.value=relationResult.data||[];
  imageIndex.value=0;imageFailed.value=false;loading.value=false;
}
function nextImage(step:number){if(!entity.value?.images.length)return;imageIndex.value=(imageIndex.value+step+entity.value.images.length)%entity.value.images.length;imageFailed.value=false}
function goGraph(){if(entity.value)router.push({path:'/knowledge-graph',query:{mode:'entity',id:entity.value.id,crop:entity.value.crop}})}
function ask(){if(entity.value)router.push({path:'/chat',query:{question:`请介绍${entity.value.name}的症状、发生条件和防治原则`}})}
function addCompare(){
  if(!entity.value)return;const key='agrigraph-compare-ids';const ids=JSON.parse(sessionStorage.getItem(key)||'[]') as string[];
  if(!ids.includes(entity.value.id))ids.push(entity.value.id);sessionStorage.setItem(key,JSON.stringify(ids.slice(-3)));
  router.push({path:'/knowledge-base',query:{crop:entity.value.crop,compare:'1'}});
}
watch(()=>route.params.id,load);onMounted(load);
</script>

<template>
  <div class="detail-page">
    <div class="detail-toolbar"><NButton text @click="router.push('/knowledge-base')"><template #icon><icon-solar:arrow-left-linear /></template>返回目录</NButton><span v-if="entity">{{ entity.crop }} / {{ entity.categoryLabel }}</span></div>
    <NSpin :show="loading">
      <template v-if="entity">
        <header class="entity-heading">
          <div><div class="type-line"><NTag size="small" :bordered="false" :type="entity.category==='Disease'?'error':'warning'">{{ entity.categoryLabel }}</NTag><span>{{ entity.crop }}</span></div><h1>{{ entity.name }}</h1><p>{{ entity.summary||`${entity.name}的规范化农业知识条目。` }}</p><div class="heading-actions"><NButton type="primary" @click="goGraph"><template #icon><icon-solar:share-circle-linear /></template>在图谱中查看</NButton><NButton secondary @click="ask"><template #icon><icon-solar:chat-round-dots-linear /></template>围绕该病害提问</NButton><NButton secondary @click="addCompare"><template #icon><icon-solar:add-square-linear /></template>加入对比</NButton></div></div>
          <div class="image-viewer">
            <img v-if="currentImage&&!imageFailed" :src="mediaUrl(currentImage.url)" :alt="entity.name" @error="imageFailed=true" />
            <div v-else class="image-empty"><icon-solar:gallery-wide-linear /><b>暂无已核验病害图片</b><span>不会使用作物或物候图片代替</span></div>
            <template v-if="entity.images.length"><button type="button" class="prev" title="上一张" @click="nextImage(-1)"><icon-solar:alt-arrow-left-linear /></button><button type="button" class="next" title="下一张" @click="nextImage(1)"><icon-solar:alt-arrow-right-linear /></button><span class="image-count">{{ imageIndex+1 }} / {{ entity.images.length }}</span></template>
          </div>
        </header>

        <section class="knowledge-grid">
          <article><h2>典型症状</h2><p>{{ entity.symptoms||'暂无规范化症状描述。' }}</p></article>
          <article><h2>病原或致害信息</h2><p>{{ entity.pathogen||(entity.category==='Pest'?'详见虫害形态与习性资料。':'暂无规范化病原描述。') }}</p></article>
          <article><h2>发生条件</h2><p>{{ entity.occurrenceFactors||'暂无规范化发生条件。' }}</p></article>
          <article><h2>防治选项</h2><p>{{ entity.controlOptions?.map(item => item.name).join('、')||'暂无规范化防治选项。' }}</p></article>
        </section>

        <section class="relation-section"><header><h2>关联知识</h2><span>点击“在图谱中查看”探索完整关系</span></header><div class="relation-groups"><div v-for="group in relations" :key="group.type"><b>{{ group.label }} · {{ group.count }}</b><span>{{ group.entities.slice(0,6).map(item=>item.name).join('、')||'待补充' }}</span></div></div></section>

        <section v-if="similar.length" class="similar-section"><header><h2>相似条目</h2><span>按共享症状、部位和病原计算</span></header><div class="similar-list"><button v-for="item in similar" :key="item.id" type="button" @click="router.push(`/knowledge-base/${item.id}`)"><span><b>{{ item.name }}</b><small>相似度 {{ Math.round(item.score*100) }}%</small></span><em v-if="item.sharedSymptoms.length">共同症状：{{ item.sharedSymptoms.slice(0,3).join('、') }}</em><em v-else-if="item.sharedParts.length">共同部位：{{ item.sharedParts.join('、') }}</em><icon-solar:alt-arrow-right-linear /></button></div></section>

        <footer class="entity-meta"><span><b>危害部位</b>{{ entity.affectedParts.join('、')||'待补充' }}</span><span><b>别名</b>{{ entity.aliases.join('、')||'无' }}</span><span><b>核验图片</b>{{ entity.images.length }} 张</span><span><b>来源数据集</b>{{ entity.sourceDatasetId||'公开农业资料' }}</span></footer>
      </template>
      <NEmpty v-else-if="!loading" description="未找到该病虫害条目" />
    </NSpin>
  </div>
</template>

<style scoped lang="scss">
.detail-page{color:var(--agri-text)}.detail-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;color:var(--agri-text-muted)}.entity-heading{display:grid;grid-template-columns:minmax(0,1fr) 420px;gap:38px;padding:28px 30px;border:1px solid var(--agri-border);background:var(--agri-surface)}.type-line{display:flex;align-items:center;gap:9px;color:var(--agri-text-muted)}.entity-heading h1{margin:12px 0 8px;font-size:30px}.entity-heading p{max-width:800px;margin:0;color:var(--agri-text-secondary);font-size:15px;line-height:1.8}.heading-actions{display:flex;flex-wrap:wrap;gap:9px;margin-top:22px}.image-viewer{position:relative;height:260px;overflow:hidden;border:1px solid var(--agri-border);background:var(--agri-surface-soft)}.image-viewer img{width:100%;height:100%;object-fit:cover}.image-empty{height:100%;display:grid;place-content:center;justify-items:center;gap:7px;color:var(--agri-text-muted)}.image-empty svg{font-size:42px}.image-empty span{font-size:12px}.image-viewer>button{position:absolute;top:50%;width:34px;height:34px;display:grid;place-items:center;transform:translateY(-50%);border:0;background:rgba(20,35,25,.68);color:#fff;cursor:pointer}.image-viewer .prev{left:8px}.image-viewer .next{right:8px}.image-count{position:absolute;right:9px;bottom:9px;padding:3px 7px;background:rgba(20,35,25,.68);color:#fff;font-size:11px}.detail-page>.n-alert{margin-top:12px}.knowledge-grid{display:grid;grid-template-columns:1fr 1fr;margin-top:16px;border-top:1px solid var(--agri-border);border-left:1px solid var(--agri-border)}.knowledge-grid article{min-height:220px;padding:22px 26px;border-right:1px solid var(--agri-border);border-bottom:1px solid var(--agri-border);background:var(--agri-surface)}.knowledge-grid h2,.relation-section h2,.similar-section h2{margin:0;font-size:17px}.knowledge-grid p{max-height:190px;overflow:auto;margin:12px 0 0;color:var(--agri-text-secondary);line-height:1.8;white-space:pre-line}.relation-section,.similar-section{margin-top:16px;padding:22px 26px;border:1px solid var(--agri-border);background:var(--agri-surface)}.relation-section>header,.similar-section>header{display:flex;align-items:center;justify-content:space-between;color:var(--agri-text-muted)}.relation-groups{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:16px;border-top:1px solid var(--agri-border);border-left:1px solid var(--agri-border)}.relation-groups>div{min-height:92px;padding:14px;border-right:1px solid var(--agri-border);border-bottom:1px solid var(--agri-border)}.relation-groups span{display:block;margin-top:7px;color:var(--agri-text-secondary);line-height:1.55}.similar-list{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:16px}.similar-list button{display:grid;grid-template-columns:1fr auto;gap:8px;min-height:90px;padding:14px;border:1px solid var(--agri-border);background:transparent;color:var(--agri-text);text-align:left;cursor:pointer}.similar-list button:hover{border-color:var(--agri-primary)}.similar-list span{display:flex;flex-direction:column}.similar-list small{margin-top:4px;color:var(--agri-primary)}.similar-list em{grid-column:1/-1;color:var(--agri-text-secondary);font-size:12px;font-style:normal}.entity-meta{display:grid;grid-template-columns:repeat(4,1fr);margin-top:16px;border:1px solid var(--agri-border);background:var(--agri-surface-soft)}.entity-meta span{padding:14px;color:var(--agri-text-secondary);border-right:1px solid var(--agri-border)}.entity-meta b{display:block;margin-bottom:5px;color:var(--agri-text);font-size:12px}@media(max-width:1000px){.entity-heading{grid-template-columns:1fr}.image-viewer{max-width:620px}.relation-groups,.similar-list{grid-template-columns:1fr 1fr}.entity-meta{grid-template-columns:1fr 1fr}}@media(max-width:650px){.entity-heading{padding:20px}.entity-heading h1{font-size:25px}.image-viewer{height:220px}.knowledge-grid,.relation-groups,.similar-list,.entity-meta{grid-template-columns:1fr}.knowledge-grid article{min-height:0}.relation-section,.similar-section{padding:18px}.relation-section>header,.similar-section>header{align-items:flex-start;flex-direction:column;gap:5px}}
</style>
