<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
})
const emit = defineEmits(['action', 'switch', 'close'])

const status = ref({ enabled: false, tasks: [], states: {}, config: {} })
const files = ref([])
const filesTotal = ref(0)
const page = ref(1)
const pageSize = ref(20)
const history = ref([])
const tab = ref('overview')
const selectedId = ref('')
const filter = ref('all')
const loading = ref(false)
const running = ref(false)
const message = ref('')
const confirm = ref({ show: false, item: null })
const taskDialog = ref({ show: false, editing: null, form: null })
const taskConfirmDelete = ref({ show: false })
const globalDialog = ref({ show: false, form: null })

const modeItems = computed(() => {
  const items = [
    { title: '增量同步', value: 'sync' },
    { title: '移动', value: 'move' },
  ]
  if (taskDialog.value.form?.mode === 'backup') {
    items.push({ title: '备份 (旧任务)', value: 'backup' })
  }
  return items
})
const modeHints = {
  sync: '增量复制；源变化重传，源消失按宽限期处理状态。',
  backup: '只增不减；源变化时目标保留旧版、新版改名存入；源消失不动目标。',
  move: '复制任务完成确认后才删源文件；未完成绝不删源。可选清理源端空目录。',
}
const conflictItems = [
  { title: '用全局默认', value: '' },
  { title: '跳过 (Skip)', value: 'skip' },
  { title: '覆盖 (Overwrite)', value: 'overwrite' },
  { title: '重命名 (Rename)', value: 'rename' },
]
const conflictTitles = { '': '全局默认', skip: '跳过', overwrite: '覆盖', rename: '重命名' }

function blankTask() {
  return {
    id: '', name: '', enabled: true, mode: 'sync',
    source_path: '', target_path: '', conflict_policy: '',
    delete_empty_dirs: false, max_concurrent_sync: 1,
  }
}
function openNewTask() {
  taskDialog.value = { show: true, editing: null, form: blankTask() }
}
function openEditTask() {
  if (!selected.value) return
  taskDialog.value = {
    show: true,
    editing: selected.value.id,
    form: { ...blankTask(), ...JSON.parse(JSON.stringify(selected.value)) },
  }
}
async function saveTask() {
  const form = taskDialog.value.form
  if (!form.source_path || !form.target_path) {
    message.value = '源目录和目标目录必填'
    return
  }
  try {
    // 宿主把插件 API 注册为 FastAPI 路由: 只认查询参数,
    // JSON body / dict 参数会被判为请求参数不正确, 故一律拼查询串
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(form)) params.set(k, String(v ?? ''))
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/save_task?${params.toString()}`,
    ))
    if (!res?.ok) {
      message.value = '保存任务失败: ' + (res?.error || '')
      return
    }
    taskDialog.value.show = false
    message.value = res.created ? '新任务已创建' : '任务已更新'
    await loadStatus()
    if (res.task?.id) selectedId.value = res.task.id
    emit('action')
  } catch (e) {
    message.value = '保存任务失败: ' + (e?.message || e)
  }
}
async function deleteTask() {
  taskConfirmDelete.value.show = false
  if (!selected.value) return
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/delete_task?task_id=${encodeURIComponent(selected.value.id)}`,
    ))
    if (!res?.ok) {
      message.value = '删除任务失败: ' + (res?.error || '')
      return
    }
    selectedId.value = ''
    message.value = '任务已删除（已同步到目标端的文件不会被删）'
    await load()
  } catch (e) {
    message.value = '删除任务失败: ' + (e?.message || e)
  }
}

