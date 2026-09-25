import type { CSSProperties, ReactNode } from 'react'

export function Card({
  children,
  className = '',
  flat = false,
  style,
}: {
  children: ReactNode
  className?: string
  flat?: boolean
  style?: CSSProperties
}) {
  return (
    <div className={`${flat ? 'card-flat' : 'card'} ${className}`} style={style}>
      {children}
    </div>
  )
}

export function CardTitle({ icon, title, subtitle, action }: { icon?: ReactNode; title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="card-title">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        {icon}
        <div>
          <b>{title}</b>
          {subtitle && <small>{subtitle}</small>}
        </div>
      </div>
      {action}
    </div>
  )
}

export function StatCard({ label, value, delta, deltaTone = 'success' }: { label: string; value: string; delta?: string; deltaTone?: 'success' | 'warning' | 'danger' }) {
  return (
    <div className="card stat-card">
      <span>{label}</span>
      <b>{value}</b>
      {delta && <span style={{ color: `var(--${deltaTone})`, fontWeight: 700 }}>{delta}</span>}
    </div>
  )
}
