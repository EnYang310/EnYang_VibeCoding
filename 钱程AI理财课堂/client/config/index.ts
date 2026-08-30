import type { UserConfigExport } from '@tarojs/cli'

const apiBase = (process.env.API_BASE || '').trim()
if (process.env.TARO_ENV === 'weapp' && !/^https:\/\/[^/]+$/.test(apiBase)) {
  throw new Error('微信小程序构建必须提供无路径的 HTTPS API_BASE')
}

export default {
  projectName: 'qiancheng-client',
  date: '2026-08-30',
  sourceRoot: 'src',
  outputRoot: process.env.TARO_ENV === 'weapp' ? 'dist/weapp' : 'dist/h5',
  designWidth: 750,
  deviceRatio: { 640: 2.34 / 2, 750: 1, 828: 1.81 / 2 },
  framework: 'react',
  compiler: 'webpack5',
  cache: { enable: false },
  plugins: [],
  defineConstants: { API_BASE: JSON.stringify(apiBase) },
  mini: {},
  h5: { publicPath: './', staticDirectory: 'static' }
} satisfies UserConfigExport
