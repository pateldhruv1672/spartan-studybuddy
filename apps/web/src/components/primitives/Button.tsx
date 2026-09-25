import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'icon'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  full?: boolean
  pending?: boolean
}

export function Button({ variant = 'secondary', full, pending, children, className = '', disabled, ...rest }: Props) {
  const classes = ['btn', `btn-${variant}`, full ? 'btn-full' : '', className].filter(Boolean).join(' ')
  return (
    <button className={classes} disabled={disabled || pending} aria-busy={pending || undefined} {...rest}>
      {children}
    </button>
  )
}

export function IconButton({ label, children, className = '', ...rest }: Props & { label: string }) {
  return (
    <button className={['btn', 'btn-icon', className].join(' ')} aria-label={label} title={label} {...rest}>
      {children}
    </button>
  )
}
