import { importShared } from './__federation_fn_import-CdTLGLGK.js';

const {toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock,createElementVNode:_createElementVNode,normalizeClass:_normalizeClass} = await importShared('vue');


const _hoisted_1 = { class: "pa-2" };
const _hoisted_2 = {
  key: 0,
  class: "text-error"
};
const _hoisted_3 = { class: "d-flex align-center mb-3 flex-wrap ga-2" };
const _hoisted_4 = { class: "text-h6" };
const _hoisted_5 = { class: "text-body-2 text-medium-emphasis mb-4" };
const _hoisted_6 = { class: "text-h5" };
const _hoisted_7 = { class: "text-caption" };
const _hoisted_8 = { class: "text-h5" };
const _hoisted_9 = { class: "text-h5" };
const _hoisted_10 = { class: "text-caption" };
const _hoisted_11 = { class: "text-caption text-medium-emphasis" };
const _hoisted_12 = {
  key: 0,
  class: "text-caption text-error"
};
const _hoisted_13 = {
  key: 0,
  class: "text-caption ml-1"
};
const _hoisted_14 = { class: "text-right" };
const _hoisted_15 = { class: "text-caption text-medium-emphasis mb-3" };
const _hoisted_16 = {
  key: 0,
  class: "mt-2 text-medium-emphasis"
};

const {computed,onMounted,ref,watch} = await importShared('vue');



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

const status = ref({ enabled: false, tasks: [], states: {} });
const files = ref([]);
const selectedId = ref('');
const filter = ref('all');
const loading = ref(false);
const running = ref(false);
const message = ref('');
const confirm = ref({ show: false, item: null });
const taskDialog = ref({ show: false, editing: null, form: null });
const taskConfirmDelete = ref({ show: false });

const modeItems = [
  { title: '同步', value: 'sync' },
  { title: '备份', value: 'backup' },
  { title: '移动', value: 'move' },
];
const modeHints = {
  sync: '增量复制；源变化重传，源消失按宽限期处理状态。',
  backup: '只增不减；源变化时目标保留旧版、新版改名存入；源消失不动目标。',
  move: '复制并校验完成后才删源文件；未完成绝不删源。可选清理源端空目录。',
};
const conflictItems = [
  { title: '用全局默认', value: '' },
  { title: '跳过 (Skip)', value: 'skip' },
  { title: '覆盖 (Overwrite)', value: 'overwrite' },
  { title: '重命名 (Rename)', value: 'rename' },
];

