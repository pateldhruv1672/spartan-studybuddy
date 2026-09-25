import type { ReactNode } from 'react'

export interface TableColumn<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  align?: 'left' | 'right' | 'center'
}

export function Table<T>({
  columns,
  rows,
  rowKey,
  caption,
}: {
  columns: TableColumn<T>[]
  rows: T[]
  rowKey: (row: T) => string
  caption?: string
}) {
  return (
    <table className="table">
      {caption && <caption>{caption}</caption>}
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.key} style={c.align ? { textAlign: c.align } : undefined}>
              {c.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={rowKey(row)}>
            {columns.map((c) => (
              <td key={c.key} style={c.align ? { textAlign: c.align } : undefined}>
                {c.render(row)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
