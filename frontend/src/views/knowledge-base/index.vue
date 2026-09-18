<script setup lang="ts">
interface ImageItem { id:string;name:string;url:string;sourceDatasetId:string;license:string }
interface Entity {
  id:string;name:string;crop:string;category:string;categoryLabel:string;summary:string;
  symptoms:string;pathogen:string;occurrenceFactors:string;controlOptions:{name:string;type:string}[];
  affectedParts:string[];aliases:string[];images:ImageItem[];
}
interface PageData { items:Entity[];total:number;page:number;pageSize:number }
interface Candidate {
  id:string;name:string;crop:string;category:string;categoryLabel:string;summary:string;
  score:number;matchedSymptoms:string[];matchedParts:string[];imageUrl:string;
}
interface Comparison { crop:string;category:string;items:Entity[] }

const router = useRouter();
const route = useRoute();
const crop = ref(String(route.query.crop||'番茄'));
const mode = ref<'directory'|'symptom'>('directory');
const category = ref('Disease');
const part = ref('');
const keyword = ref('');
const imageStatus = ref('');
const page = ref(1);
const pageSize = 20;
const total = ref(0);
const loading = ref(false);
const entities = ref<Entity[]>([]);
const compareIds = ref<string[]>([]);
const comparison = ref<Comparison|null>(null);
const compareVisible = ref(false);
const symptomText = ref('');
const symptomParts = ref<string[]>([]);
const candidates = ref<Candidate[]>([]);

const categoryOptions = [
  {label:'全部类别',value:''},{label:'病害',value:'Disease'},{label:'虫害',value:'Pest'}
];
const partOptions = [
  {label:'叶片',value:'叶片'},{label:'茎部',value:'茎'},{label:'根部',value:'根'},
  {label:'果实或穗部',value:'果实'},{label:'幼苗',value:'幼苗'},{label:'全株',value:'全株'}
];

async function load() {
  loading.value = true;
  const {data,error} = await request<PageData>({url:'/agriculture/entities',params:{
    crop:crop.value,category:category.value,part:part.value,keyword:keyword.value.trim(),
    imageStatus:imageStatus.value,page:page.value,pageSize
  }});
  loading.value = false;
  if(error||!data) return;
  entities.value=data.items;total.value=data.total;
}

function resetAndLoad(){page.value=1;compareIds.value=[];load()}
function openDetail(id:string){router.push(`/knowledge-base/${id}`)}
function toggleCompare(entity:Entity,checked:boolean){
  if(checked){
    const selected=entities.value.filter(item=>compareIds.value.includes(item.id));
    if(compareIds.value.length>=3){window.$message?.warning?.('最多选择3个条目');return}
    if(selected.some(item=>item.crop!==entity.crop||item.category!==entity.category)){
      window.$message?.warning?.('只能选择同一作物、同一类别的条目');return;
    }
    compareIds.value=[...compareIds.value,entity.id];
  }else compareIds.value=compareIds.value.filter(id=>id!==entity.id);
}

async function compare(){
  if(compareIds.value.length<2){window.$message?.warning?.('请至少选择2个条目');return}
  const {data,error}=await request<Comparison>({url:'/agriculture/entities/compare',method:'post',data:{entityIds:compareIds.value}});
  if(error||!data)return;comparison.value=data;compareVisible.value=true;
}

async function searchSymptoms(){
  if(!symptomText.value.trim()&&!symptomParts.value.length){window.$message?.warning?.('请填写症状或选择危害部位');return}
  loading.value=true;
  const {data,error}=await request<Candidate[]>({url:'/agriculture/entities/symptom-candidates',params:{
    crop:crop.value,symptoms:symptomText.value.trim(),parts:symptomParts.value.join(','),limit:20
  }});
  loading.value=false;if(error)return;candidates.value=data||[];
}

watch(crop,()=>{page.value=1;compareIds.value=[];candidates.value=[];load()});
watch(category,resetAndLoad);watch(part,resetAndLoad);watch(imageStatus,resetAndLoad);
onMounted(()=>{
  if(route.query.compare==='1'){
    const saved=JSON.parse(sessionStorage.getItem('agrigraph-compare-ids')||'[]') as string[];
    compareIds.value=saved.slice(0,3);
  }
  load();
});
</script>

