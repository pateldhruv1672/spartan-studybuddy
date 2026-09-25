export function ProgressBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100
  return (
    <div className="progress-track" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress-fill" style={{ width: `${pct}%` }} />
    </div>
  )
}

export function ProgressRing({ value, size = 96 }: { value: number; size?: number }) {
  const pct = Math.max(0, Math.min(1, value))
  const turn = `${pct}turn`
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '999px',
        background: `conic-gradient(var(--primary) 0turn ${turn}, var(--surface-alt) ${turn} 1turn)`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      role="img"
      aria-label={`${Math.round(pct * 100)} percent`}
    >
      <div
        style={{
          width: size * 0.75,
          height: size * 0.75,
          borderRadius: '999px',
          background: 'var(--bg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 700,
          fontSize: size * 0.18,
        }}
      >
        {Math.round(pct * 100)}%
      </div>
    </div>
  )
}
