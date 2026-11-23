import { importShared } from './__federation_fn_import-CdTLGLGK.js';
import Page from './__federation_expose_Page-UcYPgHOe.js';

const {createVNode:_createVNode,openBlock:_openBlock,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "pa-4" };


const _sfc_main = {
  __name: 'AppPage',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  nativeSubscribe: { type: Function, default: null },
  navKey: { type: String, default: 'main' },
},
  emits: ['action'],
  setup(__props, { emit: __emit }) {


const emit = __emit;

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createVNode(Page, {
      api: __props.api,
      "plugin-id": __props.pluginId,
      onAction: _cache[0] || (_cache[0] = $event => (emit('action')))
    }, null, 8, ["api", "plugin-id"])
  ]))
}
}

};

export { _sfc_main as default };
