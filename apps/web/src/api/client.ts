import { useSessionStore } from '../app/sessionStore'

export interface AppError {
  status: number
  code: string
  message: string
  retryable: boolean
  details?: unknown
}

function toAppError(status: number, body: string): AppError {
  let message = body || `Request failed (${status})`
  try {
    const parsed = JSON.parse(body)
    message = parsed?.detail ?? parsed?.message ?? message
  } catch {
    /* body wasn't JSON */
  }
  return {
    status,
    code: String(status),
    message: typeof message === 'string' ? message : JSON.stringify(message),
    retryable: status >= 500 || status === 0,
  }
}

export async function api<T>(path: string, opts: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs = 15000, ...init } = opts
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const isForm = init.body instanceof FormData
  const token = useSessionStore.getState().token
  try {
    const res = await fetch(path, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init.headers || {}),
      },
      signal: controller.signal,
    })
    const text = await res.text()
    if (!res.ok) throw toAppError(res.status, text)
    if (!text) return undefined as T
    const ctype = res.headers.get('content-type') || ''
    return ctype.includes('json') ? (JSON.parse(text) as T) : ((text as unknown) as T)
  } catch (err) {
    if (err && typeof err === 'object' && 'status' in err) throw err
    throw toAppError(0, err instanceof Error ? err.message : 'Network error')
  } finally {
    clearTimeout(timer)
  }
}

export function isAppError(e: unknown): e is AppError {
  return !!e && typeof e === 'object' && 'status' in e && 'message' in e
}

export function errorMessage(e: unknown): string {
  if (isAppError(e)) return e.message
  if (e instanceof Error) return e.message
  return 'Something went wrong'
}
