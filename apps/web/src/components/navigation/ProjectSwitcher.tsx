import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { listProjects } from '../../api/endpoints'
import { useSessionStore } from '../../app/sessionStore'

export function ProjectSwitcher() {
  const { orgId, projectId, setProjectId } = useSessionStore()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { data: projects } = useQuery({ queryKey: ['projects', orgId], queryFn: () => listProjects(orgId) })

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <span className="status-dot" aria-hidden="true" />
      <select
        aria-label="Active workspace"
        value={projectId ?? ''}
        onChange={async (e) => {
          const next = e.target.value
          await qc.cancelQueries()
          setProjectId(next)
        }}
        style={{ border: 0, background: 'transparent', fontWeight: 700, fontSize: 14, padding: '6px 4px' }}
      >
        {!projects?.length && <option value="">No workspaces yet</option>}
        {projects?.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button className="btn btn-icon" aria-label="Manage workspaces" onClick={() => navigate('/workspace')}>
        +
      </button>
    </div>
  )
}
