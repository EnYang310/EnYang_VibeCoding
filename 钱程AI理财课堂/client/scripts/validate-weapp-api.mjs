const apiBase = (process.env.API_BASE || '').trim()

if (!apiBase) {
  throw new Error('微信小程序构建必须设置 API_BASE，例如：https://api.example.com')
}

let parsed
try {
  parsed = new URL(apiBase)
} catch {
  throw new Error('API_BASE 必须是完整的 HTTPS 地址')
}

if (parsed.protocol !== 'https:' || parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) {
  throw new Error('API_BASE 只能是无路径、无账号信息的 HTTPS 后端域名，例如：https://api.example.com')
}

if (parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1') {
  throw new Error('微信小程序不能把本机地址作为 API_BASE')
}

console.log(`WeChat API origin: ${parsed.origin}`)
