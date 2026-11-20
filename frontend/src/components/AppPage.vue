<script setup>
import Page from './Page.vue'

defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
})
const emit = defineEmits(['action'])
</script>

<template>
  <div class="pa-4">
    <Page :api="api" :plugin-id="pluginId" @action="emit('action')" />
  </div>
</template>
