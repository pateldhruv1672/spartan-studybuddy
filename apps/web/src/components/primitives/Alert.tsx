import type { ReactNode } from 'react'
import { CheckCircleIcon, InfoIcon, WarningIcon } from './Icons'

type Tone = 'info' | 'success' | 'warning' | 'danger'

const ICONS: Record<Tone, ReactNode> = {
  info: <InfoIcon />,
  success: <CheckCircleIcon />,
  warning: <WarningIcon />,
  danger: <WarningIcon />,
}

export function Alert({ tone = 'info', title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  return (
    <div className={`alert alert-${tone}`} role={tone === 'danger' || tone === 'warning' ? 'alert' : 'status'}>
      <span className="alert-icon" aria-hidden="true">
        {ICONS[tone]}
      </span>
      <div className="alert-body">
        {title && <b>{title}</b>}
        {children}
      </div>
    </div>
  )
}
