import { importShared } from './__federation_fn_import-CdTLGLGK.js';
import { _ as _sfc_main$1 } from './Login115-ZIagGuBC.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock,renderList:_renderList,Fragment:_Fragment,normalizeClass:_normalizeClass,withModifiers:_withModifiers} = await importShared('vue');


const _hoisted_1 = { class: "p115-root" };
const _hoisted_2 = { class: "p115-header" };
const _hoisted_3 = { key: 0 };
const _hoisted_4 = { class: "p115-body" };
const _hoisted_5 = { class: "p115-side" };
const _hoisted_6 = { class: "p115-side-head" };
const _hoisted_7 = { class: "p115-task-list" };
const _hoisted_8 = ["onClick"];
const _hoisted_9 = { class: "d-flex align-center" };
const _hoisted_10 = { class: "font-weight-medium text-truncate" };
const _hoisted_11 = { class: "text-caption text-medium-emphasis p115-path" };
const _hoisted_12 = { class: "text-caption" };
const _hoisted_13 = {
  key: 0,
  class: "text-error"
};
const _hoisted_14 = { class: "text-caption text-medium-emphasis" };
const _hoisted_15 = {
  key: 0,
  class: "text-caption text-medium-emphasis pa-3"
};
const _hoisted_16 = { class: "p115-side-foot" };
const _hoisted_17 = { class: "p115-main" };
const _hoisted_18 = { class: "d-flex align-center flex-wrap ga-2 mb-1" };
const _hoisted_19 = { class: "text-h6" };
const _hoisted_20 = { class: "text-body-2 text-medium-emphasis mb-2 p115-path" };
const _hoisted_21 = { class: "p115-stats" };
const _hoisted_22 = { class: "text-h5" };
const _hoisted_23 = { class: "text-h5" };
const _hoisted_24 = { class: "text-h5" };
const _hoisted_25 = { class: "d-flex align-center flex-wrap ga-2 mb-3" };
const _hoisted_26 = { class: "text-caption text-medium-emphasis" };
const _hoisted_27 = { class: "d-flex align-center flex-wrap ga-2" };
const _hoisted_28 = { class: "text-subtitle-1 font-weight-medium" };
const _hoisted_29 = {
  key: 0,
  class: "text-body-2 text-medium-emphasis"
};
const _hoisted_30 = {
  key: 1,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_31 = {
  key: 2,
  class: "text-caption text-medium-emphasis"
};
const _hoisted_32 = { class: "text-caption text-medium-emphasis p115-path mt-1" };
const _hoisted_33 = { class: "d-flex align-center ga-2 mt-2" };
const _hoisted_34 = { class: "text-body-2" };
const _hoisted_35 = {
  key: 0,
  class: "text-body-2 mt-2"
};
const _hoisted_36 = { class: "text-caption text-medium-emphasis" };
const _hoisted_37 = {
  key: 1,
  class: "mt-2"
};
const _hoisted_38 = { class: "d-flex align-center ga-2" };
const _hoisted_39 = ["href"];
const _hoisted_40 = {
  key: 2,
  class: "text-caption text-error mt-2"
};
const _hoisted_41 = {
  key: 3,
  class: "text-caption text-medium-emphasis mt-1"
};
const _hoisted_42 = {
  key: 0,
  class: "text-medium-emphasis pa-4"
};
const _hoisted_43 = { class: "p115-pager" };
const _hoisted_44 = { class: "text-caption text-medium-emphasis" };
const _hoisted_45 = {
  key: 0,
  class: "text-caption text-medium-emphasis ml-2"
};
const _hoisted_46 = { class: "p115-table-wrap" };
const _hoisted_47 = { class: "p115-path" };
const _hoisted_48 = {
  key: 1,
  class: "text-medium-emphasis pa-4"
};
const _hoisted_49 = { class: "p115-pager" };
const _hoisted_50 = { class: "text-caption text-medium-emphasis" };
const _hoisted_51 = { class: "text-caption text-medium-emphasis" };
const _hoisted_52 = { class: "p115-form-fields" };

const {computed,onMounted,onUnmounted,ref,watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Page',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
},
  emits: ['action', 'switch', 'close'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const status = ref({ enabled: false, tasks: [], login: {}, config: {} });
const jobs = ref([]);
const jobsTotal = ref(0);
const jobsPage = ref(1);
const jobsPageSize = ref(20);
const jobFilter = ref('all');
const history = ref([]);
const historyTotal = ref(0);
const historyPage = ref(1);
const historyPageSize = ref(20);
const tab = ref('jobs');
const selectedId = ref('');
const selectedJobId = ref('');
const loading = ref(false);
const running = ref(false);
const message = ref('');
const taskDialog = ref({ show: false, editing: null, form: null });
const taskConfirmDelete = ref({ show: false });
const globalDialog = ref({ show: false, form: null });
const loginDialog = ref({ show: false });
const shareConfirm = ref({ show: false, job: null });

const completionRuleItems = [
  { title: '按季完结分享', value: 'season' },
  { title: '按整剧完结分享', value: 'show' },
];
const completionRuleHints = {
  season: '某季网盘集数 = TMDB 该季集数即分享该季, 不要求整剧完结 (如 S1 已完结、S2 在更时分享 S1)。',
  show: '整剧完结才分享: 要求 TMDB status=Ended, 并且全部季的网盘集数都 = TMDB 集数。',
};
const deleteSourceItems = [
  { title: '跟随全局', value: 'global' },
  { title: '删除源文件', value: 'yes' },
  { title: '保留源文件', value: 'no' },
];
const jobStatusMeta = {
  watching: { title: '待完结', color: 'grey', icon: 'mdi-eye-outline' },
  pending_delay: { title: '待分享 (延迟中)', color: 'warning', icon: 'mdi-timer-sand' },
  ready: { title: '待分享', color: 'info', icon: 'mdi-clock-outline' },
  copying: { title: '复制中', color: 'info', icon: 'mdi-content-copy' },
  renaming: { title: '重命名中', color: 'info', icon: 'mdi-pencil' },
  sharing: { title: '分享中', color: 'info', icon: 'mdi-share-variant' },
  verifying: { title: '校验中', color: 'info', icon: 'mdi-shield-check-outline' },
  pushing: { title: '推送中', color: 'info', icon: 'mdi-send' },
  shared: { title: '已分享', color: 'success', icon: 'mdi-check-circle' },
  cleaning_temp: { title: '清理临时文件', color: 'info', icon: 'mdi-broom' },
  deleting: { title: '删除源文件夹', color: 'warning', icon: 'mdi-delete-outline' },
  done: { title: '已完成', color: 'success', icon: 'mdi-check-circle-outline' },
  failed: { title: '失败', color: 'error', icon: 'mdi-alert-circle' },
};
const jobFilterItems = [
  { title: '全部', value: 'all' },
  { title: '待完结', value: 'watching' },
  { title: '待分享', value: 'pending_delay' },
  { title: '进行中', value: 'copying' },
  { title: '已分享', value: 'done' },
  { title: '失败', value: 'failed' },
];
const pageSizeItems = [10, 20, 50, 100];

function blankTask() {
  return { id: '', name: '', watch_path: '', enabled: true, cron: '', delay_hours: '', delete_source: 'global' }
}
function openNewTask() {
  taskDialog.value = { show: true, editing: null, form: blankTask() };
}
function openEditTask() {
  if (!selected.value) return
  const form = { ...blankTask(), ...JSON.parse(JSON.stringify(selected.value)) };
  // 后端存的是三态 (true/false/null), 表单下拉用 global/yes/no
  form.delete_source = selected.value.delete_source === true ? 'yes'
    : selected.value.delete_source === false ? 'no' : 'global';
  taskDialog.value = {
    show: true,
    editing: selected.value.id,
    form,
  };
}
async function saveTask() {
  const form = taskDialog.value.form;
  if (!form.watch_path) {
    message.value = '监听路径必填, 如 /MoviePilot Archived/电视剧/欧美剧';
    return
  }
  try {
    // 宿主把插件 API 注册为 FastAPI 路由: 只认查询参数,
    // JSON body / dict 参数会被判为请求参数不正确, 故一律拼查询串
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(form)) params.set(k, String(v ?? ''));
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/save_task?${params.toString()}`,
    ));
    if (res && res.ok === false) {
      message.value = '保存任务失败: ' + (res.error || '');
      return
    }
    taskDialog.value.show = false;
    message.value = res?.created ? '新任务已创建' : '任务已更新';
    await loadStatus();
    if (res?.task?.id) selectedId.value = res.task.id;
    emit('action');
  } catch (e) {
    message.value = '保存任务失败: ' + (e?.message || e);
  }
}
async function deleteTask() {
  taskConfirmDelete.value.show = false;
  if (!selected.value) return
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/delete_task?task_id=${encodeURIComponent(selected.value.id)}`,
    ));
    if (res && res.ok === false) {
      message.value = '删除任务失败: ' + (res.error || '');
      return
    }
    selectedId.value = '';
    message.value = '任务已删除 (已分享的链接不受影响)';
    await load();
  } catch (e) {
    message.value = '删除任务失败: ' + (e?.message || e);
  }
}

