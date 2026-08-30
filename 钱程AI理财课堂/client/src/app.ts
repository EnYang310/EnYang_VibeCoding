import './app.scss'
import { useEffect, type PropsWithChildren } from 'react'

export default function App({ children }: PropsWithChildren) {
  useEffect(() => {
    if (process.env.TARO_ENV !== 'weapp') return
    const cloud = (globalThis as typeof globalThis & { wx?: { cloud?: { init: (options: { env: string }) => void } } }).wx?.cloud
    cloud?.init({ env: CLOUDBASE_ENV_ID })
  }, [])
  return children
}
