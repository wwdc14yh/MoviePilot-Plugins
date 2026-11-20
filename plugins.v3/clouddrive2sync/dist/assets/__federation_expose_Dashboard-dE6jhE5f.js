import { importShared } from './__federation_fn_import-CdTLGLGK.js';

const {createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,toDisplayString:_toDisplayString,createElementVNode:_createElementVNode,openBlock:_openBlock,createBlock:_createBlock} = await importShared('vue');


const _hoisted_1 = { class: "text-body-2" };

const {onMounted,ref} = await importShared('vue');



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

const states = ref({});
const taskCount = ref(0);

function unwrap(res) {
  return (res && res.data !== undefined) ? res.data : res
}

async function load() {
  if (!props.api || !props.pluginId) return
  try {
    const s = unwrap(await props.api.get(`plugin/${props.pluginId}/status`));
    if (s) {
      states.value = s.states || {};
      taskCount.value = (s.tasks || []).length;
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
              _createTextVNode("mdi-cloud-sync", -1)
            ]))]),
            _: 1
          }),
          _cache[1] || (_cache[1] = _createTextVNode(" CloudDrive2 同步 ", -1))
        ]),
        _: 1
      }),
      _createVNode(_component_v_card_text, null, {
        default: _withCtx(() => [
          _createElementVNode("div", _hoisted_1, " 任务 " + _toDisplayString(taskCount.value) + " 个 · 已同步 " + _toDisplayString(states.value.done || 0) + " · 同步中 " + _toDisplayString(states.value.copying || 0) + " · 失败 " + _toDisplayString(states.value.failed || 0), 1)
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