// ---------- 全局设置 (页面内直接编辑, 不依赖宿主跳转) ----------
function openGlobal() {
  const cfg = status.value.config || {};
  globalDialog.value = {
    show: true,
    form: {
      enabled: !!cfg.enabled,
      temp_path: cfg.temp_path || '/115分享暂存',
      completion_rule: cfg.completion_rule || 'season',
      delay_hours: cfg.delay_hours ?? 48,
      cron: cfg.cron || '0 */6 * * *',
      receive_code: cfg.receive_code || 'wwdc',
      tg_enabled: !!cfg.tg_enabled,
      tg_channel_chat_id: cfg.tg_channel_chat_id || '',
      tg_use_own_bot: !!cfg.tg_use_own_bot,
      tg_bot_token: cfg.tg_bot_token || '',
      tmdb_api_key: cfg.tmdb_api_key || '',
      tmdb_api_domain: cfg.tmdb_api_domain || 'api.themoviedb.org/3',
      tmdb_language: cfg.tmdb_language || 'zh-CN',
      max_retries: cfg.max_retries ?? 3,
      history_retention_days: cfg.history_retention_days ?? 90,
      recycle_password: cfg.recycle_password || '',
      debug_logging: !!cfg.debug_logging,
      proxy_url: cfg.proxy_url || '',
      delete_source: cfg.delete_source !== false,
      share_interval_seconds: cfg.share_interval_seconds ?? 60,
    },
  };
}
async function saveGlobal() {
  try {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(globalDialog.value.form)) {
      params.set(k, String(v ?? ''));
    }
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/save_global?${params.toString()}`,
    ));
    if (res && res.ok === false) {
      message.value = '保存全局设置失败: ' + (res.error || '');
      return
    }
    globalDialog.value.show = false;
    message.value = '全局设置已保存';
    await load();
    emit('action');
  } catch (e) {
    message.value = '保存全局设置失败: ' + (e?.message || e);
  }
}

const selected = computed(
  () => status.value.tasks.find(t => t.id === selectedId.value) || null,
);
const jobsPageCount = computed(() =>
  Math.max(1, Math.ceil(jobsTotal.value / jobsPageSize.value)),
);
const historyPageCount = computed(() =>
  Math.max(1, Math.ceil(historyTotal.value / historyPageSize.value)),
);
const login = computed(() => status.value.login || {});
const completionRule = computed(() => status.value.config?.completion_rule || 'season');

function unwrap(res) {
  return res && res.data !== undefined ? res.data : res
}
function toDate(v) {
  if (v === null || v === undefined || v === '') return null
  if (typeof v === 'number') return new Date(v > 1e12 ? v : v * 1000)
  if (/^\d+$/.test(String(v))) {
    const n = Number(v);
    return new Date(n > 1e12 ? n : n * 1000)
  }
  const d = new Date(v);
  return isNaN(d.getTime()) ? null : d
}
function fmtTime(v) {
  const d = toDate(v);
  if (!d) return ''
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function countdownText(eligibleAt) {
  const d = toDate(eligibleAt);
  if (!d) return ''
  const diff = d.getTime() - Date.now();
  if (diff <= 0) return '已到分享时间'
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (h >= 24) return `约 ${Math.floor(h / 24)} 天 ${h % 24} 小时后可分享`
  if (h > 0) return `约 ${h} 小时 ${m} 分后可分享`
  return `约 ${m} 分后可分享`
}
function jobProgress(job) {
  const total = Number(job.tmdb_count || 0);
  if (!total) return 0
  return Math.min(100, Math.round((Number(job.local_count || 0) / total) * 100))
}

async function loadStatus() {
  status.value =
    unwrap(await props.api.get(`plugin/${props.pluginId}/status`)) || status.value;
  if (!selectedId.value && status.value.tasks.length) {
    selectedId.value = status.value.tasks[0].id;
  }
  if (selectedId.value && !status.value.tasks.find(t => t.id === selectedId.value)) {
    selectedId.value = status.value.tasks[0]?.id || '';
  }
}
async function loadJobs() {
  if (!selectedId.value) { jobs.value = []; jobsTotal.value = 0; return }
  const params = new URLSearchParams({
    task_id: selectedId.value,
    page: String(jobsPage.value),
    page_size: String(jobsPageSize.value),
  });
  if (jobFilter.value !== 'all') params.set('status', jobFilter.value);
  const res = unwrap(await props.api.get(
    `plugin/${props.pluginId}/jobs?${params.toString()}`,
  )) || {};
  jobs.value = res.jobs || [];
  jobsTotal.value = res.total || 0;
}
async function loadHistory() {
  const params = new URLSearchParams({
    page: String(historyPage.value),
    page_size: String(historyPageSize.value),
  });
  if (selectedJobId.value) params.set('job_id', selectedJobId.value);
  const res = unwrap(await props.api.get(
    `plugin/${props.pluginId}/history?${params.toString()}`,
  )) || {};
  history.value = res.items || [];
  historyTotal.value = res.total || 0;
}
async function load() {
  if (!props.api || !props.pluginId) return
  loading.value = true;
  try {
    await loadStatus();
    await Promise.all([loadJobs(), loadHistory()]);
  } catch (e) {
    message.value = '加载失败: ' + (e?.message || e);
  } finally {
    loading.value = false;
  }
}
async function refreshQuiet() {
  try {
    await loadStatus();
    await Promise.all([loadJobs(), loadHistory()]);
  } catch (e) { /* 自动刷新失败保持沉默 */ }
}

async function scanTask(taskId) {
  running.value = true;
  message.value = '';
  try {
    const url = taskId
      ? `plugin/${props.pluginId}/scan_now?task_id=${encodeURIComponent(taskId)}`
      : `plugin/${props.pluginId}/scan_now?task_id=`;
    await props.api.post(url);
    message.value = '已触发扫描, 稍后刷新查看结果';
    await load();
    emit('action');
  } catch (e) {
    message.value = '扫描失败: ' + (e?.message || e);
  } finally {
    running.value = false;
  }
}

function askShareNow(job) {
  if (job.status === 'pending_delay') {
    shareConfirm.value = { show: true, job };
  } else {
    shareNow(job, false);
  }
}
async function shareNow(job, skipDelay) {
  shareConfirm.value.show = false;
  running.value = true;
  try {
    const params = new URLSearchParams({
      job_id: job.id,
      skip_delay: String(!!skipDelay),
    });
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/share_now?${params.toString()}`,
    ));
    if (res && res.ok === false) {
      message.value = '分享失败: ' + (res.error || '');
      return
    }
    message.value = '分享任务已提交, 完成后自动推送到 TG 频道';
    await load();
    emit('action');
  } catch (e) {
    message.value = '分享失败: ' + (e?.message || e);
  } finally {
    running.value = false;
  }
}
async function retryJob(job) {
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/retry?job_id=${encodeURIComponent(job.id)}`,
    ));
    message.value = (res && res.ok === false)
      ? '重试失败: ' + (res.error || '')
      : '已重新排队, 稍后刷新查看';
    setTimeout(load, 1500);
  } catch (e) {
    message.value = '重试失败: ' + (e?.message || e);
  }
}
async function copyLink(url) {
  if (!url) return
  try {
    await navigator.clipboard.writeText(url);
    message.value = '分享链接已复制';
  } catch (e) {
    const ta = document.createElement('textarea');
    ta.value = url;
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); message.value = '分享链接已复制'; } catch (e2) { /* 复制失败保持沉默 */ }
    document.body.removeChild(ta);
  }
}
function selectJob(job) {
  selectedJobId.value = job.id;
  historyPage.value = 1;
  loadHistory();
}

watch(selectedId, () => { jobsPage.value = 1; selectedJobId.value = ''; loadJobs(); loadHistory(); });
watch(jobFilter, () => { jobsPage.value = 1; loadJobs(); });
watch(jobsPage, loadJobs);
watch(jobsPageSize, () => { jobsPage.value = 1; loadJobs(); });
watch(historyPage, loadHistory);
watch(historyPageSize, () => { historyPage.value = 1; loadHistory(); });

let autoTimer = null;
onMounted(() => {
  load();
  // 页面打开期间每 20 秒自动刷新, 状态跟得上分享进度
  autoTimer = setInterval(refreshQuiet, 20000);
});
onUnmounted(() => {
  if (autoTimer) clearInterval(autoTimer);
});

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_tab = _resolveComponent("v-tab");
  const _component_v_tabs = _resolveComponent("v-tabs");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_progress_linear = _resolveComponent("v-progress-linear");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_pagination = _resolveComponent("v-pagination");
  const _component_v_window_item = _resolveComponent("v-window-item");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_table = _resolveComponent("v-table");
  const _component_v_window = _resolveComponent("v-window");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_dialog = _resolveComponent("v-dialog");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_row = _resolveComponent("v-row");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _createVNode(_component_v_icon, {
        color: "primary",
        class: "mr-2"
      }, {
        default: _withCtx(() => [...(_cache[50] || (_cache[50] = [
          _createTextVNode("mdi-share-variant", -1)
        ]))]),
        _: 1
      }),
      _cache[57] || (_cache[57] = _createElementVNode("div", { class: "p115-header-title" }, [
        _createElementVNode("div", { class: "text-subtitle-1 font-weight-medium" }, "115 剧集分享管家"),
        _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "完结剧集自动打包分享并推送到 TG 频道")
      ], -1)),
      _createVNode(_component_v_chip, {
        size: "small",
        class: "ml-2",
        color: status.value.enabled ? 'success' : 'grey'
      }, {
        default: _withCtx(() => [
          _createTextVNode(_toDisplayString(status.value.enabled ? '已启用' : '未启用'), 1)
        ]),
        _: 1
      }, 8, ["color"]),
      (login.value.logged_in)
        ? (_openBlock(), _createBlock(_component_v_chip, {
            key: 0,
            size: "small",
            color: "success",
            variant: "tonal",
            class: "ml-2"
          }, {
            default: _withCtx(() => [
              _cache[51] || (_cache[51] = _createTextVNode(" 115 已登录", -1)),
              (login.value.user_name)
                ? (_openBlock(), _createElementBlock("span", _hoisted_3, "：" + _toDisplayString(login.value.user_name), 1))
                : _createCommentVNode("", true)
            ]),
            _: 1
          }))
        : (_openBlock(), _createBlock(_component_v_chip, {
            key: 1,
            size: "small",
            color: "warning",
            variant: "tonal",
            class: "ml-2"
          }, {
            default: _withCtx(() => [...(_cache[52] || (_cache[52] = [
              _createTextVNode(" 115 未登录 ", -1)
            ]))]),
            _: 1
          })),
      _createVNode(_component_v_spacer),
      _createVNode(_component_v_btn, {
        variant: "tonal",
        color: "primary",
        "prepend-icon": "mdi-qrcode",
        onClick: _cache[0] || (_cache[0] = $event => (loginDialog.value.show = true))
      }, {
        default: _withCtx(() => [...(_cache[53] || (_cache[53] = [
          _createTextVNode("115 登录", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        variant: "tonal",
        color: "primary",
        "prepend-icon": "mdi-tune-variant",
        onClick: openGlobal
      }, {
        default: _withCtx(() => [...(_cache[54] || (_cache[54] = [
          _createTextVNode("全局设置", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        variant: "text",
        "prepend-icon": "mdi-refresh",
        loading: loading.value,
        onClick: load
      }, {
        default: _withCtx(() => [...(_cache[55] || (_cache[55] = [
          _createTextVNode("刷新", -1)
        ]))]),
        _: 1
      }, 8, ["loading"]),
      _createVNode(_component_v_btn, {
        variant: "text",
        "prepend-icon": "mdi-magnify-scan",
        loading: running.value,
        onClick: _cache[1] || (_cache[1] = $event => (scanTask()))
      }, {
        default: _withCtx(() => [...(_cache[56] || (_cache[56] = [
          _createTextVNode("立即扫描", -1)
        ]))]),
        _: 1
      }, 8, ["loading"])
    ]),
    (login.value.need_relogin)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: "error",
          variant: "tonal",
          class: "mb-3"
        }, {
          append: _withCtx(() => [
            _createVNode(_component_v_btn, {
              size: "small",
              variant: "text",
              onClick: _cache[2] || (_cache[2] = $event => (loginDialog.value.show = true))
            }, {
              default: _withCtx(() => [...(_cache[58] || (_cache[58] = [
                _createTextVNode("去扫码登录", -1)
              ]))]),
              _: 1
            })
          ]),
          default: _withCtx(() => [
            _cache[59] || (_cache[59] = _createTextVNode(" 115 登录已过期, 请重新扫码登录, 否则无法监听、复制和分享 ", -1))
          ]),
          _: 1
        }))
      : (!login.value.logged_in)
        ? (_openBlock(), _createBlock(_component_v_alert, {
            key: 1,
            type: "warning",
            variant: "tonal",
            class: "mb-3"
          }, {
            append: _withCtx(() => [
              _createVNode(_component_v_btn, {
                size: "small",
                variant: "text",
                onClick: _cache[3] || (_cache[3] = $event => (loginDialog.value.show = true))
              }, {
                default: _withCtx(() => [...(_cache[60] || (_cache[60] = [
                  _createTextVNode("去扫码登录", -1)
                ]))]),
                _: 1
              })
            ]),
            default: _withCtx(() => [
              _cache[61] || (_cache[61] = _createTextVNode(" 115 未登录, 请先扫码登录 ", -1))
            ]),
            _: 1
          }))
        : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_4, [
      _createElementVNode("aside", _hoisted_5, [
        _createElementVNode("div", _hoisted_6, [
          _cache[62] || (_cache[62] = _createTextVNode(" 监听任务 ", -1)),
          _createVNode(_component_v_chip, {
            class: "ml-2",
            size: "x-small"
          }, {
            default: _withCtx(() => [
              _createTextVNode(_toDisplayString(status.value.tasks.length), 1)
            ]),
            _: 1
          })
        ]),
        _createElementVNode("div", _hoisted_7, [
          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(status.value.tasks, (task) => {
            return (_openBlock(), _createElementBlock("div", {
              key: task.id,
              class: _normalizeClass(["p115-task-item", { 'p115-task-item--active': task.id === selectedId.value }]),
              onClick: $event => (selectedId.value = task.id)
            }, [
              _createElementVNode("div", _hoisted_9, [
                _createElementVNode("span", _hoisted_10, _toDisplayString(task.name), 1),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_icon, {
                  size: "x-small",
                  color: task.enabled ? 'success' : 'grey'
                }, {
                  default: _withCtx(() => [...(_cache[63] || (_cache[63] = [
                    _createTextVNode(" mdi-circle ", -1)
                  ]))]),
                  _: 1
                }, 8, ["color"])
              ]),
              _createElementVNode("div", _hoisted_11, _toDisplayString(task.watch_path), 1),
              _createElementVNode("div", _hoisted_12, [
                _createTextVNode(" 待完结 " + _toDisplayString(task.counts?.watching || 0) + " · 待分享 " + _toDisplayString(task.counts?.pending_delay || 0) + " · 已分享 " + _toDisplayString(task.counts?.done || 0) + " ", 1),
                (task.counts?.failed)
                  ? (_openBlock(), _createElementBlock("span", _hoisted_13, " · 失败 " + _toDisplayString(task.counts.failed), 1))
                  : _createCommentVNode("", true)
              ]),
              _createElementVNode("div", _hoisted_14, " 检查频率 " + _toDisplayString(task.cron || status.value.config?.cron || '0 */6 * * *'), 1)
            ], 10, _hoisted_8))
          }), 128)),
          (!status.value.tasks.length)
            ? (_openBlock(), _createElementBlock("div", _hoisted_15, " 还没有任务 "))
            : _createCommentVNode("", true)
        ]),
        _createElementVNode("div", _hoisted_16, [
          _createVNode(_component_v_btn, {
            block: "",
            color: "primary",
            variant: "tonal",
            "prepend-icon": "mdi-plus",
            onClick: openNewTask
          }, {
            default: _withCtx(() => [...(_cache[64] || (_cache[64] = [
              _createTextVNode("新建任务", -1)
            ]))]),
            _: 1
          })
        ])
      ]),
      _createElementVNode("main", _hoisted_17, [
        (selected.value)
          ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
              _createElementVNode("div", _hoisted_18, [
                _createVNode(_component_v_icon, {
                  size: "large",
                  color: "primary"
                }, {
                  default: _withCtx(() => [...(_cache[65] || (_cache[65] = [
                    _createTextVNode("mdi-television-classic", -1)
                  ]))]),
                  _: 1
                }),
                _createElementVNode("span", _hoisted_19, _toDisplayString(selected.value.name), 1),
                _createVNode(_component_v_chip, {
                  size: "small",
                  color: selected.value.enabled ? 'success' : 'grey'
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(selected.value.enabled ? '已启用' : '已停用'), 1)
                  ]),
                  _: 1
                }, 8, ["color"]),
                _createVNode(_component_v_chip, {
                  size: "small",
                  variant: "tonal"
                }, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(completionRuleItems.find(r => r.value === completionRule.value)?.title || '按季完结分享'), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  color: "primary",
                  variant: "tonal",
                  "prepend-icon": "mdi-magnify-scan",
                  loading: running.value,
                  onClick: _cache[4] || (_cache[4] = $event => (scanTask(selected.value.id)))
                }, {
                  default: _withCtx(() => [...(_cache[66] || (_cache[66] = [
                    _createTextVNode("立即扫描", -1)
                  ]))]),
                  _: 1
                }, 8, ["loading"]),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  "prepend-icon": "mdi-pencil",
                  onClick: openEditTask
                }, {
                  default: _withCtx(() => [...(_cache[67] || (_cache[67] = [
                    _createTextVNode("编辑任务", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  color: "error",
                  "prepend-icon": "mdi-delete",
                  onClick: _cache[5] || (_cache[5] = $event => (taskConfirmDelete.value.show = true))
                }, {
                  default: _withCtx(() => [...(_cache[68] || (_cache[68] = [
                    _createTextVNode("删除任务", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _createElementVNode("div", _hoisted_20, _toDisplayString(selected.value.watch_path) + " · 检查频率 " + _toDisplayString(selected.value.cron || status.value.config?.cron || '0 */6 * * *') + " · 延迟分享 " + _toDisplayString(selected.value.delay_hours ?? status.value.config?.delay_hours ?? 48) + " 小时 · 分享后" + _toDisplayString(selected.value.delete_source_effective === false ? '保留源' : '删除源'), 1),
              (message.value)
                ? (_openBlock(), _createBlock(_component_v_alert, {
                    key: 0,
                    type: "info",
                    variant: "tonal",
                    class: "mb-3"
                  }, {
                    default: _withCtx(() => [
                      _createTextVNode(_toDisplayString(message.value), 1)
                    ]),
                    _: 1
                  }))
                : _createCommentVNode("", true),
              _createVNode(_component_v_tabs, {
                modelValue: tab.value,
                "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((tab).value = $event)),
                density: "compact",
                class: "mb-3"
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_tab, { value: "jobs" }, {
                    default: _withCtx(() => [...(_cache[69] || (_cache[69] = [
                      _createTextVNode("剧集", -1)
                    ]))]),
                    _: 1
                  }),
                  _createVNode(_component_v_tab, { value: "history" }, {
                    default: _withCtx(() => [...(_cache[70] || (_cache[70] = [
                      _createTextVNode("分享历史", -1)
                    ]))]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue"]),
              _createVNode(_component_v_window, {
                modelValue: tab.value,
                "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((tab).value = $event))
              }, {
                default: _withCtx(() => [
                  _createVNode(_component_v_window_item, { value: "jobs" }, {
                    default: _withCtx(() => [
                      _createElementVNode("div", _hoisted_21, [
                        _createVNode(_component_v_card, { variant: "tonal" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_card_text, null, {
                              default: _withCtx(() => [
                                _cache[71] || (_cache[71] = _createElementVNode("div", { class: "text-caption" }, "待完结", -1)),
                                _createElementVNode("div", _hoisted_22, _toDisplayString(selected.value.counts?.watching || 0), 1),
                                _cache[72] || (_cache[72] = _createElementVNode("div", { class: "text-caption" }, "集数未齐或未到播出日", -1))
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_card, { variant: "tonal" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_card_text, null, {
                              default: _withCtx(() => [
                                _cache[73] || (_cache[73] = _createElementVNode("div", { class: "text-caption" }, "待分享", -1)),
                                _createElementVNode("div", _hoisted_23, _toDisplayString(selected.value.counts?.pending_delay || 0), 1),
                                _cache[74] || (_cache[74] = _createElementVNode("div", { class: "text-caption" }, "已完结, 在延迟分享期内", -1))
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_card, { variant: "tonal" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_card_text, null, {
                              default: _withCtx(() => [
                                _cache[75] || (_cache[75] = _createElementVNode("div", { class: "text-caption" }, "已分享", -1)),
                                _createElementVNode("div", _hoisted_24, _toDisplayString(selected.value.counts?.done || 0), 1),
                                _cache[76] || (_cache[76] = _createElementVNode("div", { class: "text-caption" }, "已分享并推送到 TG 频道", -1))
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_card, { variant: "tonal" }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_card_text, null, {
                              default: _withCtx(() => [
                                _cache[77] || (_cache[77] = _createElementVNode("div", { class: "text-caption" }, "失败", -1)),
                                _createElementVNode("div", {
                                  class: _normalizeClass(["text-h5", selected.value.counts?.failed ? 'text-error' : ''])
                                }, _toDisplayString(selected.value.counts?.failed || 0), 3),
                                _cache[78] || (_cache[78] = _createElementVNode("div", { class: "text-caption" }, "在剧集卡片里重试", -1))
                              ]),
                              _: 1
                            })
                          ]),
                          _: 1
                        })
                      ]),
                      _createElementVNode("div", _hoisted_25, [
                        _createVNode(_component_v_btn_toggle, {
                          modelValue: jobFilter.value,
                          "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((jobFilter).value = $event)),
                          mandatory: "",
                          density: "compact"
                        }, {
                          default: _withCtx(() => [
                            (_openBlock(), _createElementBlock(_Fragment, null, _renderList(jobFilterItems, (f) => {
                              return _createVNode(_component_v_btn, {
                                key: f.value,
                                value: f.value,
                                size: "small"
                              }, {
                                default: _withCtx(() => [
                                  _createTextVNode(_toDisplayString(f.title), 1)
                                ]),
                                _: 2
                              }, 1032, ["value"])
                            }), 64))
                          ]),
                          _: 1
                        }, 8, ["modelValue"]),
                        _createVNode(_component_v_spacer),
                        _createElementVNode("span", _hoisted_26, "共 " + _toDisplayString(jobsTotal.value) + " 部 / 季", 1)
                      ]),
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(jobs.value, (job) => {
                        return (_openBlock(), _createBlock(_component_v_card, {
                          key: job.id,
                          variant: "outlined",
                          class: _normalizeClass(["mb-3", { 'p115-job--active': job.id === selectedJobId.value }]),
                          onClick: $event => (selectJob(job))
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_card_text, null, {
                              default: _withCtx(() => [
                                _createElementVNode("div", _hoisted_27, [
                                  _createElementVNode("span", _hoisted_28, _toDisplayString(job.show_name), 1),
                                  (job.en_title && job.en_title !== job.show_name)
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_29, _toDisplayString(job.en_title), 1))
                                    : _createCommentVNode("", true),
                                  _createVNode(_component_v_chip, {
                                    size: "small",
                                    color: "primary",
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createTextVNode(" Season " + _toDisplayString(job.season_number), 1)
                                    ]),
                                    _: 2
                                  }, 1024),
                                  (job.year)
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_30, _toDisplayString(job.year), 1))
                                    : _createCommentVNode("", true),
                                  (job.tmdbid)
                                    ? (_openBlock(), _createElementBlock("span", _hoisted_31, " tmdbid-" + _toDisplayString(job.tmdbid), 1))
                                    : _createCommentVNode("", true),
                                  _createVNode(_component_v_chip, {
                                    size: "small",
                                    color: jobStatusMeta[job.status]?.color,
                                    variant: "tonal"
                                  }, {
                                    default: _withCtx(() => [
                                      _createVNode(_component_v_icon, {
                                        size: "small",
                                        class: "mr-1"
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(_toDisplayString(jobStatusMeta[job.status]?.icon), 1)
                                        ]),
                                        _: 2
                                      }, 1024),
                                      _createTextVNode(" " + _toDisplayString(jobStatusMeta[job.status]?.title || job.status), 1)
                                    ]),
                                    _: 2
                                  }, 1032, ["color"]),
                                  _createVNode(_component_v_spacer),
                                  (job.status === 'failed')
                                    ? (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 3,
                                        size: "small",
                                        variant: "tonal",
                                        color: "primary",
                                        "prepend-icon": "mdi-refresh",
                                        onClick: _withModifiers($event => (retryJob(job)), ["stop"])
                                      }, {
                                        default: _withCtx(() => [...(_cache[79] || (_cache[79] = [
                                          _createTextVNode(" 重试 ", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["onClick"]))
                                    : _createCommentVNode("", true),
                                  (['pending_delay', 'ready', 'failed'].includes(job.status))
                                    ? (_openBlock(), _createBlock(_component_v_btn, {
                                        key: 4,
                                        size: "small",
                                        color: "primary",
                                        variant: "tonal",
                                        "prepend-icon": "mdi-share-variant",
                                        loading: running.value,
                                        onClick: _withModifiers($event => (askShareNow(job)), ["stop"])
                                      }, {
                                        default: _withCtx(() => [...(_cache[80] || (_cache[80] = [
                                          _createTextVNode(" 立即分享 ", -1)
                                        ]))]),
                                        _: 1
                                      }, 8, ["loading", "onClick"]))
                                    : _createCommentVNode("", true)
                                ]),
                                _createElementVNode("div", _hoisted_32, _toDisplayString(job.source_path), 1),
                                _createElementVNode("div", _hoisted_33, [
                                  _createElementVNode("span", _hoisted_34, _toDisplayString(job.local_count || 0) + " / " + _toDisplayString(job.tmdb_count || 0) + " 集 ", 1),
                                  _createVNode(_component_v_progress_linear, {
                                    "model-value": jobProgress(job),
                                    color: "primary",
                                    height: "8",
                                    rounded: "",
                                    class: "flex-grow-1"
                                  }, null, 8, ["model-value"]),
                                  (job.tmdb_status)
                                    ? (_openBlock(), _createBlock(_component_v_chip, {
                                        key: 0,
                                        size: "x-small",
                                        variant: "outlined"
                                      }, {
                                        default: _withCtx(() => [
                                          _createTextVNode(" TMDB " + _toDisplayString(job.tmdb_status), 1)
                                        ]),
                                        _: 2
                                      }, 1024))
                                    : _createCommentVNode("", true)
                                ]),
                                (job.status === 'pending_delay' && job.eligible_at)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_35, [
                                      _createTextVNode(_toDisplayString(countdownText(job.eligible_at)) + " ", 1),
                                      _createElementVNode("span", _hoisted_36, " (" + _toDisplayString(fmtTime(job.eligible_at)) + " 可分享, 首次检出完结 " + _toDisplayString(fmtTime(job.first_completed_at)) + ") ", 1)
                                    ]))
                                  : _createCommentVNode("", true),
                                (job.share_url)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_37, [
                                      _createElementVNode("div", _hoisted_38, [
                                        _createElementVNode("a", {
                                          href: job.share_url,
                                          target: "_blank",
                                          rel: "noopener",
                                          class: "text-body-2 p115-path"
                                        }, _toDisplayString(job.share_url), 9, _hoisted_39),
                                        _createVNode(_component_v_btn, {
                                          size: "small",
                                          variant: "text",
                                          "prepend-icon": "mdi-content-copy",
                                          onClick: _withModifiers($event => (copyLink(job.share_url)), ["stop"])
                                        }, {
                                          default: _withCtx(() => [...(_cache[81] || (_cache[81] = [
                                            _createTextVNode("复制链接", -1)
                                          ]))]),
                                          _: 1
                                        }, 8, ["onClick"]),
                                        (job.receive_code)
                                          ? (_openBlock(), _createBlock(_component_v_chip, {
                                              key: 0,
                                              size: "small",
                                              variant: "tonal"
                                            }, {
                                              default: _withCtx(() => [
                                                _createTextVNode(" 提取码 " + _toDisplayString(job.receive_code), 1)
                                              ]),
                                              _: 2
                                            }, 1024))
                                          : _createCommentVNode("", true)
                                      ])
                                    ]))
                                  : _createCommentVNode("", true),
                                (job.last_error)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_40, _toDisplayString(job.last_error), 1))
                                  : _createCommentVNode("", true),
                                (job.updated_at)
                                  ? (_openBlock(), _createElementBlock("div", _hoisted_41, " 更新于 " + _toDisplayString(fmtTime(job.updated_at)), 1))
                                  : _createCommentVNode("", true)
                              ]),
                              _: 2
                            }, 1024)
                          ]),
                          _: 2
                        }, 1032, ["class", "onClick"]))
                      }), 128)),
                      (!jobs.value.length)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_42, " 暂无剧集记录。首次扫描后, 监听路径下的剧集会按季出现在这里。 "))
                        : _createCommentVNode("", true),
                      _createElementVNode("div", _hoisted_43, [
                        _createElementVNode("span", _hoisted_44, "共 " + _toDisplayString(jobsTotal.value) + " 条", 1),
                        _createVNode(_component_v_select, {
                          modelValue: jobsPageSize.value,
                          "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((jobsPageSize).value = $event)),
                          items: pageSizeItems,
                          density: "compact",
                          "hide-details": "",
                          class: "p115-pagesize",
                          label: "每页"
                        }, null, 8, ["modelValue"]),
                        _createVNode(_component_v_pagination, {
                          modelValue: jobsPage.value,
                          "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((jobsPage).value = $event)),
                          length: jobsPageCount.value,
                          density: "compact",
                          "total-visible": 5
                        }, null, 8, ["modelValue", "length"])
                      ])
                    ]),
                    _: 1
                  }),
                  _createVNode(_component_v_window_item, { value: "history" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_card, { variant: "outlined" }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card_title, { class: "text-subtitle-1" }, {
                            default: _withCtx(() => [
                              _cache[82] || (_cache[82] = _createTextVNode(" 分享历史 ", -1)),
                              (selectedJobId.value)
                                ? (_openBlock(), _createElementBlock("span", _hoisted_45, " 当前剧集: 点剧集卡片可切换 "))
                                : _createCommentVNode("", true)
                            ]),
                            _: 1
                          }),
                          _createElementVNode("div", _hoisted_46, [
                            (history.value.length)
                              ? (_openBlock(), _createBlock(_component_v_table, {
                                  key: 0,
                                  density: "comfortable",
                                  class: "p115-table"
                                }, {
                                  default: _withCtx(() => [
                                    _cache[83] || (_cache[83] = _createElementVNode("thead", null, [
                                      _createElementVNode("tr", null, [
                                        _createElementVNode("th", null, "时间"),
                                        _createElementVNode("th", null, "操作"),
                                        _createElementVNode("th", null, "结果"),
                                        _createElementVNode("th", null, "详情")
                                      ])
                                    ], -1)),
                                    _createElementVNode("tbody", null, [
                                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(history.value, (item) => {
                                        return (_openBlock(), _createElementBlock("tr", {
                                          key: item.id
                                        }, [
                                          _createElementVNode("td", null, _toDisplayString(fmtTime(item.created_at)), 1),
                                          _createElementVNode("td", null, _toDisplayString(item.action), 1),
                                          _createElementVNode("td", null, [
                                            _createVNode(_component_v_chip, {
                                              size: "small",
                                              color: item.result === 'success' ? 'success' : 'error',
                                              variant: "tonal"
                                            }, {
                                              default: _withCtx(() => [
                                                _createTextVNode(_toDisplayString(item.result === 'success' ? '成功' : (item.result || '失败')), 1)
                                              ]),
                                              _: 2
                                            }, 1032, ["color"])
                                          ]),
                                          _createElementVNode("td", _hoisted_47, _toDisplayString(item.detail), 1)
                                        ]))
                                      }), 128))
                                    ])
                                  ]),
                                  _: 1
                                }))
                              : (_openBlock(), _createElementBlock("div", _hoisted_48, " 暂无分享历史。点一张剧集卡片可只看该剧的历史, 不选则显示全部。 "))
                          ]),
                          _createElementVNode("div", _hoisted_49, [
                            _createElementVNode("span", _hoisted_50, "共 " + _toDisplayString(historyTotal.value) + " 条", 1),
                            _createVNode(_component_v_select, {
                              modelValue: historyPageSize.value,
                              "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((historyPageSize).value = $event)),
                              items: pageSizeItems,
                              density: "compact",
                              "hide-details": "",
                              class: "p115-pagesize",
                              label: "每页"
                            }, null, 8, ["modelValue"]),
                            _createVNode(_component_v_pagination, {
                              modelValue: historyPage.value,
                              "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((historyPage).value = $event)),
                              length: historyPageCount.value,
                              density: "compact",
                              "total-visible": 5
                            }, null, 8, ["modelValue", "length"])
                          ])
                        ]),
                        _: 1
                      })
                    ]),
                    _: 1
                  })
                ]),
                _: 1
              }, 8, ["modelValue"])
            ], 64))
          : (_openBlock(), _createBlock(_component_v_alert, {
              key: 1,
              type: "info",
              variant: "tonal"
            }, {
              default: _withCtx(() => [...(_cache[84] || (_cache[84] = [
                _createTextVNode(" 还没有配置任务, 点左侧「新建任务」新增一个。 ", -1)
              ]))]),
              _: 1
            }))
      ])
    ]),
    _createVNode(_component_v_dialog, {
      modelValue: loginDialog.value.show,
      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((loginDialog.value.show) = $event)),
      "max-width": "560"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[85] || (_cache[85] = [
                _createTextVNode("115 登录", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                _createVNode(_sfc_main$1, {
                  api: __props.api,
                  "plugin-id": __props.pluginId,
                  onChanged: loadStatus
                }, null, 8, ["api", "plugin-id"])
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[13] || (_cache[13] = $event => (loginDialog.value.show = false))
                }, {
                  default: _withCtx(() => [...(_cache[86] || (_cache[86] = [
                    _createTextVNode("关闭", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: globalDialog.value.show,
      "onUpdate:modelValue": _cache[36] || (_cache[36] = $event => ((globalDialog.value.show) = $event)),
      "max-width": "720"
    }, {
      default: _withCtx(() => [
        (globalDialog.value.form)
          ? (_openBlock(), _createBlock(_component_v_card, { key: 0 }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _cache[87] || (_cache[87] = _createTextVNode(" 全局设置 ", -1)),
                    _createVNode(_component_v_spacer),
                    _createVNode(_component_v_switch, {
                      modelValue: globalDialog.value.form.enabled,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((globalDialog.value.form.enabled) = $event)),
                      color: "primary",
                      "hide-details": "",
                      label: "启用插件"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_row, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_select, {
                              modelValue: globalDialog.value.form.completion_rule,
                              "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((globalDialog.value.form.completion_rule) = $event)),
                              items: completionRuleItems,
                              label: "剧集完结检查规则"
                            }, null, 8, ["modelValue"]),
                            _createElementVNode("div", _hoisted_51, _toDisplayString(completionRuleHints[globalDialog.value.form.completion_rule]), 1)
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.temp_path,
                              "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((globalDialog.value.form.temp_path) = $event)),
                              label: "115 临时分享路径",
                              placeholder: "/115分享暂存"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.delay_hours,
                              "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((globalDialog.value.form.delay_hours) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              label: "延迟分享 (小时)"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.cron,
                              "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((globalDialog.value.form.cron) = $event)),
                              label: "全局检查频率 (cron)",
                              placeholder: "0 */6 * * *"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.receive_code,
                              "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((globalDialog.value.form.receive_code) = $event)),
                              label: "分享提取码",
                              placeholder: "wwdc"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.tg_channel_chat_id,
                              "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((globalDialog.value.form.tg_channel_chat_id) = $event)),
                              label: "TG 频道 chat_id",
                              placeholder: "-100xxxxxxxxxx"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_switch, {
                              modelValue: globalDialog.value.form.tg_enabled,
                              "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((globalDialog.value.form.tg_enabled) = $event)),
                              label: "推送到 TG 频道",
                              color: "primary",
                              "hide-details": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_switch, {
                              modelValue: globalDialog.value.form.tg_use_own_bot,
                              "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((globalDialog.value.form.tg_use_own_bot) = $event)),
                              label: "使用自有 TG Bot",
                              color: "primary",
                              "hide-details": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.tg_bot_token,
                              "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((globalDialog.value.form.tg_bot_token) = $event)),
                              type: "password",
                              label: "自有 Bot Token",
                              hint: "使用自有 Bot 时填写, 否则复用 MoviePilot 已配的 TG Bot",
                              "persistent-hint": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.max_retries,
                              "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((globalDialog.value.form.max_retries) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              label: "失败最大重试次数"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.share_interval_seconds,
                              "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((globalDialog.value.form.share_interval_seconds) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              label: "批量分享间隔 (秒)",
                              hint: "两次创建分享之间至少间隔, 防 115 风控",
                              "persistent-hint": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "3"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.history_retention_days,
                              "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((globalDialog.value.form.history_retention_days) = $event)),
                              modelModifiers: { number: true },
                              type: "number",
                              label: "分享历史保留 (天)"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.tmdb_api_key,
                              "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((globalDialog.value.form.tmdb_api_key) = $event)),
                              type: "password",
                              label: "TMDB API Key (备用)",
                              hint: "留空 = 只用宿主 TMDB",
                              "persistent-hint": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.tmdb_api_domain,
                              "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((globalDialog.value.form.tmdb_api_domain) = $event)),
                              label: "TMDB 直调域名",
                              placeholder: "api.themoviedb.org/3"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "6",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.tmdb_language,
                              "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((globalDialog.value.form.tmdb_language) = $event)),
                              label: "TMDB 直调语言",
                              placeholder: "zh-CN"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.recycle_password,
                              "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((globalDialog.value.form.recycle_password) = $event)),
                              type: "password",
                              label: "115 回收站安全密钥",
                              hint: "留空 = 不清回收站",
                              "persistent-hint": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_switch, {
                              modelValue: globalDialog.value.form.delete_source,
                              "onUpdate:modelValue": _cache[32] || (_cache[32] = $event => ((globalDialog.value.form.delete_source) = $event)),
                              label: "分享后删除源文件",
                              color: "primary",
                              "hide-details": ""
                            }, null, 8, ["modelValue"]),
                            _cache[88] || (_cache[88] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "关 = 分享成功后保留源文件, 只删临时目录；任务里可单独覆盖", -1))
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "4"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_switch, {
                              modelValue: globalDialog.value.form.debug_logging,
                              "onUpdate:modelValue": _cache[33] || (_cache[33] = $event => ((globalDialog.value.form.debug_logging) = $event)),
                              label: "详细日志 (排查用)",
                              color: "primary",
                              "hide-details": ""
                            }, null, 8, ["modelValue"]),
                            _cache[89] || (_cache[89] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "打开后每次 115 调用、每季完结判定都会记到 MoviePilot 日志; 平时建议关", -1))
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "8"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: globalDialog.value.form.proxy_url,
                              "onUpdate:modelValue": _cache[34] || (_cache[34] = $event => ((globalDialog.value.form.proxy_url) = $event)),
                              label: "TMDB 直连代理地址",
                              placeholder: "http://192.168.2.2:7890",
                              hint: "仅 TMDB 直连兜底时走代理; 115 网盘调用一律直连; 留空 = 直连",
                              "persistent-hint": ""
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    _cache[90] || (_cache[90] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mt-1" }, " 检查频率：cron 表达式, 5 段 (分 时 日 月 周)；一天一次如 0 8 * * *；每 6 小时 0 */6 * * *。 分享有效期固定为长期, 提取码固定为上面填写的值 (默认 wwdc)。 ", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_actions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_spacer),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      onClick: _cache[35] || (_cache[35] = $event => (globalDialog.value.show = false))
                    }, {
                      default: _withCtx(() => [...(_cache[91] || (_cache[91] = [
                        _createTextVNode("取消", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      color: "primary",
                      onClick: saveGlobal
                    }, {
                      default: _withCtx(() => [...(_cache[92] || (_cache[92] = [
                        _createTextVNode("保存全局设置", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: taskDialog.value.show,
      "onUpdate:modelValue": _cache[44] || (_cache[44] = $event => ((taskDialog.value.show) = $event)),
      "max-width": "640"
    }, {
      default: _withCtx(() => [
        (taskDialog.value.form)
          ? (_openBlock(), _createBlock(_component_v_card, { key: 0 }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, null, {
                  default: _withCtx(() => [
                    _createTextVNode(_toDisplayString(taskDialog.value.editing ? '编辑任务' : '新建任务'), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_text, null, {
                  default: _withCtx(() => [
                    _createElementVNode("div", _hoisted_52, [
                      _createVNode(_component_v_row, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_text_field, {
                                modelValue: taskDialog.value.form.name,
                                "onUpdate:modelValue": _cache[37] || (_cache[37] = $event => ((taskDialog.value.form.name) = $event)),
                                label: "任务名称",
                                placeholder: "不填则用监听路径"
                              }, null, 8, ["modelValue"])
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_switch, {
                                modelValue: taskDialog.value.form.enabled,
                                "onUpdate:modelValue": _cache[38] || (_cache[38] = $event => ((taskDialog.value.form.enabled) = $event)),
                                label: "启用任务",
                                color: "primary",
                                "hide-details": ""
                              }, null, 8, ["modelValue"])
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_text_field, {
                        modelValue: taskDialog.value.form.watch_path,
                        "onUpdate:modelValue": _cache[39] || (_cache[39] = $event => ((taskDialog.value.form.watch_path) = $event)),
                        label: "监听路径 (115)",
                        placeholder: "/MoviePilot Archived/电视剧/欧美剧"
                      }, null, 8, ["modelValue"]),
                      _createVNode(_component_v_row, null, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_text_field, {
                                modelValue: taskDialog.value.form.cron,
                                "onUpdate:modelValue": _cache[40] || (_cache[40] = $event => ((taskDialog.value.form.cron) = $event)),
                                label: "检查频率 (cron)",
                                placeholder: "留空用全局, 如 0 8 * * *",
                                hint: "一天一次如 0 8 * * *；每 6 小时 0 */6 * * *",
                                "persistent-hint": ""
                              }, null, 8, ["modelValue"])
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_text_field, {
                                modelValue: taskDialog.value.form.delay_hours,
                                "onUpdate:modelValue": _cache[41] || (_cache[41] = $event => ((taskDialog.value.form.delay_hours) = $event)),
                                modelModifiers: { number: true },
                                type: "number",
                                label: "延迟分享 (小时)",
                                hint: "留空用全局",
                                "persistent-hint": ""
                              }, null, 8, ["modelValue"])
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_col, {
                            cols: "12",
                            md: "6"
                          }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_select, {
                                modelValue: taskDialog.value.form.delete_source,
                                "onUpdate:modelValue": _cache[42] || (_cache[42] = $event => ((taskDialog.value.form.delete_source) = $event)),
                                items: deleteSourceItems,
                                label: "分享后删除源文件",
                                hint: "跟随全局 = 用全局设置；选否则该任务分享后保留源文件",
                                "persistent-hint": ""
                              }, null, 8, ["modelValue"])
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }),
                      _cache[93] || (_cache[93] = _createElementVNode("div", { class: "text-caption text-medium-emphasis mt-1" }, " 检查频率：本任务独立的 cron 表达式；留空则用全局设置。 ", -1))
                    ])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_actions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_spacer),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      onClick: _cache[43] || (_cache[43] = $event => (taskDialog.value.show = false))
                    }, {
                      default: _withCtx(() => [...(_cache[94] || (_cache[94] = [
                        _createTextVNode("取消", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      color: "primary",
                      onClick: saveTask
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(taskDialog.value.editing ? '保存' : '创建任务'), 1)
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }))
          : _createCommentVNode("", true)
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: taskConfirmDelete.value.show,
      "onUpdate:modelValue": _cache[46] || (_cache[46] = $event => ((taskConfirmDelete.value.show) = $event)),
      "max-width": "480"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[95] || (_cache[95] = [
                _createTextVNode("删除任务", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                _createTextVNode(" 确认删除任务「" + _toDisplayString(selected.value?.name) + "」？只删除任务配置和它的分享状态记录， 已经分享出去的链接不受影响。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[45] || (_cache[45] = $event => (taskConfirmDelete.value.show = false))
                }, {
                  default: _withCtx(() => [...(_cache[96] || (_cache[96] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "error",
                  onClick: deleteTask
                }, {
                  default: _withCtx(() => [...(_cache[97] || (_cache[97] = [
                    _createTextVNode("删除任务", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"]),
    _createVNode(_component_v_dialog, {
      modelValue: shareConfirm.value.show,
      "onUpdate:modelValue": _cache[49] || (_cache[49] = $event => ((shareConfirm.value.show) = $event)),
      "max-width": "480"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[98] || (_cache[98] = [
                _createTextVNode("立即分享", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                _createTextVNode(" 「" + _toDisplayString(shareConfirm.value.job?.show_name) + " Season " + _toDisplayString(shareConfirm.value.job?.season_number) + "」 还在延迟分享期内, 现在分享会跳过剩余的洗板等待时间, 确认立即分享吗？ 分享前仍会重新检查完结状态, 分享成功后立即删除源文件夹。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[47] || (_cache[47] = $event => (shareConfirm.value.show = false))
                }, {
                  default: _withCtx(() => [...(_cache[99] || (_cache[99] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "primary",
                  onClick: _cache[48] || (_cache[48] = $event => (shareNow(shareConfirm.value.job, true)))
                }, {
                  default: _withCtx(() => [...(_cache[100] || (_cache[100] = [
                    _createTextVNode("跳过延迟, 立即分享", -1)
                  ]))]),
                  _: 1
                })
              ]),
              _: 1
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4762f722"]]);

export { Page as default };
