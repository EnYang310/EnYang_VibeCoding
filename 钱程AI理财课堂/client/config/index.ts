import type { UserConfigExport } from '@tarojs/cli'

const apiBase = (process.env.API_BASE || '').trim()
// Mini programs call the deployed CloudBase Run service through WeChat's
// private callContainer channel.  It deliberately does not need a public
// request domain or an ICP-filed custom domain.
const cloudbaseEnvId = (process.env.CLOUDBASE_ENV_ID || '287874-10-1325700028').trim()
const cloudbaseService = (process.env.CLOUDBASE_SERVICE || 'qiancheng-ai-finance-agent').trim()

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
  defineConstants: {
    API_BASE: JSON.stringify(apiBase),
    CLOUDBASE_ENV_ID: JSON.stringify(cloudbaseEnvId),
    CLOUDBASE_SERVICE: JSON.stringify(cloudbaseService)
  },
  mini: {},
  h5: { publicPath: './', staticDirectory: 'static' }
} satisfies UserConfigExport