// ---------- 全局设置 (页面内直接编辑, 不依赖宿主跳转) ----------
function openGlobal() {
  const cfg = status.value.config || {}
  globalDialog.value = {
    show: true,
    form: {
      enabled: !!cfg.enabled,
      cd2_address: cfg.cd2_address || '127.0.0.1:19798',
      cd2_token: cfg.cd2_token || '',
      interval_minutes: cfg.interval_minutes ?? 30,
      max_retries: cfg.max_retries ?? 5,
      verify_wait_seconds: cfg.verify_wait_seconds ?? 30,
      verify_interval_seconds: cfg.verify_interval_seconds ?? 5,
      pending_timeout_hours: cfg.pending_timeout_hours ?? 24,
      copy_timeout_seconds: cfg.copy_timeout_seconds ?? 180,
      history_retention_days: cfg.history_retention_days ?? 30,
      failed_retention_days: cfg.failed_retention_days ?? 90,
      state_tombstone_days: cfg.state_tombstone_days ?? 30,
    },
  }
}
async function saveGlobal() {
  try {
    const params = new URLSearchParams()
    for (const [k, v] of Object.entries(globalDialog.value.form)) {
      params.set(k, String(v ?? ''))
    }
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/save_global?${params.toString()}`,
    ))
    if (!res?.ok) {
      message.value = '保存全局设置失败: ' + (res?.error || '')
      return
    }
    globalDialog.value.show = false
    message.value = '全局设置已保存'
    await load()
    emit('action')
  } catch (e) {
    message.value = '保存全局设置失败: ' + (e?.message || e)
  }
}

const modeMeta = {
  sync: { title: '增量同步', color: 'success', icon: 'mdi-sync' },
  backup: { title: '备份', color: 'info', icon: 'mdi-archive-arrow-down' },
  move: { title: '移动', color: 'warning', icon: 'mdi-file-move' },
}
const stateMeta = {
  done: { title: '已同步', color: 'success', icon: 'mdi-check-circle' },
  copying: { title: '同步中', color: 'info', icon: 'mdi-progress-clock' },
  failed: { title: '失败', color: 'error', icon: 'mdi-alert-circle' },
  source_gone: { title: '源已消失', color: 'grey', icon: 'mdi-file-remove' },
  excluded: { title: '已排除', color: 'grey', icon: 'mdi-cancel' },
}
const filterItems = [
  { title: '全部', value: 'all' },
  { title: '已同步', value: 'done' },
  { title: '同步中', value: 'copying' },
  { title: '失败', value: 'failed' },
]
const pageSizeItems = [10, 20, 50, 100]

const selected = computed(
  () => status.value.tasks.find(t => t.id === selectedId.value) || null,
)
const pageCount = computed(() =>
  Math.max(1, Math.ceil(filesTotal.value / pageSize.value)),
)

function unwrap(res) {
  return res && res.data !== undefined ? res.data : res
}
function humanSize(size) {
  let v = Number(size || 0)
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return (i === 0 ? v : v.toFixed(2)) + ' ' + units[i]
}
function humanTime(ts) {
  if (!ts) return ''
  const d = new Date(Number(ts) * 1000)
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function loadStatus() {
  status.value =
    unwrap(await props.api.get(`plugin/${props.pluginId}/status`)) || status.value
  if (!selectedId.value && status.value.tasks.length) {
    selectedId.value = status.value.tasks[0].id
  }
  if (selectedId.value && !status.value.tasks.find(t => t.id === selectedId.value)) {
    selectedId.value = status.value.tasks[0]?.id || ''
  }
}
async function loadFiles() {
  if (!selectedId.value) { files.value = []; filesTotal.value = 0; return }
  const params = new URLSearchParams({
    task_id: selectedId.value,
    limit: String(pageSize.value),
    offset: String((page.value - 1) * pageSize.value),
  })
  if (filter.value !== 'all') params.set('status', filter.value)
  const res = unwrap(await props.api.get(
    `plugin/${props.pluginId}/files?${params.toString()}`,
  )) || {}
  files.value = res.files || []
  filesTotal.value = res.total || 0
}
async function loadHistory() {
  if (!selectedId.value) { history.value = []; return }
  history.value = unwrap(await props.api.get(
    `plugin/${props.pluginId}/tasks?task_id=${encodeURIComponent(selectedId.value)}&limit=5`,
  )) || []
}
async function settle() {
  // 先让后端按 CD2 任务状态快速结算一次, 页面状态才能及时更新,
  // 不必等下一轮定时同步
  try {
    await props.api.post(`plugin/${props.pluginId}/settle`)
  } catch (e) { /* 结算失败不阻塞页面加载 */ }
}
async function load() {
  if (!props.api || !props.pluginId) return
  loading.value = true
  try {
    await settle()
    await loadStatus()
    await Promise.all([loadFiles(), loadHistory()])
  } catch (e) {
    message.value = '加载失败: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
}
async function refreshQuiet() {
  try {
    await settle()
    await loadStatus()
    await Promise.all([loadFiles(), loadHistory()])
  } catch (e) { /* 自动刷新失败保持沉默 */ }
}

async function runOnce(taskId) {
  running.value = true
  message.value = ''
  try {
    const url = taskId
      ? `plugin/${props.pluginId}/run_once?task_id=${encodeURIComponent(taskId)}`
      : `plugin/${props.pluginId}/run_once`
    await props.api.post(url)
    await load()
    emit('action')
  } catch (e) {
    message.value = '运行失败: ' + (e?.message || e)
  } finally {
    running.value = false
  }
}

async function retryFile(item) {
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/retry_file?state_key=${encodeURIComponent(item.state_key)}`,
    ))
    message.value = res?.ok ? '已重新排队, 任务已在后台重跑' : ('重试失败: ' + (res?.error || ''))
    setTimeout(load, 1500)
  } catch (e) {
    message.value = '重试失败: ' + (e?.message || e)
  }
}

