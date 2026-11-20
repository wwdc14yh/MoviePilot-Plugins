// 本地开发入口: 宿主环境中组件由模块联邦直接加载, 不走这里。
import { createApp, h } from 'vue'
import Page from './components/Page.vue'

createApp({ render: () => h(Page) }).mount('#app')
