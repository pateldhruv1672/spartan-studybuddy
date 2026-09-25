import { useEffect, useRef, useState, type ReactNode } from 'react'

export interface DropdownItem {
  label: string
  onSelect: () => void
  danger?: boolean
  icon?: ReactNode
}

export function Dropdown({ trigger, items }: { trigger: ReactNode; items: (DropdownItem | 'separator')[] }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="menu-wrap" ref={ref}>
      <span onClick={() => setOpen((v) => !v)}>{trigger}</span>
      {open && (
        <div className="menu" role="menu">
          {items.map((item, i) =>
            item === 'separator' ? (
              <div key={i} className="menu-separator" role="separator" />
            ) : (
              <button
                key={item.label}
                role="menuitem"
                className="menu-item"
                data-danger={item.danger ? 'true' : undefined}
                onClick={() => {
                  setOpen(false)
                  item.onSelect()
                }}
              >
                {item.icon}
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  )
}