function askDelete(item) {
  confirm.value = { show: true, item }
}
async function doDelete() {
  const item = confirm.value.item
  confirm.value.show = false
  if (!item) return
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/delete_file?state_key=${encodeURIComponent(item.state_key)}`,
    ))
    message.value = res?.ok ? '已删除目标副本并排除该文件' : ('删除失败: ' + (res?.error || ''))
    await load()
  } catch (e) {
    message.value = '删除失败: ' + (e?.message || e)
  }
}

watch(selectedId, () => { page.value = 1; loadFiles(); loadHistory() })
watch(filter, () => { page.value = 1; loadFiles() })
watch(page, loadFiles)
watch(pageSize, () => { page.value = 1; loadFiles() })

let autoTimer = null
onMounted(() => {
  load()
  // 页面打开期间每 20 秒自动结算并刷新, 状态跟得上 CD2 的完成进度
  autoTimer = setInterval(refreshQuiet, 20000)
})
onUnmounted(() => {
  if (autoTimer) clearInterval(autoTimer)
})
</script>

<template>
  <div class="cd2-root">
    <!-- 顶栏: 标题 + 全局入口 -->
    <div class="cd2-header">
      <v-icon color="primary" class="mr-2">mdi-cloud-sync</v-icon>
      <div class="cd2-header-title">
        <div class="text-subtitle-1 font-weight-medium">CloudDrive2 同步</div>
        <div class="text-caption text-medium-emphasis">多任务增量同步 / 备份 / 移动</div>
      </div>
      <v-chip size="small" class="ml-2" :color="status.enabled ? 'success' : 'grey'">
        {{ status.enabled ? '已启用' : '未启用' }}
      </v-chip>
      <v-spacer />
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-tune-variant"
        @click="openGlobal">全局设置</v-btn>
      <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading"
        @click="load">刷新</v-btn>
      <v-btn variant="text" prepend-icon="mdi-play-circle-outline"
        :loading="running" @click="runOnce()">运行全部</v-btn>
    </div>

    <div class="cd2-body">
      <!-- 左: 固定任务栏 (列表独立滚动, 新建按钮钉在底部) -->
      <aside class="cd2-side">
        <div class="cd2-side-head">
          同步任务
          <v-chip class="ml-2" size="x-small">{{ status.tasks.length }}</v-chip>
        </div>
        <div class="cd2-task-list">
          <div
            v-for="task in status.tasks"
            :key="task.id"
            class="cd2-task-item"
            :class="{ 'cd2-task-item--active': task.id === selectedId }"
            @click="selectedId = task.id"
          >
            <div class="d-flex align-center">
              <span class="font-weight-medium text-truncate">{{ task.name }}</span>
              <v-spacer />
              <v-icon size="x-small" :color="task.enabled ? 'success' : 'grey'">
                mdi-circle
              </v-icon>
            </div>
            <div class="text-caption text-medium-emphasis cd2-path">
              {{ modeMeta[task.mode]?.title }} · {{ task.source_path }} → {{ task.target_path }}
            </div>
            <div class="text-caption">
              已同步 {{ task.states?.done || 0 }} · 同步中 {{ task.states?.copying || 0 }}
              <span v-if="task.states?.failed" class="text-error">
                · 失败 {{ task.states.failed }}
              </span>
            </div>
          </div>
          <div v-if="!status.tasks.length" class="text-caption text-medium-emphasis pa-3">
            还没有任务
          </div>
        </div>
        <div class="cd2-side-foot">
          <v-btn block color="primary" variant="tonal" prepend-icon="mdi-plus"
            @click="openNewTask">新建任务</v-btn>
        </div>
      </aside>

      <!-- 右: 详情 (独立滚动) -->
      <main class="cd2-main">
        <template v-if="selected">
          <div class="d-flex align-center flex-wrap ga-2 mb-1">
            <v-icon size="large" :color="modeMeta[selected.mode]?.color">
              {{ modeMeta[selected.mode]?.icon }}
            </v-icon>
            <span class="text-h6">{{ selected.name }}</span>
            <v-chip size="small" :color="modeMeta[selected.mode]?.color">
              {{ modeMeta[selected.mode]?.title }}
            </v-chip>
            <v-chip size="small" :color="selected.enabled ? 'success' : 'grey'">
              {{ selected.enabled ? '已启用' : '已停用' }}
            </v-chip>
            <v-spacer />
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-play"
              :loading="running" @click="runOnce(selected.id)">运行此任务</v-btn>
            <v-btn variant="text" prepend-icon="mdi-pencil" @click="openEditTask">编辑任务</v-btn>
            <v-btn variant="text" color="error" prepend-icon="mdi-delete"
              @click="taskConfirmDelete.show = true">删除任务</v-btn>
          </div>
          <div class="text-body-2 text-medium-emphasis mb-2 cd2-path">
            {{ selected.source_path }} → {{ selected.target_path }}
          </div>

          <v-alert v-if="message" type="info" variant="tonal" class="mb-3">{{ message }}</v-alert>

          <v-tabs v-model="tab" density="compact" class="mb-3">
            <v-tab value="overview">任务概览</v-tab>
            <v-tab value="files">文件列表</v-tab>
          </v-tabs>

          <v-window v-model="tab">
            <v-window-item value="overview">
              <div class="cd2-stats">
                <v-card variant="tonal">
                  <v-card-text>
                    <div class="text-caption">已同步文件</div>
                    <div class="text-h5">{{ selected.states?.done || 0 }}</div>
                    <div class="text-caption">共 {{ humanSize(selected.done_size) }}</div>
                  </v-card-text>
                </v-card>
                <v-card variant="tonal">
                  <v-card-text>
                    <div class="text-caption">正在同步</div>
                    <div class="text-h5">{{ selected.states?.copying || 0 }}</div>
                    <div class="text-caption">异步复制进行中, 下轮自动结算</div>
                  </v-card-text>
                </v-card>
                <v-card variant="tonal">
                  <v-card-text>
                    <div class="text-caption">失败项目</div>
                    <div class="text-h5" :class="selected.states?.failed ? 'text-error' : ''">
                      {{ selected.states?.failed || 0 }}
                    </div>
                    <div class="text-caption">在文件列表里重试或删除</div>
                  </v-card-text>
                </v-card>
                <v-card variant="tonal">
                  <v-card-text>
                    <div class="text-caption">源已消失 / 已排除</div>
                    <div class="text-h5">
                      {{ (selected.states?.source_gone || 0) + (selected.states?.excluded || 0) }}
                    </div>
                    <div class="text-caption">
                      消失 {{ selected.states?.source_gone || 0 }} · 排除 {{ selected.states?.excluded || 0 }}
                    </div>
                  </v-card-text>
                </v-card>
              </div>

              <v-card variant="outlined" class="mb-3">
                <v-card-title class="text-subtitle-1">任务信息</v-card-title>
                <v-card-text>
                  <div class="cd2-kv">
                    <span>模式</span><b>{{ modeMeta[selected.mode]?.title }}</b>
                    <span>冲突策略</span><b>{{ conflictTitles[selected.conflict_policy || ''] }}</b>
                    <span>同步线程</span><b>每轮最多同时 {{ selected.max_concurrent_sync || 1 }} 个文件</b>
                    <span>源目录</span><b class="cd2-path">{{ selected.source_path }}</b>
                    <span>目标目录</span><b class="cd2-path">{{ selected.target_path }}</b>
                    <span v-if="selected.mode === 'move'">删源后清理空目录</span>
                    <b v-if="selected.mode === 'move'">{{ selected.delete_empty_dirs ? '是' : '否' }}</b>
                  </div>
                </v-card-text>
              </v-card>

              <v-card variant="outlined">
                <v-card-title class="text-subtitle-1">最近运行</v-card-title>
                <v-card-text v-if="history.length">
                  <div v-for="run in history" :key="run.id" class="cd2-run-row">
                    <v-chip size="x-small" variant="tonal"
                      :color="run.status === 'failed' ? 'error' : 'success'">
                      {{ run.status }}
                    </v-chip>
                    <span class="text-body-2">
                      {{ humanTime(run.finished_at || run.started_at) }}
                      · 已同步 {{ (run.copied || 0) + (run.verified || 0) }}
                      · 同步中 {{ run.pending || 0 }}
                      · 失败 {{ run.failed || 0 }}
                      · 跳过 {{ run.skipped || 0 }}
                    </span>
                  </div>
                </v-card-text>
                <v-card-text v-else class="text-medium-emphasis">暂无运行记录</v-card-text>
              </v-card>
            </v-window-item>

            <v-window-item value="files">
              <v-card variant="outlined">
                <v-card-title class="d-flex align-center flex-wrap ga-2">
                  同步文件
                  <v-chip class="ml-1" size="small">{{ filesTotal }}</v-chip>
                  <v-spacer />
                  <v-btn-toggle v-model="filter" mandatory density="compact">
                    <v-btn v-for="f in filterItems" :key="f.value" :value="f.value" size="small">
                      {{ f.title }}
                    </v-btn>
                  </v-btn-toggle>
                </v-card-title>
                <div class="cd2-table-wrap">
                  <v-table v-if="files.length" density="comfortable" class="cd2-table">
                    <thead>
                      <tr>
                        <th>文件</th>
                        <th>状态</th>
                        <th>大小</th>
                        <th>更新时间</th>
                        <th class="text-right">操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in files" :key="item.state_key">
                        <td>
                          <div>{{ item.file_name }}</div>
                          <div class="text-caption text-medium-emphasis cd2-path">{{ item.target_path }}</div>
                          <div v-if="item.last_error" class="text-caption text-error">
                            {{ item.last_error }}
                          </div>
                        </td>
                        <td>
                          <v-chip size="small" :color="stateMeta[item.status]?.color" variant="tonal">
                            <v-icon size="small" class="mr-1">{{ stateMeta[item.status]?.icon }}</v-icon>
                            {{ stateMeta[item.status]?.title || item.status }}
                          </v-chip>
                          <span v-if="item.status === 'failed'" class="text-caption ml-1">
                            已重试 {{ item.retry_count }} 次
                          </span>
                        </td>
                        <td>{{ humanSize(item.size) }}</td>
                        <td>{{ humanTime(item.last_seen_at) }}</td>
                        <td class="text-right">
                          <v-btn v-if="item.status === 'failed'" size="small" variant="tonal"
                            color="primary" prepend-icon="mdi-refresh" @click="retryFile(item)">
                            重试
                          </v-btn>
                          <v-btn v-if="item.status !== 'copying'" size="small" variant="text"
                            color="error" prepend-icon="mdi-delete" @click="askDelete(item)">
                            删除
                          </v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                  <div v-else class="text-medium-emphasis pa-4">
                    暂无文件记录。第一轮运行出现「同步中」是正常异步状态, 下一轮自动结算为已同步。
                  </div>
                </div>
                <div class="cd2-pager">
                  <span class="text-caption text-medium-emphasis">共 {{ filesTotal }} 条</span>
                  <v-select v-model="pageSize" :items="pageSizeItems" density="compact"
                    hide-details class="cd2-pagesize" label="每页" />
                  <v-pagination v-model="page" :length="pageCount" density="compact"
                    :total-visible="5" />
                </div>
              </v-card>
            </v-window-item>
          </v-window>
        </template>
        <v-alert v-else type="info" variant="tonal">
          还没有配置任务, 点左侧「新建任务」新增一个。
        </v-alert>
      </main>
    </div>

    <v-dialog v-model="globalDialog.show" max-width="680">
      <v-card v-if="globalDialog.form">
        <v-card-title class="d-flex align-center">
          全局设置
          <v-spacer />
          <v-switch v-model="globalDialog.form.enabled" color="primary"
            hide-details label="启用插件" />
        </v-card-title>
        <v-card-text>
          <v-row>
            <v-col cols="12" md="7">
              <v-text-field v-model="globalDialog.form.cd2_address"
                label="CloudDrive2 gRPC 地址" placeholder="127.0.0.1:19798" />
            </v-col>
            <v-col cols="12" md="5">
              <v-text-field v-model="globalDialog.form.cd2_token" type="password"
                label="CD2 API Token" hint="移动模式需要带删除权限的 Token" persistent-hint />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.interval_minutes"
                type="number" label="定时间隔 (分钟)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.max_retries"
                type="number" label="失败最大重试次数" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.copy_timeout_seconds"
                type="number" label="提交复制超时 (秒)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.verify_wait_seconds"
                type="number" label="提交后等待校验 (秒)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.verify_interval_seconds"
                type="number" label="校验轮询间隔 (秒)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.pending_timeout_hours"
                type="number" label="同步中超时判失败 (小时)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.history_retention_days"
                type="number" label="成功历史保留 (天)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.failed_retention_days"
                type="number" label="失败历史保留 (天)" />
            </v-col>
            <v-col cols="6" md="4">
              <v-text-field v-model.number="globalDialog.form.state_tombstone_days"
                type="number" label="源消失宽限 (天)" />
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="globalDialog.show = false">取消</v-btn>
          <v-btn color="primary" @click="saveGlobal">保存全局设置</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="taskDialog.show" max-width="640">
      <v-card v-if="taskDialog.form">
        <v-card-title>{{ taskDialog.editing ? '编辑任务' : '新建任务' }}</v-card-title>
        <v-card-text>
          <div class="cd2-form-fields">
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field v-model="taskDialog.form.name" label="任务名称"
                placeholder="不填则用源目录" />
            </v-col>
            <v-col cols="12" md="6">
              <v-select v-model="taskDialog.form.mode" :items="modeItems" label="模式" />
            </v-col>
          </v-row>
          <div class="text-caption text-medium-emphasis mb-3">
            {{ modeHints[taskDialog.form.mode] }}
          </div>
          <v-text-field v-model="taskDialog.form.source_path" label="源目录 (A 网盘)"
            placeholder="/网盘名/源目录" />
          <v-text-field v-model="taskDialog.form.target_path" label="目标目录 (B 网盘)"
            placeholder="/网盘名/目标目录" />
          <v-row>
            <v-col cols="12" md="4">
              <v-select v-model="taskDialog.form.conflict_policy"
                :items="conflictItems" label="目标同名文件冲突策略" />
            </v-col>
            <v-col cols="12" md="4">
              <v-text-field v-model.number="taskDialog.form.max_concurrent_sync"
                type="number" min="1" label="同步线程"
                hint="每轮最多同时进行的文件数" persistent-hint />
            </v-col>
            <v-col cols="12" md="4">
              <v-switch v-model="taskDialog.form.enabled" label="启用任务"
                color="primary" hide-details />
              <v-switch v-if="taskDialog.form.mode === 'move'"
                v-model="taskDialog.form.delete_empty_dirs" color="primary"
                hide-details label="移动后清理源端空目录" />
            </v-col>
          </v-row>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="taskDialog.show = false">取消</v-btn>
          <v-btn color="primary" @click="saveTask">
            {{ taskDialog.editing ? '保存' : '创建任务' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="taskConfirmDelete.show" max-width="480">
      <v-card>
        <v-card-title>删除任务</v-card-title>
        <v-card-text>
          确认删除任务「{{ selected?.name }}」？只删除任务配置和它的同步状态记录，
          已经同步到目标端的文件不会被删除。
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="taskConfirmDelete.show = false">取消</v-btn>
          <v-btn color="error" @click="deleteTask">删除任务</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="confirm.show" max-width="480">
      <v-card>
        <v-card-title>确认删除</v-card-title>
        <v-card-text>
          <p>文件：{{ confirm.item?.file_name }}</p>
          <p class="mt-2">
            将删除<b>目标端</b>的这份副本, 并把该文件标记为已排除, 此任务以后不再同步它。
            源文件不会被删除。
          </p>
          <p v-if="confirm.item?.status === 'failed'" class="mt-2 text-medium-emphasis">
            失败项目在目标端通常没有完整副本, 删除等于直接排除该文件。
          </p>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirm.show = false">取消</v-btn>
          <v-btn color="error" @click="doDelete">删除并排除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.cd2-root {
  display: flex;
  flex-direction: column;
  height: min(880px, calc(100vh - 150px));
  min-height: 520px;
}
.cd2-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 4px 10px;
}
.cd2-body {
  flex: 1;
  display: flex;
  min-height: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.cd2-side {
  width: 288px;
  flex: 0 0 288px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.cd2-side-head {
  display: flex;
  align-items: center;
  padding: 12px 12px 6px;
  font-weight: 600;
}
.cd2-task-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 8px;
}
.cd2-task-item {
  padding: 12px;
  margin-bottom: 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  cursor: pointer;
}
.cd2-task-item:hover {
  background: rgba(var(--v-theme-primary), 0.06);
}
.cd2-task-item--active {
  border-color: rgba(var(--v-theme-primary), 0.45);
  background: rgba(var(--v-theme-primary), 0.08);
}
.cd2-side-foot {
  padding: 10px 12px 12px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
.cd2-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px;
}
.cd2-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.cd2-kv {
  display: grid;
  grid-template-columns: 110px 1fr;
  row-gap: 8px;
  column-gap: 12px;
}
.cd2-kv span {
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.cd2-run-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  flex-wrap: wrap;
}
.cd2-path {
  word-break: break-all;
}
.cd2-table-wrap {
  overflow-x: auto;
}
.cd2-table {
  min-width: 620px;
}
.cd2-table tbody td {
  padding-top: 16px;
  padding-bottom: 16px;
}
.cd2-table thead th {
  padding-top: 12px;
  padding-bottom: 12px;
}
.cd2-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 8px 12px;
  flex-wrap: wrap;
}
.cd2-pagesize {
  max-width: 96px;
}
.cd2-form-fields {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding-top: 6px;
}

/* 移动端: 上下堆叠, 左栏限高独立滚动, 统计卡两列, 表格横向滚动 */
@media (max-width: 900px) {
  .cd2-root {
    height: calc(100vh - 110px);
    min-height: 0;
  }
  .cd2-body {
    flex-direction: column;
  }
  .cd2-side {
    width: 100%;
    flex: 0 1 auto;
    max-height: 42%;
    border-right: none;
    border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  }
  .cd2-main {
    padding: 10px;
  }
  .cd2-stats {
    grid-template-columns: repeat(2, 1fr);
  }
  .cd2-header .v-btn {
    padding: 0 8px;
  }
}
</style>
