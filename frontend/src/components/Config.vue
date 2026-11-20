<script setup>
import { ref } from 'vue'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
})
const emit = defineEmits(['save', 'close', 'switch'])

const modeItems = [
  { title: '同步', value: 'sync' },
  { title: '备份', value: 'backup' },
  { title: '移动', value: 'move' },
]
const modeHints = {
  sync: '增量复制到目标；源文件变化会重新复制，源文件消失按宽限期清理同步状态（不动目标文件）。',
  backup: '只增不减：新文件复制过去，源文件变化时目标保留旧版、新版自动改名存入；源文件消失不处理目标。',
  move: '复制并校验完成（哈希/大小一致）后才删除源文件；未传完绝不删源，删源失败下一轮重试。可选清理源端空目录。',
}
const conflictItems = [
  { title: '用全局默认', value: '' },
  { title: '跳过 (Skip)', value: 'skip' },
  { title: '覆盖 (Overwrite)', value: 'overwrite' },
  { title: '重命名 (Rename)', value: 'rename' },
]

function newTask() {
  return {
    id: Math.random().toString(16).slice(2, 14),
    name: '',
    enabled: true,
    mode: 'sync',
    source_path: '',
    target_path: '',
    conflict_policy: '',
    delete_empty_dirs: false,
  }
}

function normalize(cfg) {
  const c = JSON.parse(JSON.stringify(cfg || {}))
  if (!Array.isArray(c.tasks) || !c.tasks.length) {
    // 兼容旧的单任务配置
    if (c.source_path || c.target_path) {
      c.tasks = [{
        id: 'default',
        name: '默认任务',
        enabled: true,
        mode: 'sync',
        source_path: c.source_path || '',
        target_path: c.target_path || '',
        conflict_policy: '',
        delete_empty_dirs: false,
      }]
    } else {
      c.tasks = [newTask()]
    }
  }
  c.tasks = c.tasks.map(t => ({ ...newTask(), ...t }))
  return c
}

const config = ref(normalize(props.initialConfig))

function addTask() {
  config.value.tasks.push(newTask())
}
function removeTask(idx) {
  config.value.tasks.splice(idx, 1)
}
function saveConfig() {
  const out = JSON.parse(JSON.stringify(config.value))
  out.tasks = out.tasks.map(t => ({
    ...t,
    name: t.name || t.source_path || '未命名任务',
  }))
  emit('save', out)
}
</script>

<template>
  <div class="pa-2">
    <v-card variant="outlined" class="mb-4">
      <v-card-title>连接与全局设置</v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="3">
            <v-switch v-model="config.enabled" label="启用插件" color="primary" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-switch v-model="config.onlyonce" label="保存后立即运行一次" color="primary" hide-details />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model.number="config.interval_minutes" type="number"
              label="轮询间隔 (分钟)" hint="所有任务共用这个周期" persistent-hint />
          </v-col>
          <v-col cols="12" md="3">
            <v-text-field v-model.number="config.max_retries" type="number"
              label="失败最大重试次数" />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="config.cd2_address" label="CloudDrive2 gRPC 地址"
              placeholder="127.0.0.1:19798" hint="CD2 的 gRPC 监听地址, 默认端口 19798" persistent-hint />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="config.cd2_token" type="password" label="API Token"
              hint="在 CloudDrive2 设置中创建；移动模式需要删除权限" persistent-hint />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <div class="d-flex align-center mb-2">
      <span class="text-h6">任务列表</span>
      <v-spacer />
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="addTask">新增任务</v-btn>
    </div>
    <v-alert type="info" variant="tonal" class="mb-4">
      每个任务是一组独立的「源目录 → 目标目录」，有自己的模式和同步状态，互不影响。
      复制是异步的：提交后先显示同步中，后续轮次自动结算，不会误判失败。
    </v-alert>

    <v-card v-for="(task, idx) in config.tasks" :key="task.id || idx" variant="outlined" class="mb-4">
      <v-card-title class="d-flex align-center">
        <v-text-field v-model="task.name" label="任务名称" density="compact"
          hide-details style="max-width: 280px" />
        <v-chip class="ml-3" size="small"
          :color="task.mode === 'move' ? 'warning' : task.mode === 'backup' ? 'info' : 'success'">
          {{ modeItems.find(m => m.value === task.mode)?.title }}
        </v-chip>
        <v-spacer />
        <v-switch v-model="task.enabled" label="启用" color="primary" hide-details density="compact" />
        <v-btn icon="mdi-delete" variant="text" color="error" @click="removeTask(idx)" />
      </v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="4">
            <v-select v-model="task.mode" :items="modeItems" label="模式" />
            <div class="text-caption text-medium-emphasis">{{ modeHints[task.mode] }}</div>
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="task.source_path" label="源目录 (A 网盘)"
              placeholder="/网盘名/源目录" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model="task.target_path" label="目标目录 (B 网盘)"
              placeholder="/网盘名/目标目录" />
          </v-col>
          <v-col cols="12" md="4">
            <v-select v-model="task.conflict_policy" :items="conflictItems"
              label="目标同名文件冲突策略" />
          </v-col>
          <v-col v-if="task.mode === 'move'" cols="12" md="4">
            <v-switch v-model="task.delete_empty_dirs" color="primary" hide-details
              label="移动后清理源端空目录" />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card variant="outlined" class="mb-4">
      <v-card-title>异步校验与记录清理（全局）</v-card-title>
      <v-card-text>
        <v-row>
          <v-col cols="12" md="4">
            <v-text-field v-model.number="config.verify_wait_seconds" type="number"
              label="提交后本轮等待 (秒)" hint="0 = 全部留到下一轮结算" persistent-hint />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model.number="config.verify_interval_seconds" type="number"
              label="等待时轮询间隔 (秒)" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model.number="config.pending_timeout_hours" type="number"
              label="同步中超时判失败 (小时)" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model.number="config.history_retention_days" type="number"
              label="成功历史保留 (天)" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model.number="config.failed_retention_days" type="number"
              label="失败历史保留 (天)" />
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field v-model.number="config.state_tombstone_days" type="number"
              label="源文件消失后宽限 (天)" hint="同步/移动模式的状态清理" persistent-hint />
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <div class="d-flex justify-end ga-2">
      <v-btn variant="text" @click="emit('switch')">查看任务</v-btn>
      <v-btn variant="text" @click="emit('close')">关闭</v-btn>
      <v-btn color="primary" @click="saveConfig">保存</v-btn>
    </div>
  </div>
</template>
