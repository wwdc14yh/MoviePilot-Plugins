import { importShared } from './__federation_fn_import-CdTLGLGK.js';
import { _ as _sfc_main$1 } from './Login115-ZIagGuBC.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "pa-2" };
const _hoisted_2 = { class: "text-caption text-medium-emphasis" };
const _hoisted_3 = {
  key: 0,
  class: "text-body-2 mt-2"
};
const _hoisted_4 = {
  key: 1,
  class: "text-error"
};
const _hoisted_5 = { class: "d-flex align-center mb-2" };
const _hoisted_6 = { class: "d-flex justify-end ga-2" };

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

const completionRuleItems = [
  { title: '按季完结分享', value: 'season' },
  { title: '按整剧完结分享', value: 'show' },
];
const completionRuleHints = {
  season: '某季网盘集数 = TMDB 该季集数即分享该季, 不要求整剧完结 (如 S1 已完结、S2 在更时分享 S1)。',
  show: '整剧完结才分享: 要求 TMDB status=Ended, 并且全部季的网盘集数都 = TMDB 集数。',
};
const deleteSourceItems = [
  { title: '跟随全局', value: '' },
  { title: '删除源文件', value: true },
  { title: '保留源文件', value: false },
];

function newTask() {
  return {
    id: Math.random().toString(16).slice(2, 14),
    name: '',
    watch_path: '',
    enabled: true,
    cron: '',
    delay_hours: '',
    delete_source: '',
  }
}

function normalize(cfg) {
  const c = JSON.parse(JSON.stringify(cfg || {}));
  if (!Array.isArray(c.tasks)) {
    // 没有任务就是空列表, 不从旧字段拼凑任务 (防删光后复活)
    c.tasks = [];
  }
  c.tasks = c.tasks.map(t => ({ ...newTask(), ...t }));
  if (c.completion_rule !== 'show') c.completion_rule = 'season';
  if (typeof c.delete_source !== 'boolean') c.delete_source = true;
  if (typeof c.share_interval_seconds !== 'number'
      || c.share_interval_seconds < 0) c.share_interval_seconds = 60;
  return c
}

const config = ref(normalize(props.initialConfig));

const tmdbTestId = ref('');
const tmdbTestResult = ref(null);
const tmdbTesting = ref(false);

function addTask() {
  config.value.tasks.push(newTask());
}
function removeTask(idx) {
  config.value.tasks.splice(idx, 1);
}
async function testTmdb() {
  if (!tmdbTestId.value || !props.api || !props.pluginId) return
  tmdbTesting.value = true;
  tmdbTestResult.value = null;
  try {
    const res = await props.api.get(
      `plugin/${props.pluginId}/tmdb_test?tmdbid=${encodeURIComponent(tmdbTestId.value)}`,
    );
    tmdbTestResult.value = (res && res.data !== undefined) ? res.data : res;
  } catch (e) {
    tmdbTestResult.value = { ok: false, error: String(e?.message || e) };
  } finally {
    tmdbTesting.value = false;
  }
}
function saveConfig() {
  const out = JSON.parse(JSON.stringify(config.value));
  const seen = new Set();
  out.tasks = out.tasks.map(t => {
    // id 缺失或重复时重新生成, 避免两个任务共用同一份状态
    if (!t.id || seen.has(t.id)) {
      t = { ...t, id: Math.random().toString(16).slice(2, 14) + Date.now().toString(16) };
    }
    seen.add(t.id);
    return { ...t, name: t.name || t.watch_path || '未命名任务' }
  });
  emit('save', out);
}