<template>
  <div class="kb-page">
    <header class="page-heading">
      <div><h1>病虫害知识库</h1><p>按作物检索规范化病虫害知识，或根据田间症状反查候选条目</p></div>
      <NRadioGroup v-model:value="mode" size="small"><NRadioButton value="directory">病虫害目录</NRadioButton><NRadioButton value="symptom">症状反查</NRadioButton></NRadioGroup>
    </header>

    <template v-if="mode==='directory'">
      <div class="filter-bar">
        <NSelect v-model:value="crop" :options="[{label:'番茄',value:'番茄'},{label:'水稻',value:'水稻'}]" />
        <NSelect v-model:value="category" :options="categoryOptions" />
        <NSelect v-model:value="part" clearable placeholder="全部部位" :options="partOptions" />
        <NSelect v-model:value="imageStatus" :options="[{label:'全部图片状态',value:''},{label:'有核验图片',value:'WITH'},{label:'暂无核验图片',value:'WITHOUT'}]" />
        <NInput v-model:value="keyword" clearable placeholder="名称或症状关键词" @keyup.enter="resetAndLoad"><template #prefix><icon-solar:magnifer-linear /></template></NInput>
        <NButton type="primary" :loading="loading" @click="resetAndLoad">查询</NButton>
      </div>

      <div class="catalog-head"><span>{{ crop }}共找到 <b>{{ total }}</b> 个条目</span><span>已选择 {{ compareIds.length }}/3 项用于对比</span></div>
      <div class="entity-table" :class="{loading}">
        <div class="table-row table-header"><span></span><span>名称</span><span>类别与部位</span><span>知识摘要</span><span>图片</span><span></span></div>
        <div v-for="item in entities" :key="item.id" class="table-row" @dblclick="openDetail(item.id)">
          <NCheckbox :checked="compareIds.includes(item.id)" @update:checked="value=>toggleCompare(item,value)" />
          <button type="button" class="entity-name" @click="openDetail(item.id)"><b>{{ item.name }}</b><small>{{ item.crop }}</small></button>
          <span><NTag size="small" :bordered="false" :type="item.category==='Disease'?'error':'warning'">{{ item.categoryLabel }}</NTag><small>{{ item.affectedParts.slice(0,3).join('、')||'部位待补充' }}</small></span>
          <p>{{ item.summary||item.symptoms||'暂无摘要' }}</p>
          <span class="image-state" :class="{available:item.images.length}"><icon-solar:gallery-wide-linear />{{ item.images.length?'已核验':'暂无' }}</span>
          <NButton quaternary circle title="查看详情" @click="openDetail(item.id)"><template #icon><icon-solar:alt-arrow-right-linear /></template></NButton>
        </div>
        <NEmpty v-if="!loading&&!entities.length" description="没有符合条件的条目" />
      </div>
      <div class="catalog-footer"><NPagination v-model:page="page" :page-size="pageSize" :item-count="total" @update:page="load" /><NButton type="primary" :disabled="compareIds.length<2" @click="compare">对比已选条目</NButton></div>
    </template>

    <template v-else>
      <div class="symptom-search">
        <NSelect v-model:value="crop" :options="[{label:'番茄',value:'番茄'},{label:'水稻',value:'水稻'}]" />
        <NInput v-model:value="symptomText" clearable placeholder="输入症状，如：褐色病斑、霉层、萎蔫" @keyup.enter="searchSymptoms" />
        <NSelect v-model:value="symptomParts" multiple clearable placeholder="选择危害部位" :options="partOptions" />
        <NButton type="primary" :loading="loading" @click="searchSymptoms">查找候选</NButton>
      </div>
      <div class="candidate-list">
        <button v-for="item in candidates" :key="item.id" type="button" @click="openDetail(item.id)">
          <span class="candidate-score">{{ Math.round(item.score*100) }}<small>匹配度</small></span>
          <span class="candidate-main"><b>{{ item.name }}</b><small>{{ item.categoryLabel }} · {{ item.summary||'暂无摘要' }}</small><em v-if="item.matchedSymptoms.length">症状：{{ item.matchedSymptoms.join('、') }}</em><em v-if="item.matchedParts.length">部位：{{ item.matchedParts.join('、') }}</em></span>
          <icon-solar:alt-arrow-right-linear />
        </button>
        <NEmpty v-if="!loading&&!candidates.length" description="填写症状和部位后查找候选病虫害" />
      </div>
    </template>

    <NModal v-model:show="compareVisible" preset="card" title="病虫害特征对比" class="compare-modal">
      <div v-if="comparison" class="compare-grid">
        <article v-for="item in comparison.items" :key="item.id"><h3>{{ item.name }}</h3><NTag size="small" :bordered="false">{{ item.categoryLabel }}</NTag><dl><dt>危害部位</dt><dd>{{ item.affectedParts.join('、')||'待补充' }}</dd><dt>典型症状</dt><dd>{{ item.symptoms||'待补充' }}</dd><dt>病原或致害信息</dt><dd>{{ item.pathogen||'待补充' }}</dd><dt>发生条件</dt><dd>{{ item.occurrenceFactors||'待补充' }}</dd><dt>防治选项</dt><dd>{{ item.controlOptions?.map(option => option.name).join('、')||'待补充' }}</dd></dl><NButton text type="primary" @click="openDetail(item.id);compareVisible=false">查看完整详情</NButton></article>
      </div>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.kb-page{color:var(--agri-text)}.page-heading{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:14px}.page-heading h1{margin:0;font-size:22px}.page-heading p{margin:4px 0 0;color:var(--agri-text-secondary)}.filter-bar{display:grid;grid-template-columns:110px 120px 140px 150px minmax(210px,1fr) auto;gap:8px;padding:12px;border:1px solid var(--agri-border);background:var(--agri-surface)}.catalog-head,.catalog-footer{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;color:var(--agri-text-secondary);border:1px solid var(--agri-border);border-top:0;background:var(--agri-surface-soft)}.catalog-head b{color:var(--agri-primary)}.entity-table{min-height:510px;border-right:1px solid var(--agri-border);border-left:1px solid var(--agri-border);background:var(--agri-surface)}.entity-table.loading{opacity:.65}.table-row{display:grid;grid-template-columns:32px minmax(150px,1.1fr) minmax(150px,1fr) minmax(260px,2fr) 100px 38px;align-items:center;gap:12px;min-height:70px;padding:9px 14px;border-bottom:1px solid var(--agri-border)}.table-header{min-height:42px;color:var(--agri-text-muted);font-size:12px;background:var(--agri-surface-soft)}.entity-name{display:flex;min-width:0;flex-direction:column;border:0;background:transparent;color:var(--agri-text);text-align:left;cursor:pointer}.entity-name:hover b{color:var(--agri-primary)}.entity-name small,.table-row>span small{display:block;margin-top:4px;color:var(--agri-text-muted)}.table-row>p{display:-webkit-box;overflow:hidden;margin:0;color:var(--agri-text-secondary);line-height:1.55;-webkit-box-orient:vertical;-webkit-line-clamp:2}.image-state{display:flex!important;align-items:center;gap:5px;color:var(--agri-text-muted)}.image-state.available{color:var(--agri-primary)}.symptom-search{display:grid;grid-template-columns:120px minmax(260px,1.4fr) minmax(220px,1fr) auto;gap:9px;padding:14px;border:1px solid var(--agri-border);background:var(--agri-surface)}.candidate-list{min-height:560px;border:1px solid var(--agri-border);border-top:0;background:var(--agri-surface)}.candidate-list>button{width:100%;display:grid;grid-template-columns:72px minmax(0,1fr) 24px;align-items:center;gap:16px;padding:18px;border:0;border-bottom:1px solid var(--agri-border);background:transparent;color:var(--agri-text);text-align:left;cursor:pointer}.candidate-list>button:hover{background:var(--agri-surface-active)}.candidate-score{font-size:24px;color:var(--agri-primary);text-align:center}.candidate-score small{display:block;color:var(--agri-text-muted);font-size:11px}.candidate-main{display:flex;min-width:0;flex-direction:column;gap:5px}.candidate-main small{overflow:hidden;color:var(--agri-text-secondary);text-overflow:ellipsis;white-space:nowrap}.candidate-main em{color:var(--agri-primary);font-size:12px;font-style:normal}.compare-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0;border:1px solid var(--agri-border)}.compare-grid article{min-width:0;padding:18px;border-right:1px solid var(--agri-border)}.compare-grid article:last-child{border:0}.compare-grid h3{margin:0 0 8px}.compare-grid dl{margin:14px 0}.compare-grid dt{margin-top:12px;color:var(--agri-text-muted);font-size:12px}.compare-grid dd{max-height:120px;overflow:auto;margin:4px 0 0;line-height:1.65;white-space:pre-line}:global(.compare-modal){width:min(1180px,94vw)}@media(max-width:900px){.filter-bar{grid-template-columns:1fr 1fr 1fr}.symptom-search{grid-template-columns:1fr 1fr}.table-row{grid-template-columns:28px minmax(140px,1fr) minmax(140px,1fr) 80px 34px}.table-row>p{display:none}.compare-grid{grid-template-columns:1fr}.compare-grid article{border-right:0;border-bottom:1px solid var(--agri-border)}}@media(max-width:650px){.page-heading{align-items:flex-start;flex-direction:column;gap:12px}.page-heading p{display:none}.filter-bar,.symptom-search{grid-template-columns:1fr 1fr}.table-row{grid-template-columns:26px minmax(0,1fr) 32px}.table-row>span,.table-header{display:none}.catalog-head span:last-child{display:none}.catalog-footer{align-items:flex-end;flex-direction:column;gap:10px}.candidate-list>button{grid-template-columns:56px minmax(0,1fr) 20px}}
</style>
