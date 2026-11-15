<script setup lang="ts">
import { renderMarkdown } from '@/utils/markdown';

defineOptions({ name: 'SafeMarkdown' });

const props = defineProps<{ content?: string }>();

const renderedContent = computed(() => renderMarkdown(props.content));
</script>

<template>
  <div class="safe-markdown" v-html="renderedContent"></div>
</template>

<style scoped>
.safe-markdown {
  line-height: 1.75;
  overflow-wrap: anywhere;
}

.safe-markdown :deep(p:first-child) {
  margin-top: 0;
}

.safe-markdown :deep(p:last-child) {
  margin-bottom: 0;
}

.safe-markdown :deep(pre) {
  overflow-x: auto;
}
</style>
