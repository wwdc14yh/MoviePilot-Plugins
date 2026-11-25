import { importShared } from './__federation_fn_import-CdTLGLGK.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "text-body-2" };
const _hoisted_2 = { class: "text-caption text-medium-emphasis mt-1" };
const _hoisted_3 = { key: 0 };
const _hoisted_4 = { key: 0 };
const _hoisted_5 = {
  key: 1,
  class: "text-error"
};
const _hoisted_6 = { key: 2 };

const {computed,onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Dashboard',
  props: {
  config: { type: Object, default: () => ({}) },
  allowRefresh: { type: Boolean, default: true },
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
},
  setup(__props) {

const props = __props;

const counts = ref({ watching: 0, pending_delay: 0, done: 0, failed: 0 });
const taskCount = ref(0);
const login = ref({ logged_in: false, user_name: '', need_relogin: false });

function unwrap(res) {
  return (res && res.data !== undefined) ? res.data : res
}

function sumCounts(tasks) {
  const out = { watching: 0, pending_delay: 0, done: 0, failed: 0 };
  for (const t of tasks || []) {
    const c = t.counts || {};
    out.watching += c.watching || 0;
    out.pending_delay += c.pending_delay || 0;
    out.done += c.done || 0;
    out.failed += c.failed || 0;
  }
  return out
}

async function load() {
  if (!props.api || !props.pluginId) return
  try {
    const s = unwrap(await props.api.get(`plugin/${props.pluginId}/status`));
    if (s) {
      counts.value = sumCounts(s.tasks);
      taskCount.value = (s.tasks || []).length;
      login.value = s.login || login.value;
    }
  } catch (e) { /* 仪表盘加载失败保持空白 */ }
}

onMounted(load);

return (_ctx, _cache) => {
  const _component_v_icon = _resolveComponent("v-icon");
  const _component_v_card_title = _resolveComponent("v-card-title");
  const _component_v_card_text = _resolveComponent("v-card-text");
  const _component_v_card = _resolveComponent("v-card");

  return (_openBlock(), _createBlock(_component_v_card, null, {
    default: _withCtx(() => [
      _createVNode(_component_v_card_title, { class: "d-flex align-center" }, {
        default: _withCtx(() => [
          _createVNode(_component_v_icon, { class: "mr-2" }, {
            default: _withCtx(() => [...(_cache[0] || (_cache[0] = [
              _createTextVNode("mdi-share-variant", -1)
            ]))]),
            _: 1
          }),
          _cache[1] || (_cache[1] = _createTextVNode(" 115 剧集分享 ", -1))
        ]),
        _: 1
      }),
      _createVNode(_component_v_card_text, null, {
        default: _withCtx(() => [
          _createElementVNode("div", _hoisted_1, " 任务 " + _toDisplayString(taskCount.value) + " 个 · 待完结 " + _toDisplayString(counts.value.watching) + " · 待分享 " + _toDisplayString(counts.value.pending_delay) + " · 已分享 " + _toDisplayString(counts.value.done) + " · 失败 " + _toDisplayString(counts.value.failed), 1),
          _createElementVNode("div", _hoisted_2, [
            (login.value.logged_in)
              ? (_openBlock(), _createElementBlock("span", _hoisted_3, [
                  _cache[2] || (_cache[2] = _createTextVNode("115 已登录", -1)),
                  (login.value.user_name)
                    ? (_openBlock(), _createElementBlock("span", _hoisted_4, "：" + _toDisplayString(login.value.user_name), 1))
                    : _createCommentVNode("", true)
                ]))
              : (login.value.need_relogin)
                ? (_openBlock(), _createElementBlock("span", _hoisted_5, "115 登录已过期, 请重新扫码"))
                : (_openBlock(), _createElementBlock("span", _hoisted_6, "115 未登录"))
          ])
        ]),
        _: 1
      })
    ]),
    _: 1
  }))
}
}

};

export { _sfc_main as default };
