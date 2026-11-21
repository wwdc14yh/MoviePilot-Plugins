import { importShared } from './__federation_fn_import-CdTLGLGK.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,createBlock:_createBlock,createCommentVNode:_createCommentVNode} = await importShared('vue');


const _hoisted_1 = { class: "pa-2" };
const _hoisted_2 = { class: "d-flex align-center mb-2" };
const _hoisted_3 = { class: "text-caption text-medium-emphasis" };
const _hoisted_4 = { class: "d-flex justify-end ga-2" };

const {computed,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
},
  emits: ['save', 'close', 'switch'],
  setup(__props, { emit: __emit }) {

const props = __props;
const emit = __emit;

const modeItems = computed(() => {
  const items = [
    { title: '增量同步', value: 'sync' },
    { title: '移动', value: 'move' },
  ];
  if ((config.value?.tasks || []).some(t => t.mode === 'backup')) {
    items.push({ title: '备份 (旧任务)', value: 'backup' });
  }
  return items
});
const modeHints = {
  sync: '增量复制到目标；源文件变化会重新复制，源文件消失按宽限期清理同步状态（不动目标文件）。',
  backup: '只增不减：新文件复制过去，源文件变化时目标保留旧版、新版自动改名存入；源文件消失不处理目标。',
  move: '复制任务在 CD2 端完成确认后才删除源文件；未完成绝不删源，删源失败下一轮重试。可选清理源端空目录。',
};
const conflictItems = [
  { title: '用全局默认', value: '' },
  { title: '跳过 (Skip)', value: 'skip' },
  { title: '覆盖 (Overwrite)', value: 'overwrite' },
  { title: '重命名 (Rename)', value: 'rename' },
];

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
    max_concurrent_sync: 1,
  }
}

function normalize(cfg) {
  const c = JSON.parse(JSON.stringify(cfg || {}));
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
      }];
    } else {
      c.tasks = [newTask()];
    }
  }
  c.tasks = c.tasks.map(t => ({ ...newTask(), ...t }));
  return c
}

const config = ref(normalize(props.initialConfig));

function addTask() {
  config.value.tasks.push(newTask());
}
function removeTask(idx) {
  config.value.tasks.splice(idx, 1);
}
function saveConfig() {
  const out = JSON.parse(JSON.stringify(config.value));
  const seen = new Set();
  out.tasks = out.tasks.map(t => {
    // id 缺失或重复时重新生成, 避免两个任务共用同一份同步状态
    if (!t.id || seen.has(t.id)) {
      t = { ...t, id: Math.random().toString(16).slice(2, 14) + Date.now().toString(16) };
    }
    seen.add(t.id);
    return { ...t, name: t.name || t.source_path || '未命名任务' }
  });
  emit('save', out);
}

