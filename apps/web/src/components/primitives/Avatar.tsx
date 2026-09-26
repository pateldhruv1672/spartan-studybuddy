export function Avatar({ label, name, size = 32 }: { label?: string; name?: string; size?: number }) {
  const initials = label || (name ? name.trim().split(/\s+/).slice(0, 2).map((p) => p[0]).join('').toUpperCase() : '?')
  return (
    <span
      className="user-avatar"
      aria-hidden="true"
      style={{ width: size, height: size, flexBasis: size, fontSize: Math.max(10, size * 0.34) }}
    >
      {initials}
    </span>
  )
}
