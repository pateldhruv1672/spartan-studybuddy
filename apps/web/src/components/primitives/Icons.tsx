import type { CSSProperties, ReactNode } from 'react'

interface IconProps {
  size?: number
  label?: string
  style?: CSSProperties
}

/** Small inline icons. Decorative unless a label is given. */
function iconProps(size: number, label: string | undefined, style: CSSProperties | undefined) {
  return {
    width: size,
    height: size,
    viewBox: '0 0 16 16',
    fill: 'none' as const,
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    role: label ? ('img' as const) : undefined,
    'aria-label': label,
    'aria-hidden': label ? undefined : true,
    style: { flex: '0 0 auto', ...style },
  }
}

function Svg({ size = 14, label, style, children }: IconProps & { children: ReactNode }) {
  return <svg {...iconProps(size, label, style)}>{children}</svg>
}

export function LockIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="7" width="10" height="7" rx="1.6" />
      <path d="M5.2 7V5a2.8 2.8 0 0 1 5.6 0v2" />
    </Svg>
  )
}

export function ChevronDownIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 6.5 8 10.5 12 6.5" />
    </Svg>
  )
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 4 12 12M12 4 4 12" />
    </Svg>
  )
}

export function CheckIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 8.5 6.5 11.5 12.5 5" />
    </Svg>
  )
}

export function CheckCircleIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.2" />
      <path d="M5.2 8.2 7.2 10.2 11 6" />
    </Svg>
  )
}

export function SearchIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M13 13 10.2 10.2" />
    </Svg>
  )
}

export function ExternalLinkIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6.5 3H3v10h10V9.5" />
      <path d="M9.5 3H13v3.5M13 3 7.5 8.5" />
    </Svg>
  )
}

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="8" cy="8" r="6.2" />
      <path d="M8 7.2v4M8 5v.01" />
    </Svg>
  )
}

export function WarningIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 2.5 14.5 13.5h-13Z" />
      <path d="M8 6.5v3.2M8 11.7v.01" />
    </Svg>
  )
}
