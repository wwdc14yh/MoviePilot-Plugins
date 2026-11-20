<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
})

const states = ref({})
const taskCount = ref(0)

function unwrap(res) {
  return (res && res.data !== undefined) ? res.data : res
}

async function load() {
  if (!props.api || !props.pluginId) return
  try {
    const s = unwrap(await props.api.get(`plugin/${props.pluginId}/status`))
    if (s) {
      states.value = s.states || {}
      taskCount.value = (s.tasks || []).length
    }
  } catch (e) { /* 仪表盘加载失败保持空白 */ }
}

onMounted(load)
</script>

<template>
  <v-card>
    <v-card-title class="d-flex align-center">
      <v-icon class="mr-2">mdi-cloud-sync</v-icon>
      CloudDrive2 同步
    </v-card-title>
    <v-card-text>
      <div class="text-body-2">
        任务 {{ taskCount }} 个 · 已同步 {{ states.done || 0 }} ·
        同步中 {{ states.copying || 0 }} · 失败 {{ states.failed || 0 }}
      </div>
    </v-card-text>
  </v-card>
</template>
