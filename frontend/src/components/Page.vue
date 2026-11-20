<script setup>
import { computed, onMounted, ref, watch } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
})
const emit = defineEmits(['action', 'switch', 'close'])

const status = ref({ enabled: false, tasks: [], states: {} })
const files = ref([])
const selectedId = ref('')
const filter = ref('all')
const loading = ref(false)
const running = ref(false)
const message = ref('')
const confirm = ref({ show: false, item: null })
const taskDialog = ref({ show: false, editing: null, form: null })
const taskConfirmDelete = ref({ show: false })

const modeItems = [
  { title: '同步', value: 'sync' },
  { title: '备份', value: 'backup' },
  { title: '移动', value: 'move' },
]
const modeHints = {
  sync: '增量复制；源变化重传，源消失按宽限期处理状态。',
  backup: '只增不减；源变化时目标保留旧版、新版改名存入；源消失不动目标。',
  move: '复制并校验完成后才删源文件；未完成绝不删源。可选清理源端空目录。',
}
const conflictItems = [
  { title: '用全局默认', value: '' },
  { title: '跳过 (Skip)', value: 'skip' },
  { title: '覆盖 (Overwrite)', value: 'overwrite' },
  { title: '重命名 (Rename)', value: 'rename' },
]

function blankTask() {
  return {
    id: '', name: '', enabled: true, mode: 'sync',
    source_path: '', target_path: '', conflict_policy: '',
    delete_empty_dirs: false,
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
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/save_task`, { ...form },
    ))
    if (!res?.ok) {
      message.value = '保存任务失败: ' + (res?.error || '')
      return
    }
    taskDialog.value.show = false
    message.value = res.created ? '新任务已创建' : '任务已更新'
    await loadStatus()
    if (res.task?.id) selectedId.value = res.task.id
    await loadFiles()
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

const modeMeta = {
  sync: { title: '同步', color: 'success', icon: 'mdi-sync' },
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

const selected = computed(
  () => status.value.tasks.find(t => t.id === selectedId.value) || null,
)
const filteredFiles = computed(() =>
  filter.value === 'all'
    ? files.value
    : files.value.filter(f => f.status === filter.value),
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
}
async function loadFiles() {
  if (!selectedId.value) { files.value = []; return }
  files.value =
    unwrap(await props.api.get(
      `plugin/${props.pluginId}/files?task_id=${encodeURIComponent(selectedId.value)}&limit=200`,
    )) || []
}
async function load() {
  if (!props.api || !props.pluginId) return
  loading.value = true
  try {
    await loadStatus()
    await loadFiles()
  } catch (e) {
    message.value = '加载失败: ' + (e?.message || e)
  } finally {
    loading.value = false
  }
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

watch(selectedId, loadFiles)
onMounted(load)
</script>

<template>
  <div class="pa-2">
    <v-row>
      <!-- 左: 任务列表 -->
      <v-col cols="12" md="3">
        <v-card variant="outlined" class="fill-height d-flex flex-column">
          <v-card-title class="d-flex align-center">
            同步任务
            <v-chip class="ml-2" size="small">{{ status.tasks.length }}</v-chip>
            <v-spacer />
            <v-chip size="small" :color="status.enabled ? 'success' : 'grey'">
              {{ status.enabled ? '运行中' : '未启用' }}
            </v-chip>
          </v-card-title>
          <v-list class="flex-grow-1" lines="two">
            <v-list-item
              v-for="task in status.tasks"
              :key="task.id"
              :active="task.id === selectedId"
              color="primary"
              @click="selectedId = task.id"
            >
              <v-list-item-title class="d-flex align-center">
                {{ task.name }}
                <v-spacer />
                <v-icon size="x-small"
                  :color="task.enabled ? 'success' : 'grey'">mdi-circle</v-icon>
              </v-list-item-title>
              <v-list-item-subtitle>
                {{ modeMeta[task.mode]?.title }} · {{ task.source_path }} → {{ task.target_path }}
              </v-list-item-subtitle>
              <v-list-item-subtitle>
                已同步 {{ task.states?.done || 0 }} · 同步中 {{ task.states?.copying || 0 }}
                <span v-if="task.states?.failed" class="text-error">
                  · 失败 {{ task.states.failed }}
                </span>
              </v-list-item-subtitle>
            </v-list-item>
            <v-list-item v-if="!status.tasks.length">
              <v-list-item-subtitle>还没有任务</v-list-item-subtitle>
            </v-list-item>
          </v-list>
          <v-card-actions>
            <v-btn block color="primary" variant="tonal" prepend-icon="mdi-plus"
              @click="openNewTask">新建任务</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <!-- 右: 选中任务详情 -->
      <v-col cols="12" md="9">
        <template v-if="selected">
          <div class="d-flex align-center mb-3 flex-wrap ga-2">
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
            <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loading" @click="load">刷新</v-btn>
            <v-btn color="primary" variant="tonal" prepend-icon="mdi-play"
              :loading="running" @click="runOnce(selected.id)">运行此任务</v-btn>
            <v-btn variant="text" prepend-icon="mdi-play-circle-outline"
              :loading="running" @click="runOnce()">运行全部</v-btn>
            <v-btn variant="text" prepend-icon="mdi-pencil" @click="openEditTask">编辑任务</v-btn>
            <v-btn variant="text" color="error" prepend-icon="mdi-delete"
              @click="taskConfirmDelete.show = true">删除任务</v-btn>
          </div>
          <div class="text-body-2 text-medium-emphasis mb-4">
            {{ selected.source_path }} → {{ selected.target_path }}
          </div>

          <v-row class="mb-2">
            <v-col cols="6" md="3">
              <v-card variant="tonal">
                <v-card-text>
                  <div class="text-caption">已同步文件</div>
                  <div class="text-h5">{{ selected.states?.done || 0 }}</div>
                  <div class="text-caption">共 {{ humanSize(selected.done_size) }}</div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="6" md="3">
              <v-card variant="tonal">
                <v-card-text>
                  <div class="text-caption">正在同步</div>
                  <div class="text-h5">{{ selected.states?.copying || 0 }}</div>
                  <div class="text-caption">异步复制进行中, 下轮自动结算</div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="6" md="3">
              <v-card variant="tonal">
                <v-card-text>
                  <div class="text-caption">失败项目</div>
                  <div class="text-h5" :class="selected.states?.failed ? 'text-error' : ''">
                    {{ selected.states?.failed || 0 }}
                  </div>
                  <div class="text-caption">可在下方列表重试或删除</div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="6" md="3">
              <v-card variant="tonal">
                <v-card-text>
                  <div class="text-caption">源已消失 / 已排除</div>
                  <div class="text-h5">
                    {{ (selected.states?.source_gone || 0) + (selected.states?.excluded || 0) }}
                  </div>
                  <div class="text-caption">消失 {{ selected.states?.source_gone || 0 }} · 排除 {{ selected.states?.excluded || 0 }}</div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <v-alert v-if="message" type="info" variant="tonal" class="mb-3">{{ message }}</v-alert>

          <v-card variant="outlined">
            <v-card-title class="d-flex align-center">
              同步文件
              <v-chip class="ml-2" size="small">{{ filteredFiles.length }}</v-chip>
              <v-spacer />
              <v-btn-toggle v-model="filter" mandatory density="compact">
                <v-btn v-for="f in filterItems" :key="f.value" :value="f.value" size="small">
                  {{ f.title }}
                </v-btn>
              </v-btn-toggle>
            </v-card-title>
            <v-table v-if="filteredFiles.length" density="comfortable">
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
                <tr v-for="item in filteredFiles" :key="item.state_key">
                  <td>
                    <div>{{ item.file_name }}</div>
                    <div class="text-caption text-medium-emphasis">{{ item.target_path }}</div>
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
            <v-card-text v-else class="text-medium-emphasis">
              暂无文件记录。第一轮运行出现「同步中」是正常异步状态, 下一轮自动结算为已同步。
            </v-card-text>
          </v-card>
        </template>
        <v-alert v-else type="info" variant="tonal">
          还没有配置任务, 点左侧「新建任务」去配置页新增。
        </v-alert>
      </v-col>
    </v-row>

    <v-dialog v-model="taskDialog.show" max-width="640">
      <v-card v-if="taskDialog.form">
        <v-card-title>{{ taskDialog.editing ? '编辑任务' : '新建任务' }}</v-card-title>
        <v-card-text>
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
            <v-col cols="12" md="6">
              <v-select v-model="taskDialog.form.conflict_policy"
                :items="conflictItems" label="目标同名文件冲突策略" />
            </v-col>
            <v-col cols="12" md="6">
              <v-switch v-model="taskDialog.form.enabled" label="启用任务"
                color="primary" hide-details />
              <v-switch v-if="taskDialog.form.mode === 'move'"
                v-model="taskDialog.form.delete_empty_dirs" color="primary"
                hide-details label="移动后清理源端空目录" />
            </v-col>
          </v-row>
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
