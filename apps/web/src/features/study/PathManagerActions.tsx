import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assignPath, listTeam, rescoutPath } from '../../api/endpoints'
import { errorMessage } from '../../api/client'
import { useSessionStore } from '../../app/sessionStore'
import { toast } from '../../app/uiStore'
import { Button } from '../../components/primitives/Button'
import { SelectField } from '../../components/primitives/Field'

export function PathManagerActions({ pathId }: { pathId: string }) {
  const { orgId } = useSessionStore()
  const qc = useQueryClient()
  const [learner, setLearner] = useState('')
  const team = useQuery({ queryKey: ['team', orgId], queryFn: () => listTeam(orgId) })
  const assign = useMutation({
    mutationFn: () => assignPath(pathId, learner),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['path', pathId] }); toast('Learner assigned to the path and workspace') },
  })
  const scout = useMutation({
    mutationFn: () => rescoutPath(pathId),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['path', pathId] }); toast('Public resource scouting queued') },
  })
  return <div style={{ display: 'grid', gap: 10 }}>
    <SelectField label="Assign teammate" value={learner} onChange={e => setLearner(e.target.value)}>
      <option value="">Select a teammate</option>
      {(team.data || []).map(u => <option key={u.id} value={u.id}>{u.display_name}</option>)}
    </SelectField>
    <Button disabled={!learner} pending={assign.isPending} onClick={() => assign.mutate()}>Assign to path</Button>
    <Button pending={scout.isPending} onClick={() => scout.mutate()}>Find public resources again</Button>
    {team.isError && <p role="alert">{errorMessage(team.error)}</p>}
    {assign.isError && <p role="alert">{errorMessage(assign.error)}</p>}
    {scout.isError && <p role="alert">{errorMessage(scout.error)}</p>}
  </div>
}
