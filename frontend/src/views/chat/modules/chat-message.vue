<script setup lang="ts">
import SafeMarkdown from '@/components/common/SafeMarkdown.vue';
import { formatDate } from '@/utils/common';

defineOptions({ name: 'ChatMessage' });

defineProps<{
  msg: Api.Chat.Message;
  sessionId?: string;
}>();

const authStore = useAuthStore();

function handleCopy(content: string) {
  navigator.clipboard.writeText(content);
  window.$message?.success('已复制');
}
</script>

<template>
  <div class="mb-8 flex-col gap-2">
    <div class="flex items-center gap-4">
      <NAvatar :class="msg.role === 'user' ? 'bg-success' : 'bg-primary'">
        <SvgIcon v-if="msg.role === 'user'" icon="ph:user-circle" class="text-icon-large color-white" />
        <SystemLogo v-else class="text-6 text-white" />
      </NAvatar>
      <div class="flex-col gap-1">
        <NText class="text-4 font-bold">
          {{ msg.role === 'user' ? authStore.userInfo.username : 'AgriGraph' }}
        </NText>
        <NText class="text-3 color-gray-500">{{ formatDate(msg.timestamp) }}</NText>
      </div>
    </div>

    <NText v-if="msg.status === 'pending'">
      <icon-eos-icons:three-dots-loading class="ml-12 mt-2 text-8" />
    </NText>
    <NText v-else-if="msg.status === 'error'" class="ml-12 mt-2 italic">服务暂时不可用，请稍后重试</NText>
    <SafeMarkdown v-else-if="msg.role === 'assistant'" class="mt-2 pl-12" :content="msg.content" />
    <NText v-else class="ml-12 mt-2 text-4">{{ msg.content }}</NText>

    <NDivider class="ml-12 w-[calc(100%-3rem)] mb-0! mt-2!" />
    <div class="ml-12 flex gap-4">
      <NButton quaternary title="复制回答" @click="handleCopy(msg.content)">
        <template #icon><icon-mynaui:copy /></template>
      </NButton>
    </div>
  </div>
</template>