return (_ctx, _cache) => {
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_chip = _resolveComponent("v-chip");
  const _component_v_select = _resolveComponent("v-select");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[17] || (_cache[17] = [
            _createTextVNode("连接与全局设置", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_row, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.value.enabled,
                      "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((config.value.enabled) = $event)),
                      label: "启用插件",
                      color: "primary",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.value.onlyonce,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.onlyonce) = $event)),
                      label: "保存后立即运行一次",
                      color: "primary",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.value.debug_logging,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.debug_logging) = $event)),
                      label: "详细日志",
                      color: "primary",
                      "hide-details": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.interval_minutes,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.interval_minutes) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "扫描间隔 (分钟)",
                      hint: "所有任务共用这个周期",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.copy_poll_interval_seconds,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.copy_poll_interval_seconds) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "复制任务轮询间隔 (秒)",
                      hint: "后台拉取 CD2 任务状态对账的间隔",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "3"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.max_retries,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.max_retries) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "失败最大重试次数"
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
                      modelValue: config.value.cd2_address,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.cd2_address) = $event)),
                      label: "CloudDrive2 gRPC 地址",
                      placeholder: "127.0.0.1:19798",
                      hint: "CD2 的 gRPC 监听地址, 默认端口 19798",
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
                      modelValue: config.value.cd2_token,
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.cd2_token) = $event)),
                      type: "password",
                      label: "API Token",
                      hint: "在 CloudDrive2 设置中创建；移动模式需要删除权限",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
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
    _createElementVNode("div", _hoisted_2, [
      _cache[19] || (_cache[19] = _createElementVNode("span", { class: "text-h6" }, "任务列表", -1)),
      _createVNode(_component_v_spacer),
      _createVNode(_component_v_btn, {
        color: "primary",
        variant: "tonal",
        "prepend-icon": "mdi-plus",
        onClick: addTask
      }, {
        default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
          _createTextVNode("新增任务", -1)
        ]))]),
        _: 1
      })
    ]),
    _createVNode(_component_v_alert, {
      type: "info",
      variant: "tonal",
      class: "mb-4"
    }, {
      default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
        _createTextVNode(" 每个任务是一组独立的「源目录 → 目标目录」，有自己的模式和同步状态，互不影响。 复制是异步的：提交后先显示同步中，后续轮次自动结算，不会误判失败。 ", -1)
      ]))]),
      _: 1
    }),
    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(config.value.tasks, (task, idx) => {
      return (_openBlock(), _createBlock(_component_v_card, {
        key: task.id || idx,
        variant: "outlined",
        class: "mb-4"
      }, {
        default: _withCtx(() => [
          _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
            default: _withCtx(() => [
              _createVNode(_component_v_text_field, {
                modelValue: task.name,
                "onUpdate:modelValue": $event => ((task.name) = $event),
                label: "任务名称",
                density: "compact",
                "hide-details": "",
                style: {"max-width":"280px"}
              }, null, 8, ["modelValue", "onUpdate:modelValue"]),
              _createVNode(_component_v_chip, {
                class: "ml-3",
                size: "small",
                color: task.mode === 'move' ? 'warning' : task.mode === 'backup' ? 'info' : 'success'
              }, {
                default: _withCtx(() => [
                  _createTextVNode(_toDisplayString(modeItems.value.find(m => m.value === task.mode)?.title), 1)
                ]),
                _: 2
              }, 1032, ["color"]),
              _createVNode(_component_v_spacer),
              _createVNode(_component_v_switch, {
                modelValue: task.enabled,
                "onUpdate:modelValue": $event => ((task.enabled) = $event),
                label: "启用",
                color: "primary",
                "hide-details": "",
                density: "compact"
              }, null, 8, ["modelValue", "onUpdate:modelValue"]),
              _createVNode(_component_v_btn, {
                icon: "mdi-delete",
                variant: "text",
                color: "error",
                onClick: $event => (removeTask(idx))
              }, null, 8, ["onClick"])
            ]),
            _: 2
          }, 1024),
          _createVNode(_component_v_card_text, null, {
            default: _withCtx(() => [
              _createVNode(_component_v_row, null, {
                default: _withCtx(() => [
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_select, {
                        modelValue: task.mode,
                        "onUpdate:modelValue": $event => ((task.mode) = $event),
                        items: modeItems.value,
                        label: "模式"
                      }, null, 8, ["modelValue", "onUpdate:modelValue", "items"]),
                      _createElementVNode("div", _hoisted_3, _toDisplayString(modeHints[task.mode]), 1)
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_text_field, {
                        modelValue: task.source_path,
                        "onUpdate:modelValue": $event => ((task.source_path) = $event),
                        label: "源目录 (A 网盘)",
                        placeholder: "/网盘名/源目录"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_text_field, {
                        modelValue: task.target_path,
                        "onUpdate:modelValue": $event => ((task.target_path) = $event),
                        label: "目标目录 (B 网盘)",
                        placeholder: "/网盘名/目标目录"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_select, {
                        modelValue: task.conflict_policy,
                        "onUpdate:modelValue": $event => ((task.conflict_policy) = $event),
                        items: conflictItems,
                        label: "目标同名文件冲突策略"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "4"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_text_field, {
                        modelValue: task.max_concurrent_sync,
                        "onUpdate:modelValue": $event => ((task.max_concurrent_sync) = $event),
                        modelModifiers: { number: true },
                        type: "number",
                        min: "1",
                        label: "同步线程",
                        hint: "每轮最多同时进行的文件数",
                        "persistent-hint": ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  (task.mode === 'move')
                    ? (_openBlock(), _createBlock(_component_v_col, {
                        key: 0,
                        cols: "12",
                        md: "4"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_v_switch, {
                            modelValue: task.delete_empty_dirs,
                            "onUpdate:modelValue": $event => ((task.delete_empty_dirs) = $event),
                            color: "primary",
                            "hide-details": "",
                            label: "移动后清理源端空目录"
                          }, null, 8, ["modelValue", "onUpdate:modelValue"])
                        ]),
                        _: 2
                      }, 1024))
                    : _createCommentVNode("", true)
                ]),
                _: 2
              }, 1024)
            ]),
            _: 2
          }, 1024)
        ]),
        _: 2
      }, 1024))
    }), 128)),
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
            _createTextVNode("异步校验与记录清理（全局）", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createVNode(_component_v_row, null, {
              default: _withCtx(() => [
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.verify_wait_seconds,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.verify_wait_seconds) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "提交后本轮等待 (秒)",
                      hint: "0 = 全部留到下一轮结算",
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
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.verify_interval_seconds,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.verify_interval_seconds) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "等待时轮询间隔 (秒)"
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
                      modelValue: config.value.pending_timeout_hours,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.pending_timeout_hours) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "同步中超时判失败 (小时)"
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
                      modelValue: config.value.copy_timeout_seconds,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.copy_timeout_seconds) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "提交复制超时 (秒)",
                      hint: "跨盘提交慢时调大, 默认 180",
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
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.history_retention_days,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.history_retention_days) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "成功历史保留 (天)"
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
                      modelValue: config.value.failed_retention_days,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.failed_retention_days) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "失败历史保留 (天)"
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
                      modelValue: config.value.state_tombstone_days,
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.state_tombstone_days) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "源文件消失后宽限 (天)",
                      hint: "同步/移动模式的状态清理",
                      "persistent-hint": ""
                    }, null, 8, ["modelValue"])
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
    _createElementVNode("div", _hoisted_4, [
      _createVNode(_component_v_btn, {
        variant: "text",
        onClick: _cache[15] || (_cache[15] = $event => (emit('switch')))
      }, {
        default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
          _createTextVNode("查看任务", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        variant: "text",
        onClick: _cache[16] || (_cache[16] = $event => (emit('close')))
      }, {
        default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
          _createTextVNode("关闭", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        color: "primary",
        onClick: saveConfig
      }, {
        default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
          _createTextVNode("保存", -1)
        ]))]),
        _: 1
      })
    ])
  ]))
}
}

};

export { _sfc_main as default };
