import { useEffect, useRef, useState } from 'react'
import { useSessionStore } from '../app/sessionStore'

export interface WsMessage {
  kind: string
  [key: string]: unknown
}

const DELAYS = [1000, 2000, 5000, 10000, 30000]

export function useLiveUpdates(userId: string | null, onMessage: (msg: WsMessage) => void) {
  const [connected, setConnected] = useState(false)
  const token = useSessionStore((s) => s.token)
  const attemptRef = useRef(0)
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!userId || !token) return
    let closedByEffect = false
    let socket: WebSocket | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    let pingTimer: ReturnType<typeof setInterval> | null = null

    function connect() {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      socket = new WebSocket(`${proto}://${location.host}/ws/${userId}?token=${encodeURIComponent(token!)}`)
      socket.onopen = () => {
        setConnected(true)
        attemptRef.current = 0
        pingTimer = setInterval(() => {
          if (socket?.readyState === WebSocket.OPEN) socket.send('ping')
        }, 25000)
      }
      socket.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data)
          onMessageRef.current(msg)
        } catch {
          /* non-JSON ping/pong, ignore */
        }
      }
      socket.onclose = () => {
        setConnected(false)
        if (pingTimer) clearInterval(pingTimer)
        if (closedByEffect) return
        const delay = DELAYS[Math.min(attemptRef.current, DELAYS.length - 1)]
        attemptRef.current += 1
        retryTimer = setTimeout(connect, delay)
      }
      socket.onerror = () => socket?.close()
    }

    connect()
    return () => {
      closedByEffect = true
      if (retryTimer) clearTimeout(retryTimer)
      if (pingTimer) clearInterval(pingTimer)
      socket?.close()
    }
  }, [userId, token])

  return { connected }
}