function blankTask() {
  return {
    id: '', name: '', enabled: true, mode: 'sync',
    source_path: '', target_path: '', conflict_policy: '',
    delete_empty_dirs: false,
  }
}
function openNewTask() {
  taskDialog.value = { show: true, editing: null, form: blankTask() };
}
function openEditTask() {
  if (!selected.value) return
  taskDialog.value = {
    show: true,
    editing: selected.value.id,
    form: { ...blankTask(), ...JSON.parse(JSON.stringify(selected.value)) },
  };
}
async function saveTask() {
  const form = taskDialog.value.form;
  if (!form.source_path || !form.target_path) {
    message.value = '源目录和目标目录必填';
    return
  }
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/save_task`, { ...form },
    ));
    if (!res?.ok) {
      message.value = '保存任务失败: ' + (res?.error || '');
      return
    }
    taskDialog.value.show = false;
    message.value = res.created ? '新任务已创建' : '任务已更新';
    await loadStatus();
    if (res.task?.id) selectedId.value = res.task.id;
    await loadFiles();
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
    if (!res?.ok) {
      message.value = '删除任务失败: ' + (res?.error || '');
      return
    }
    selectedId.value = '';
    message.value = '任务已删除（已同步到目标端的文件不会被删）';
    await load();
  } catch (e) {
    message.value = '删除任务失败: ' + (e?.message || e);
  }
}

const modeMeta = {
  sync: { title: '同步', color: 'success', icon: 'mdi-sync' },
  backup: { title: '备份', color: 'info', icon: 'mdi-archive-arrow-down' },
  move: { title: '移动', color: 'warning', icon: 'mdi-file-move' },
};
const stateMeta = {
  done: { title: '已同步', color: 'success', icon: 'mdi-check-circle' },
  copying: { title: '同步中', color: 'info', icon: 'mdi-progress-clock' },
  failed: { title: '失败', color: 'error', icon: 'mdi-alert-circle' },
  source_gone: { title: '源已消失', color: 'grey', icon: 'mdi-file-remove' },
  excluded: { title: '已排除', color: 'grey', icon: 'mdi-cancel' },
};
const filterItems = [
  { title: '全部', value: 'all' },
  { title: '已同步', value: 'done' },
  { title: '同步中', value: 'copying' },
  { title: '失败', value: 'failed' },
];

const selected = computed(
  () => status.value.tasks.find(t => t.id === selectedId.value) || null,
);
const filteredFiles = computed(() =>
  filter.value === 'all'
    ? files.value
    : files.value.filter(f => f.status === filter.value),
);

function unwrap(res) {
  return res && res.data !== undefined ? res.data : res
}
function humanSize(size) {
  let v = Number(size || 0);
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return (i === 0 ? v : v.toFixed(2)) + ' ' + units[i]
}
function humanTime(ts) {
  if (!ts) return ''
  const d = new Date(Number(ts) * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function loadStatus() {
  status.value =
    unwrap(await props.api.get(`plugin/${props.pluginId}/status`)) || status.value;
  if (!selectedId.value && status.value.tasks.length) {
    selectedId.value = status.value.tasks[0].id;
  }
}
async function loadFiles() {
  if (!selectedId.value) { files.value = []; return }
  files.value =
    unwrap(await props.api.get(
      `plugin/${props.pluginId}/files?task_id=${encodeURIComponent(selectedId.value)}&limit=200`,
    )) || [];
}
async function load() {
  if (!props.api || !props.pluginId) return
  loading.value = true;
  try {
    await loadStatus();
    await loadFiles();
  } catch (e) {
    message.value = '加载失败: ' + (e?.message || e);
  } finally {
    loading.value = false;
  }
}

async function runOnce(taskId) {
  running.value = true;
  message.value = '';
  try {
    const url = taskId
      ? `plugin/${props.pluginId}/run_once?task_id=${encodeURIComponent(taskId)}`
      : `plugin/${props.pluginId}/run_once`;
    await props.api.post(url);
    await load();
    emit('action');
  } catch (e) {
    message.value = '运行失败: ' + (e?.message || e);
  } finally {
    running.value = false;
  }
}

async function retryFile(item) {
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/retry_file?state_key=${encodeURIComponent(item.state_key)}`,
    ));
    message.value = res?.ok ? '已重新排队, 任务已在后台重跑' : ('重试失败: ' + (res?.error || ''));
    setTimeout(load, 1500);
  } catch (e) {
    message.value = '重试失败: ' + (e?.message || e);
  }
}

function askDelete(item) {
  confirm.value = { show: true, item };
}
async function doDelete() {
  const item = confirm.value.item;
  confirm.value.show = false;
  if (!item) return
  try {
    const res = unwrap(await props.api.post(
      `plugin/${props.pluginId}/delete_file?state_key=${encodeURIComponent(item.state_key)}`,
    ));
    message.value = res?.ok ? '已删除目标副本并排除该文件' : ('删除失败: ' + (res?.error || ''));
    await load();
  } catch (e) {
    message.value = '删除失败: ' + (e?.message || e);
  }
}

watch(selectedId, loadFiles);
onMounted(load);

