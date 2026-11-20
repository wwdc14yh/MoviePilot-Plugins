import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import federation from '@originjs/vite-plugin-federation'

// 产物直接输出到插件目录的 dist/assets, 与后端 get_render_mode() 返回的
// ("vue", "dist/assets") 对应, 入口为 remoteEntry.js。
export default defineConfig({
  plugins: [
    vue(),
    federation({
      name: 'CloudDrive2Sync',
      filename: 'remoteEntry.js',
      exposes: {
        './Page': './src/components/Page.vue',
        './Config': './src/components/Config.vue',
        './Dashboard': './src/components/Dashboard.vue',
        './AppPage': './src/components/AppPage.vue',
      },
      shared: {
        vue: { singleton: true, requiredVersion: false },
        vuetify: { singleton: true, requiredVersion: false },
        'vuetify/styles': { singleton: true, requiredVersion: false },
      },
    }),
  ],
  build: {
    target: 'esnext',
    minify: false,
    cssCodeSplit: true,
    assetsDir: '',
    outDir: '../plugins.v3/clouddrive2sync/dist/assets',
    emptyOutDir: true,
  },
})