return (_ctx, _cache) => {
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");
  const _component_v_switch = _resolveComponent("v-switch");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_text_field = _resolveComponent("v-text-field");
  const _component_v_row = _resolveComponent("v-row");
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_spacer = _resolveComponent("v-spacer");
  const _component_v_alert = _resolveComponent("v-alert");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
            _createTextVNode("115 登录", -1)
          ]))]),
          _: 1
        }),
        _createVNode(_component_v_card_text, null, {
          default: _withCtx(() => [
            _createVNode(_sfc_main$1, {
              api: __props.api,
              "plugin-id": __props.pluginId
            }, null, 8, ["api", "plugin-id"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
            _createTextVNode("全局设置", -1)
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
                      modelValue: config.value.tg_enabled,
                      "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((config.value.tg_enabled) = $event)),
                      label: "推送到 TG 频道",
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
                    _createVNode(_component_v_select, {
                      modelValue: config.value.completion_rule,
                      "onUpdate:modelValue": _cache[2] || (_cache[2] = $event => ((config.value.completion_rule) = $event)),
                      items: completionRuleItems,
                      label: "剧集完结检查规则"
                    }, null, 8, ["modelValue"]),
                    _createElementVNode("div", _hoisted_2, _toDisplayString(completionRuleHints[config.value.completion_rule]), 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "6"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.temp_path,
                      "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((config.value.temp_path) = $event)),
                      label: "115 临时分享路径",
                      placeholder: "/115分享暂存",
                      hint: "完结剧集先站内复制到这里重命名、分享, 分享成功后删除临时文件",
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
                      modelValue: config.value.delay_hours,
                      "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((config.value.delay_hours) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "延迟分享 (小时)",
                      hint: "完结后等多久再分享, 用于留出洗板时间",
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
                      modelValue: config.value.cron,
                      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((config.value.cron) = $event)),
                      label: "全局检查频率 (cron)",
                      placeholder: "0 */6 * * *",
                      hint: "5 段 cron: 分 时 日 月 周; 一天一次如 0 8 * * *",
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
                      modelValue: config.value.receive_code,
                      "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((config.value.receive_code) = $event)),
                      label: "分享提取码",
                      placeholder: "wwdc",
                      hint: "固定提取码, 默认 wwdc",
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
                      "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((config.value.max_retries) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "失败最大重试次数"
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
                      modelValue: config.value.share_interval_seconds,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((config.value.share_interval_seconds) = $event)),
                      modelModifiers: { number: true },
                      type: "number",
                      label: "批量分享间隔 (秒)",
                      hint: "两次创建分享之间至少间隔, 防 115 风控; 0 = 不延迟",
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
                      modelValue: config.value.tg_channel_chat_id,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((config.value.tg_channel_chat_id) = $event)),
                      label: "TG 频道 chat_id",
                      placeholder: "-100xxxxxxxxxx",
                      hint: "推送目标频道, Bot 须为频道管理员",
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
                    _createVNode(_component_v_switch, {
                      modelValue: config.value.tg_use_own_bot,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((config.value.tg_use_own_bot) = $event)),
                      label: "使用自有 TG Bot",
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
                      modelValue: config.value.tg_bot_token,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((config.value.tg_bot_token) = $event)),
                      type: "password",
                      label: "自有 Bot Token",
                      hint: "使用自有 Bot 时填写, 否则复用 MoviePilot 已配的 TG Bot",
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
                      modelValue: config.value.tmdb_api_key,
                      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((config.value.tmdb_api_key) = $event)),
                      type: "password",
                      label: "TMDB API Key (备用)",
                      hint: "留空 = 只用宿主自带 TMDB; 填了 = 宿主调不通时改用直调",
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
                      modelValue: config.value.tmdb_api_domain,
                      "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((config.value.tmdb_api_domain) = $event)),
                      label: "TMDB 直调域名",
                      placeholder: "api.themoviedb.org/3"
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
                      modelValue: config.value.tmdb_language,
                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((config.value.tmdb_language) = $event)),
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
                      modelValue: config.value.history_retention_days,
                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((config.value.history_retention_days) = $event)),
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
                      modelValue: config.value.recycle_password,
                      "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((config.value.recycle_password) = $event)),
                      type: "password",
                      label: "115 回收站安全密钥",
                      hint: "留空 = 删临时文件后不清回收站; 填 6 位密钥才清理",
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
                      modelValue: config.value.delete_source,
                      "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((config.value.delete_source) = $event)),
                      label: "分享后删除源文件",
                      color: "primary",
                      "hide-details": ""
                    }, null, 8, ["modelValue"]),
                    _cache[25] || (_cache[25] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "关 = 分享成功后保留源文件, 只删临时目录；任务里可单独覆盖", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_switch, {
                      modelValue: config.value.debug_logging,
                      "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((config.value.debug_logging) = $event)),
                      label: "详细日志 (排查用)",
                      color: "primary",
                      "hide-details": ""
                    }, null, 8, ["modelValue"]),
                    _cache[26] || (_cache[26] = _createElementVNode("div", { class: "text-caption text-medium-emphasis" }, "打开后每次 115 调用、每季完结判定都会记到 MoviePilot 日志; 平时建议关", -1))
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "8"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_text_field, {
                      modelValue: config.value.proxy_url,
                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((config.value.proxy_url) = $event)),
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
            })
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createVNode(_component_v_card, {
      variant: "outlined",
      class: "mb-4"
    }, {
      default: _withCtx(() => [
        _createVNode(_component_v_card_title, null, {
          default: _withCtx(() => [...(_cache[27] || (_cache[27] = [
            _createTextVNode("TMDB 联通性自检", -1)
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
                      modelValue: tmdbTestId.value,
                      "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((tmdbTestId).value = $event)),
                      label: "TMDB ID",
                      placeholder: "153312"
                    }, null, 8, ["modelValue"])
                  ]),
                  _: 1
                }),
                _createVNode(_component_v_col, {
                  cols: "12",
                  md: "4",
                  class: "d-flex align-center"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_v_btn, {
                      color: "primary",
                      variant: "tonal",
                      loading: tmdbTesting.value,
                      onClick: testTmdb
                    }, {
                      default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                        _createTextVNode("测试查询", -1)
                      ]))]),
                      _: 1
                    }, 8, ["loading"])
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }),
            (tmdbTestResult.value)
              ? (_openBlock(), _createElementBlock("div", _hoisted_3, [
                  (tmdbTestResult.value.ok)
                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                        _createTextVNode(" 查询成功 (经 " + _toDisplayString(tmdbTestResult.value.via === 'direct' ? '自配 Key 直调' : '宿主 TMDB') + ")： 状态 " + _toDisplayString(tmdbTestResult.value.status) + "； ", 1),
                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList((tmdbTestResult.value.seasons || []), (s) => {
                          return (_openBlock(), _createElementBlock("span", {
                            key: s.season_number
                          }, " S" + _toDisplayString(s.season_number) + " " + _toDisplayString(s.episode_count) + " 集； ", 1))
                        }), 128))
                      ], 64))
                    : (_openBlock(), _createElementBlock("span", _hoisted_4, " 查询失败: " + _toDisplayString(tmdbTestResult.value.error || '未知错误'), 1))
                ]))
              : _createCommentVNode("", true)
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    _createElementVNode("div", _hoisted_5, [
      _cache[30] || (_cache[30] = _createElementVNode("span", { class: "text-h6" }, "监听任务", -1)),
      _createVNode(_component_v_spacer),
      _createVNode(_component_v_btn, {
        color: "primary",
        variant: "tonal",
        "prepend-icon": "mdi-plus",
        onClick: addTask
      }, {
        default: _withCtx(() => [...(_cache[29] || (_cache[29] = [
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
      default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
        _createTextVNode(" 每个任务是一条 115 监听路径, 有自己的检查频率 (cron) 和延迟分享时间, 互不影响。 前缀一般填到电视剧分类这一级, 如 /MoviePilot Archived/电视剧/欧美剧。 ", -1)
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
                    md: "6"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_text_field, {
                        modelValue: task.watch_path,
                        "onUpdate:modelValue": $event => ((task.watch_path) = $event),
                        label: "监听路径 (115)",
                        placeholder: "/MoviePilot Archived/电视剧/欧美剧"
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_text_field, {
                        modelValue: task.cron,
                        "onUpdate:modelValue": $event => ((task.cron) = $event),
                        label: "检查频率 (cron)",
                        placeholder: "留空用全局",
                        hint: "一天一次如 0 8 * * *",
                        "persistent-hint": ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_text_field, {
                        modelValue: task.delay_hours,
                        "onUpdate:modelValue": $event => ((task.delay_hours) = $event),
                        modelModifiers: { number: true },
                        type: "number",
                        label: "延迟分享 (小时)",
                        hint: "留空用全局",
                        "persistent-hint": ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024),
                  _createVNode(_component_v_col, {
                    cols: "12",
                    md: "3"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_v_select, {
                        modelValue: task.delete_source,
                        "onUpdate:modelValue": $event => ((task.delete_source) = $event),
                        items: deleteSourceItems,
                        label: "分享后删除源文件",
                        hint: "留空 = 跟随全局",
                        "persistent-hint": ""
                      }, null, 8, ["modelValue", "onUpdate:modelValue"])
                    ]),
                    _: 2
                  }, 1024)
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
    _createElementVNode("div", _hoisted_6, [
      _createVNode(_component_v_btn, {
        variant: "text",
        onClick: _cache[21] || (_cache[21] = $event => (emit('switch')))
      }, {
        default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
          _createTextVNode("查看任务", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        variant: "text",
        onClick: _cache[22] || (_cache[22] = $event => (emit('close')))
      }, {
        default: _withCtx(() => [...(_cache[33] || (_cache[33] = [
          _createTextVNode("关闭", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_v_btn, {
        color: "primary",
        onClick: saveConfig
      }, {
        default: _withCtx(() => [...(_cache[34] || (_cache[34] = [
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
