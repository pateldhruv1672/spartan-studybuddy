import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'

let uid = 0
function useId(prefix: string) {
  uid += 1
  return `${prefix}-${uid}`
}

export function TextField({ label, hint, ...rest }: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId('field')
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} {...rest} />
      {hint && <small>{hint}</small>}
    </div>
  )
}

export function TextAreaField({ label, hint, ...rest }: { label: string; hint?: string } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const id = useId('field')
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} {...rest} />
      {hint && <small>{hint}</small>}
    </div>
  )
}

export function SelectField({
  label,
  children,
  ...rest
}: { label: string; children: ReactNode } & SelectHTMLAttributes<HTMLSelectElement>) {
  const id = useId('field')
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} {...rest}>
        {children}
      </select>
    </div>
  )
}

export function CheckboxField({ label, ...rest }: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId('field')
  return (
    <div className="checkbox-row">
      <input id={id} type="checkbox" {...rest} />
      <label htmlFor={id}>{label}</label>
    </div>
  )
}