return (_ctx, _cache) => {
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_list_item_title = _resolveComponent("v-list-item-title");
  const _component_v_list_item_subtitle = _resolveComponent("v-list-item-subtitle");
  const _component_v_list_item = _resolveComponent("v-list-item");
  const _component_v_list = _resolveComponent("v-list");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_card_actions = _resolveComponent("v-card-actions");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_btn_toggle = _resolveComponent("v-btn-toggle");
  const _component_v_table = _resolveComponent("v-table");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_dialog = _resolveComponent("v-dialog");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_row, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, {
          cols: "12",
          md: "3"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_card, {
              variant: "outlined",
              class: "fill-height d-flex flex-column"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                  default: _withCtx(() => [
                    _cache[17] || (_cache[17] = _createTextVNode(" 同步任务 ", -1)),
                    _createVNode(_component_v_chip, {
                      class: "ml-2",
                      size: "small"
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(status.value.tasks.length), 1)
                      ]),
                      _: 1
                    }),
                    _createVNode(_component_v_spacer),
                    _createVNode(_component_v_chip, {
                      size: "small",
                      color: status.value.enabled ? 'success' : 'grey'
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(status.value.enabled ? '运行中' : '未启用'), 1)
                      ]),
                      _: 1
                    }, 8, ["color"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_list, {
                  class: "flex-grow-1",
                  lines: "two"
                }, {
                  default: _withCtx(() => [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(status.value.tasks, (task) => {
                      return (_openBlock(), _createBlock(_component_v_list_item, {
                        key: task.id,
                        active: task.id === selectedId.value,
                        color: "primary",
                        onClick: $event => (selectedId.value = task.id)
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_list_item_title, { class: "d-flex align-center" }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(task.name) + " ", 1),
                              _createVNode(_component_v_spacer),
                              _createVNode(_component_v_icon, {
                                size: "x-small",
                                color: task.enabled ? 'success' : 'grey'
                              }, {
                                default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
                                  _createTextVNode("mdi-circle", -1)
                                ]))]),
                                _: 1
                              }, 8, ["color"])
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode(_component_v_list_item_subtitle, null, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(modeMeta[task.mode]?.title) + " · " + _toDisplayString(task.source_path) + " → " + _toDisplayString(task.target_path), 1)
                            ]),
                            _: 2
                          }, 1024),
                          _createVNode(_component_v_list_item_subtitle, null, {
                            default: _withCtx(() => [
                              _createTextVNode(" 已同步 " + _toDisplayString(task.states?.done || 0) + " · 同步中 " + _toDisplayString(task.states?.copying || 0) + " ", 1),
                              (task.states?.failed)
                                ? (_openBlock(), _createElementBlock("span", _hoisted_2, " · 失败 " + _toDisplayString(task.states.failed), 1))
                                : _createCommentVNode("", true)
                            ]),
                            _: 2
                          }, 1024)
                        ]),
                        _: 2
                      }, 1032, ["active", "onClick"]))
                    }), 128)),
                    (!status.value.tasks.length)
                      ? (_openBlock(), _createBlock(_component_v_list_item, { key: 0 }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_list_item_subtitle, null, {
                              default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                                _createTextVNode("还没有任务", -1)
                              ]))]),
                              _: 1
                            })
                          ]),
                          _: 1
                        }))
                      : _createCommentVNode("", true)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_actions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      block: "",
                      color: "primary",
                      variant: "tonal",
                      "prepend-icon": "mdi-plus",
                      onClick: openNewTask
                    }, {
                      default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                        _createTextVNode("新建任务", -1)
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
        }),
        _createVNode(_component_v_col, {
          cols: "12",
          md: "9"
        }, {
          default: _withCtx(() => [
            (selected.value)
              ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                  _createElementVNode("div", _hoisted_3, [
                    _createVNode(_component_v_icon, {
                      size: "large",
                      color: modeMeta[selected.value.mode]?.color
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(modeMeta[selected.value.mode]?.icon), 1)
                      ]),
                      _: 1
                    }, 8, ["color"]),
                    _createElementVNode("span", _hoisted_4, _toDisplayString(selected.value.name), 1),
                    _createVNode(_component_v_chip, {
                      size: "small",
                      color: modeMeta[selected.value.mode]?.color
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(modeMeta[selected.value.mode]?.title), 1)
                      ]),
                      _: 1
                    }, 8, ["color"]),
                    _createVNode(_component_v_chip, {
                      size: "small",
                      color: selected.value.enabled ? 'success' : 'grey'
                    }, {
                      default: _withCtx(() => [
                        _createTextVNode(_toDisplayString(selected.value.enabled ? '已启用' : '已停用'), 1)
                      ]),
                      _: 1
                    }, 8, ["color"]),
                    _createVNode(_component_v_spacer),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      "prepend-icon": "mdi-refresh",
                      loading: loading.value,
                      onClick: load
                    }, {
                      default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                        _createTextVNode("刷新", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      color: "primary",
                      variant: "tonal",
                      "prepend-icon": "mdi-play",
                      loading: running.value,
                      onClick: _cache[0] || (_cache[0] = $event => (runOnce(selected.value.id)))
                    }, {
                      default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                        _createTextVNode("运行此任务", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      "prepend-icon": "mdi-play-circle-outline",
                      loading: running.value,
                      onClick: _cache[1] || (_cache[1] = $event => (runOnce()))
                    }, {
                      default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
                        _createTextVNode("运行全部", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"]),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      "prepend-icon": "mdi-pencil",
                      onClick: openEditTask
                    }, {
                      default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                        _createTextVNode("编辑任务", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      color: "error",
                      "prepend-icon": "mdi-delete",
                      onClick: _cache[2] || (_cache[2] = $event => (taskConfirmDelete.value.show = true))
                    }, {
                      default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
                        _createTextVNode("删除任务", -1)
                      ]))]),
                      _: 1
                    })
                  ]),
                  _createElementVNode("div", _hoisted_5, _toDisplayString(selected.value.source_path) + " → " + _toDisplayString(selected.value.target_path), 1),
                  _createVNode(_component_v_row, { class: "mb-2" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_col, {
                        cols: "6",
                        md: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, { variant: "tonal" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_text, null, {
                                default: _withCtx(() => [
                                  _cache[26] || (_cache[26] = _createElementVNode("div", { class: "text-caption" }, "已同步文件", -1)),
                                  _createElementVNode("div", _hoisted_6, _toDisplayString(selected.value.states?.done || 0), 1),
                                  _createElementVNode("div", _hoisted_7, "共 " + _toDisplayString(humanSize(selected.value.done_size)), 1)
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "6",
                        md: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, { variant: "tonal" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_text, null, {
                                default: _withCtx(() => [
                                  _cache[27] || (_cache[27] = _createElementVNode("div", { class: "text-caption" }, "正在同步", -1)),
                                  _createElementVNode("div", _hoisted_8, _toDisplayString(selected.value.states?.copying || 0), 1),
                                  _cache[28] || (_cache[28] = _createElementVNode("div", { class: "text-caption" }, "异步复制进行中, 下轮自动结算", -1))
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "6",
                        md: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, { variant: "tonal" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_text, null, {
                                default: _withCtx(() => [
                                  _cache[29] || (_cache[29] = _createElementVNode("div", { class: "text-caption" }, "失败项目", -1)),
                                  _createElementVNode("div", {
                                    class: _normalizeClass(["text-h5", selected.value.states?.failed ? 'text-error' : ''])
                                  }, _toDisplayString(selected.value.states?.failed || 0), 3),
                                  _cache[30] || (_cache[30] = _createElementVNode("div", { class: "text-caption" }, "可在下方列表重试或删除", -1))
                                ]),
                                _: 1
                              })
                            ]),
                            _: 1
                          })
                        ]),
                        _: 1
                      }),
                      _createVNode(_component_v_col, {
                        cols: "6",
                        md: "3"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_card, { variant: "tonal" }, {
                            default: _withCtx(() => [
                              _createVNode(_component_v_card_text, null, {
                                default: _withCtx(() => [
                                  _cache[31] || (_cache[31] = _createElementVNode("div", { class: "text-caption" }, "源已消失 / 已排除", -1)),
                                  _createElementVNode("div", _hoisted_9, _toDisplayString((selected.value.states?.source_gone || 0) + (selected.value.states?.excluded || 0)), 1),
                                  _createElementVNode("div", _hoisted_10, "消失 " + _toDisplayString(selected.value.states?.source_gone || 0) + " · 排除 " + _toDisplayString(selected.value.states?.excluded || 0), 1)
                                ]),
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
                  }),
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
                  _createVNode(_component_v_card, { variant: "outlined" }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
                        default: _withCtx(() => [
                          _cache[32] || (_cache[32] = _createTextVNode(" 同步文件 ", -1)),
                          _createVNode(_component_v_chip, {
                            class: "ml-2",
                            size: "small"
                          }, {
                            default: _withCtx(() => [
                              _createTextVNode(_toDisplayString(filteredFiles.value.length), 1)
                            ]),
                            _: 1
                          }),
                          _createVNode(_component_v_spacer),
                          _createVNode(_component_v_btn_toggle, {
                            modelValue: filter.value,
                            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((filter).value = $event)),
                            mandatory: "",
                            density: "compact"
                          }, {
                            default: _withCtx(() => [
                              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(filterItems, (f) => {
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
                          }, 8, ["modelValue"])
                        ]),
                        _: 1
                      }),
                      (filteredFiles.value.length)
                        ? (_openBlock(), _createBlock(_component_v_table, {
                            key: 0,
                            density: "comfortable"
                          }, {
                            default: _withCtx(() => [
                              _cache[35] || (_cache[35] = _createElementVNode("thead", null, [
                                _createElementVNode("tr", null, [
                                  _createElementVNode("th", null, "文件"),
                                  _createElementVNode("th", null, "状态"),
                                  _createElementVNode("th", null, "大小"),
                                  _createElementVNode("th", null, "更新时间"),
                                  _createElementVNode("th", { class: "text-right" }, "操作")
                                ])
                              ], -1)),
                              _createElementVNode("tbody", null, [
                                (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(filteredFiles.value, (item) => {
                                  return (_openBlock(), _createElementBlock("tr", {
                                    key: item.state_key
                                  }, [
                                    _createElementVNode("td", null, [
                                      _createElementVNode("div", null, _toDisplayString(item.file_name), 1),
                                      _createElementVNode("div", _hoisted_11, _toDisplayString(item.target_path), 1),
                                      (item.last_error)
                                        ? (_openBlock(), _createElementBlock("div", _hoisted_12, _toDisplayString(item.last_error), 1))
                                        : _createCommentVNode("", true)
                                    ]),
                                    _createElementVNode("td", null, [
                                      _createVNode(_component_v_chip, {
                                        size: "small",
                                        color: stateMeta[item.status]?.color,
                                        variant: "tonal"
                                      }, {
                                        default: _withCtx(() => [
                                          _createVNode(_component_v_icon, {
                                            size: "small",
                                            class: "mr-1"
                                          }, {
                                            default: _withCtx(() => [
                                              _createTextVNode(_toDisplayString(stateMeta[item.status]?.icon), 1)
                                            ]),
                                            _: 2
                                          }, 1024),
                                          _createTextVNode(" " + _toDisplayString(stateMeta[item.status]?.title || item.status), 1)
                                        ]),
                                        _: 2
                                      }, 1032, ["color"]),
                                      (item.status === 'failed')
                                        ? (_openBlock(), _createElementBlock("span", _hoisted_13, " 已重试 " + _toDisplayString(item.retry_count) + " 次 ", 1))
                                        : _createCommentVNode("", true)
                                    ]),
                                    _createElementVNode("td", null, _toDisplayString(humanSize(item.size)), 1),
                                    _createElementVNode("td", null, _toDisplayString(humanTime(item.last_seen_at)), 1),
                                    _createElementVNode("td", _hoisted_14, [
                                      (item.status === 'failed')
                                        ? (_openBlock(), _createBlock(_component_v_btn, {
                                            key: 0,
                                            size: "small",
                                            variant: "tonal",
                                            color: "primary",
                                            "prepend-icon": "mdi-refresh",
                                            onClick: $event => (retryFile(item))
                                          }, {
                                            default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
                                              _createTextVNode(" 重试 ", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["onClick"]))
                                        : _createCommentVNode("", true),
                                      (item.status !== 'copying')
                                        ? (_openBlock(), _createBlock(_component_v_btn, {
                                            key: 1,
                                            size: "small",
                                            variant: "text",
                                            color: "error",
                                            "prepend-icon": "mdi-delete",
                                            onClick: $event => (askDelete(item))
                                          }, {
                                            default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
                                              _createTextVNode(" 删除 ", -1)
                                            ]))]),
                                            _: 1
                                          }, 8, ["onClick"]))
                                        : _createCommentVNode("", true)
                                    ])
                                  ]))
                                }), 128))
                              ])
                            ]),
                            _: 1
                          }))
                        : (_openBlock(), _createBlock(_component_v_card_text, {
                            key: 1,
                            class: "text-medium-emphasis"
                          }, {
                            default: _withCtx(() => [...(_cache[36] || (_cache[36] = [
                              _createTextVNode(" 暂无文件记录。第一轮运行出现「同步中」是正常异步状态, 下一轮自动结算为已同步。 ", -1)
                            ]))]),
                            _: 1
                          }))
                    ]),
                    _: 1
                  })
                ], 64))
              : (_openBlock(), _createBlock(_component_v_alert, {
                  key: 1,
                  type: "info",
                  variant: "tonal"
                }, {
                  default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                    _createTextVNode(" 还没有配置任务, 点左侧「新建任务」去配置页新增。 ", -1)
                  ]))]),
                  _: 1
                }))
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_dialog, {
      modelValue: taskDialog.value.show,
      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((taskDialog.value.show) = $event)),
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
                    _createVNode(_component_v_row, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_text_field, {
                              modelValue: taskDialog.value.form.name,
                              "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((taskDialog.value.form.name) = $event)),
                              label: "任务名称",
                              placeholder: "不填则用源目录"
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
                              modelValue: taskDialog.value.form.mode,
                              "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((taskDialog.value.form.mode) = $event)),
                              items: modeItems,
                              label: "模式"
                            }, null, 8, ["modelValue"])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }),
                    _createElementVNode("div", _hoisted_15, _toDisplayString(modeHints[taskDialog.value.form.mode]), 1),
                    _createVNode(_component_v_text_field, {
                      modelValue: taskDialog.value.form.source_path,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((taskDialog.value.form.source_path) = $event)),
                      label: "源目录 (A 网盘)",
                      placeholder: "/网盘名/源目录"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_text_field, {
                      modelValue: taskDialog.value.form.target_path,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((taskDialog.value.form.target_path) = $event)),
                      label: "目标目录 (B 网盘)",
                      placeholder: "/网盘名/目标目录"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_v_row, null, {
                      default: _withCtx(() => [
                        _createVNode(_component_v_col, {
                          cols: "12",
                          md: "6"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_v_select, {
                              modelValue: taskDialog.value.form.conflict_policy,
                              "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((taskDialog.value.form.conflict_policy) = $event)),
                              items: conflictItems,
                              label: "目标同名文件冲突策略"
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
                              "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((taskDialog.value.form.enabled) = $event)),
                              label: "启用任务",
                              color: "primary",
                              "hide-details": ""
                            }, null, 8, ["modelValue"]),
                            (taskDialog.value.form.mode === 'move')
                              ? (_openBlock(), _createBlock(_component_v_switch, {
                                  key: 0,
                                  modelValue: taskDialog.value.form.delete_empty_dirs,
                                  "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((taskDialog.value.form.delete_empty_dirs) = $event)),
                                  color: "primary",
                                  "hide-details": "",
                                  label: "移动后清理源端空目录"
                                }, null, 8, ["modelValue"]))
                              : _createCommentVNode("", true)
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    })
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_card_actions, null, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_spacer),
                    _createVNode(_component_v_btn, {
                      variant: "text",
                      onClick: _cache[11] || (_cache[11] = $event => (taskDialog.value.show = false))
                    }, {
                      default: _withCtx(() => [...(_cache[38] || (_cache[38] = [
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
      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((taskConfirmDelete.value.show) = $event)),
      "max-width": "480"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[39] || (_cache[39] = [
                _createTextVNode("删除任务", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                _createTextVNode(" 确认删除任务「" + _toDisplayString(selected.value?.name) + "」？只删除任务配置和它的同步状态记录， 已经同步到目标端的文件不会被删除。 ", 1)
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[13] || (_cache[13] = $event => (taskConfirmDelete.value.show = false))
                }, {
                  default: _withCtx(() => [...(_cache[40] || (_cache[40] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "error",
                  onClick: deleteTask
                }, {
                  default: _withCtx(() => [...(_cache[41] || (_cache[41] = [
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
      modelValue: confirm.value.show,
      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((confirm.value.show) = $event)),
      "max-width": "480"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_card_title, null, {
              default: _withCtx(() => [...(_cache[42] || (_cache[42] = [
                _createTextVNode("确认删除", -1)
              ]))]),
              _: 1
            }),
            _createVNode(_component_v_card_text, null, {
              default: _withCtx(() => [
                _createElementVNode("p", null, "文件：" + _toDisplayString(confirm.value.item?.file_name), 1),
                _cache[43] || (_cache[43] = _createElementVNode("p", { class: "mt-2" }, [
                  _createTextVNode(" 将删除"),
                  _createElementVNode("b", null, "目标端"),
                  _createTextVNode("的这份副本, 并把该文件标记为已排除, 此任务以后不再同步它。 源文件不会被删除。 ")
                ], -1)),
                (confirm.value.item?.status === 'failed')
                  ? (_openBlock(), _createElementBlock("p", _hoisted_16, " 失败项目在目标端通常没有完整副本, 删除等于直接排除该文件。 "))
                  : _createCommentVNode("", true)
              ]),
              _: 1
            }),
            _createVNode(_component_v_card_actions, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_spacer),
                _createVNode(_component_v_btn, {
                  variant: "text",
                  onClick: _cache[15] || (_cache[15] = $event => (confirm.value.show = false))
                }, {
                  default: _withCtx(() => [...(_cache[44] || (_cache[44] = [
                    _createTextVNode("取消", -1)
                  ]))]),
                  _: 1
                }),
                _createVNode(_component_v_btn, {
                  color: "error",
                  onClick: doDelete
                }, {
                  default: _withCtx(() => [...(_cache[45] || (_cache[45] = [
                    _createTextVNode("删除并排除", -1)
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

export { _sfc_main as default };
