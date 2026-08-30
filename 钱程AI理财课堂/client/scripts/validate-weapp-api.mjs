const envId = (process.env.CLOUDBASE_ENV_ID || 'maodie-ai-d7gcaowhk300e638f').trim()
const service = (process.env.CLOUDBASE_SERVICE || 'qiancheng-ai-finance-agent').trim()

if (!envId || !service) {
  throw new Error('微信小程序构建必须设置 CLOUDBASE_ENV_ID 和 CLOUDBASE_SERVICE')
}

console.log(`WeChat CloudBase private call: ${envId}/${service}`)
