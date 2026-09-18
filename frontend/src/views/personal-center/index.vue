<script setup lang="ts">
const router = useRouter();
</script>

<template>
  <div class="profile-page">
    <h1>个人中心</h1>
    <p>账号设置与默认作物入口已收缩为基础信息。</p>
    <NButton type="primary" @click="router.push('/chat')">返回农业问答</NButton>
  </div>
</template>

<style scoped>
.profile-page { padding: 24px; }
</style>
