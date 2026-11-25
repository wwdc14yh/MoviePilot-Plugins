import { importShared } from './__federation_fn_import-CdTLGLGK.js';

const {toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,createTextVNode:_createTextVNode,resolveComponent:_resolveComponent,withCtx:_withCtx,createVNode:_createVNode,createBlock:_createBlock,createElementVNode:_createElementVNode} = await importShared('vue');


const _hoisted_1 = { key: 0 };
const _hoisted_2 = {
  key: 3,
  class: "mt-2 text-center"
};
const _hoisted_3 = ["src"];
const _hoisted_4 = { class: "text-caption text-medium-emphasis mt-1" };
const _hoisted_5 = { key: 0 };
const _hoisted_6 = {
  key: 4,
  class: "text-body-2 mt-2"
};

const {onMounted,onUnmounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Login115',
  props: {
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
},
  emits: ['changed'],
  setup(__props, { expose: __expose, emit: __emit }) {

const props = __props;
const emit = __emit;

const fallbackPlatforms = [
  { title: '网页端 (web)', value: 'web' },
  { title: 'iOS', value: 'ios' },
  { title: 'Android', value: 'android' },
  { title: 'iPad', value: 'ipad' },
  { title: 'TV', value: 'tv' },
  { title: '微信小程序', value: 'wechatmini' },
];

const platforms = ref(fallbackPlatforms);
const platform = ref('web');
const loginInfo = ref({ logged_in: false, user_name: '', need_relogin: false });
const qr = ref(null);
const qrStatus = ref('');
const loading = ref(false);
const message = ref('');

let pollTimer = null;

function unwrap(res) {
  return (res && res.data !== undefined) ? res.data : res
}
function stopPoll() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

async function loadPlatforms() {
  if (!props.api || !props.pluginId) return
  try {
    const res = unwrap(await props.api.get(`plugin/${props.pluginId}/115_login_platforms`));
    if (Array.isArray(res) && res.length) platforms.value = res;
  } catch (e) { /* 接口失败用内置默认平台列表 */ }
}
async function loadStatus() {
  if (!props.api || !props.pluginId) return false
  try {
    const res = unwrap(await props.api.get(`plugin/${props.pluginId}/115_status`)) || {};
    loginInfo.value = {
      logged_in: !!res.logged_in,
      user_name: res.user_name || '',
      need_relogin: !!res.need_relogin,
    };
    return !!res.logged_in
  } catch (e) { /* 状态读取失败保持原值, 调用方按未登录处理 */ return false }
}
async function fetchQr() {
  if (!props.api || !props.pluginId) return
  loading.value = true;
  message.value = '';
  qrStatus.value = '';
  try {
    const res = unwrap(await props.api.get(
      `plugin/${props.pluginId}/qrcode?platform=${encodeURIComponent(platform.value)}`,
    )) || {};
    if (!res.ok && res.token === undefined && !res.qrcode) {
      message.value = '获取二维码失败: ' + (res.error || '');
      return
    }
    qr.value = res;
    qrStatus.value = 'waiting';
    stopPoll();
    pollTimer = setInterval(checkQrStatus, 2000);
  } catch (e) {
    message.value = '获取二维码失败: ' + (e?.message || e);
  } finally {
    loading.value = false;
  }
}
async function checkQrStatus() {
  if (!qr.value?.token) { stopPoll(); return }
  try {
    const res = unwrap(await props.api.get(
      `plugin/${props.pluginId}/qrcode_status?token=${encodeURIComponent(qr.value.token)}`,
    )) || {};
    qrStatus.value = res.status || '';
    if (res.logged_in) {
      // v0.1.0 的 bug: 只看 status==='confirmed' 就报成功, 后端取回
      // Cookie 失败时也显示“扫码登录成功”, 但登录状态仍是过期。
      // 必须以 logged_in 为准才报成功。
      stopPoll();
      qrStatus.value = 'confirmed';
      message.value = '扫码登录成功';
      await loadStatus();
      emit('changed', loginInfo.value);
    } else if (res.status === 'confirmed') {
      // 已扫码确认, 但后端取回 Cookie/登录失败: 不要报成功, 显示真实错误
      stopPoll();
      message.value = '扫码已确认, 但登录失败: ' + (res.error || '取回登录信息失败, 请重新获取二维码');
    } else if (res.status === 'failed') {
      stopPoll();
      message.value = '登录失败: ' + (res.error || '请重新获取二维码');
    } else if (res.status === 'expired') {
      stopPoll();
      message.value = '二维码已过期, 请重新获取';
    }
  } catch (e) { /* 轮询失败等下一次 */ }
}
async function logout() {
  if (!props.api || !props.pluginId) return
  try {
    await props.api.post(`plugin/${props.pluginId}/115_logout`);
    stopPoll();
    qr.value = null;
    qrStatus.value = '';
    message.value = '已退出 115 登录';
    await loadStatus();
    emit('changed', loginInfo.value);
  } catch (e) {
    message.value = '退出登录失败: ' + (e?.message || e);
  }
}

const qrStatusText = {
  waiting: '等待扫码…',
  scanned: '已扫码, 请在手机上确认登录',
  confirmed: '登录成功',
  expired: '二维码已过期',
};

onMounted(async () => {
  await Promise.all([loadPlatforms(), loadStatus()]);
});
onUnmounted(stopPoll);

__expose({ loadStatus, loginInfo });

return (_ctx, _cache) => {
  const _component_v_btn = _resolveComponent("v-btn");
  const _component_v_alert = _resolveComponent("v-alert");
  const _component_v_select = _resolveComponent("v-select");
  const _component_v_col = _resolveComponent("v-col");
  const _component_v_row = _resolveComponent("v-row");

  return (_openBlock(), _createElementBlock("div", null, [
    (loginInfo.value.logged_in)
      ? (_openBlock(), _createBlock(_component_v_alert, {
          key: 0,
          type: "success",
          variant: "tonal",
          class: "mb-3"
        }, {
          append: _withCtx(() => [
            _createVNode(_component_v_btn, {
              size: "small",
              variant: "text",
              color: "error",
              onClick: logout
            }, {
              default: _withCtx(() => [...(_cache[1] || (_cache[1] = [
                _createTextVNode("退出登录", -1)
              ]))]),
              _: 1
            })
          ]),
          default: _withCtx(() => [
            _cache[2] || (_cache[2] = _createTextVNode(" 115 已登录", -1)),
            (loginInfo.value.user_name)
              ? (_openBlock(), _createElementBlock("span", _hoisted_1, "：" + _toDisplayString(loginInfo.value.user_name), 1))
              : _createCommentVNode("", true)
          ]),
          _: 1
        }))
      : (loginInfo.value.need_relogin)
        ? (_openBlock(), _createBlock(_component_v_alert, {
            key: 1,
            type: "error",
            variant: "tonal",
            class: "mb-3"
          }, {
            default: _withCtx(() => [...(_cache[3] || (_cache[3] = [
              _createTextVNode(" 115 登录已过期, 请重新扫码登录 ", -1)
            ]))]),
            _: 1
          }))
        : (_openBlock(), _createBlock(_component_v_alert, {
            key: 2,
            type: "warning",
            variant: "tonal",
            class: "mb-3"
          }, {
            default: _withCtx(() => [...(_cache[4] || (_cache[4] = [
              _createTextVNode(" 115 未登录, 扫码登录后才能监听、复制和分享 ", -1)
            ]))]),
            _: 1
          })),
    _createVNode(_component_v_row, null, {
      default: _withCtx(() => [
        _createVNode(_component_v_col, {
          cols: "12",
          md: "4"
        }, {
          default: _withCtx(() => [
            _createVNode(_component_v_select, {
              modelValue: platform.value,
              "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((platform).value = $event)),
              items: platforms.value,
              label: "登录平台",
              hint: "同一平台扫码会把该平台已登录的其他设备踢下线, 建议固定用一个平台",
              "persistent-hint": ""
            }, null, 8, ["modelValue", "items"])
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
              "prepend-icon": "mdi-qrcode",
              loading: loading.value,
              onClick: fetchQr
            }, {
              default: _withCtx(() => [...(_cache[5] || (_cache[5] = [
                _createTextVNode("获取扫码二维码", -1)
              ]))]),
              _: 1
            }, 8, ["loading"])
          ]),
          _: 1
        })
      ]),
      _: 1
    }),
    (qr.value?.qrcode)
      ? (_openBlock(), _createElementBlock("div", _hoisted_2, [
          _createElementVNode("img", {
            src: qr.value.qrcode,
            alt: "115 扫码登录二维码",
            style: {"max-width":"220px","width":"100%"}
          }, null, 8, _hoisted_3),
          _createElementVNode("div", _hoisted_4, [
            _createTextVNode(_toDisplayString(qrStatusText[qrStatus.value] || '请用 115 App 扫码') + " ", 1),
            (qr.value.expires_in)
              ? (_openBlock(), _createElementBlock("span", _hoisted_5, " · " + _toDisplayString(qr.value.expires_in) + " 秒内有效", 1))
              : _createCommentVNode("", true)
          ]),
          (qrStatus.value === 'expired')
            ? (_openBlock(), _createBlock(_component_v_btn, {
                key: 0,
                variant: "text",
                color: "primary",
                class: "mt-1",
                onClick: fetchQr
              }, {
                default: _withCtx(() => [...(_cache[6] || (_cache[6] = [
                  _createTextVNode("重新获取", -1)
                ]))]),
                _: 1
              }))
            : _createCommentVNode("", true)
        ]))
      : _createCommentVNode("", true),
    (message.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_6, _toDisplayString(message.value), 1))
      : _createCommentVNode("", true)
  ]))
}
}

};

export { _sfc_main as _ };
