<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { createTaskBySkuText, fetchActiveClients, fetchTasks } from './api';

const skuText = ref('');
const msg = ref('');
const tasks = ref<any[]>([]);
const clients = ref<any[]>([]);

async function refresh() {
  const [t, c] = await Promise.all([fetchTasks(), fetchActiveClients()]);
  tasks.value = t.items || [];
  clients.value = c.items || [];
}

async function submit() {
  try {
    const out = await createTaskBySkuText(skuText.value);
    msg.value = `任务创建成功: ${out.task_id}`;
    await refresh();
  } catch (e: any) {
    msg.value = `提交失败: ${e.message}`;
  }
}

onMounted(async () => {
  await refresh();
  setInterval(refresh, 3000);
});
</script>

<template>
  <div>
    <h2>Vue SKU 调度面板</h2>
    <textarea v-model="skuText" rows="6" placeholder="SKU001\nSKU002,SKU003" />
    <button @click="submit">开始踢跟</button>
    <p>{{ msg }}</p>

    <h3>活跃客户端</h3>
    <ul>
      <li v-for="c in clients" :key="c.client_id">{{ c.client_id }} / {{ c.alive ? 'alive' : 'offline' }}</li>
    </ul>

    <h3>任务</h3>
    <ul>
      <li v-for="t in tasks" :key="t.id">{{ t.id }} / {{ t.status }} / {{ t.message }}</li>
    </ul>
  </div>
</template>
