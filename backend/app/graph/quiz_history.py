"""Persistent attempt review and answer-safe, progressive assessment hints."""
import json
from typing import Any

from ..db import db
from . import catalog
from .quiz import _present


def history(path_id: str, item_id: str, user_id: str) -> list[dict[str, Any]]:
    with db() as conn:
        rows = conn.execute(
            """SELECT a.*,q.project_id,q.path_id,q.module_id,q.item_id FROM quiz_attempts a
               JOIN quizzes q ON q.id=a.quiz_id
               WHERE q.path_id=? AND q.item_id=? AND a.user_id=? ORDER BY a.attempt_no DESC""",
            (path_id, item_id, user_id)).fetchall()
        out = []
        for row in rows:
            snapshot = json.loads(row['snapshot_json'])
            if not snapshot:
                ids = json.loads(row['question_ids_json'])
                snapshot = [dict(r) for r in conn.execute('SELECT * FROM quiz_questions WHERE quiz_id=?', (row['quiz_id'],)).fetchall() if r['id'] in ids]
            details = json.loads(row['detail_json']) if row['status'] == 'graded' else []
            out.append({
                **{k: row[k] for k in ('id','quiz_id','user_id','project_id','path_id','module_id','item_id','attempt_no','status','score','passed','created_at','submitted_at')},
                'questions': _present(snapshot, json.loads(row['order_json'])),
                'answers': json.loads(row['answers_json']),
                'hints': json.loads(row['hints_json']),
                'results': details,
                'weak_concepts': sorted({d['concept'] for d in details if d.get('concept') and d.get('correct') is False}),
            })
    return out


def hint(attempt_id: str, question_id: str, user_id: str) -> dict[str, Any]:
    with db() as conn:
        a = conn.execute('SELECT * FROM quiz_attempts WHERE id=? FOR UPDATE', (attempt_id,)).fetchone()
        if not a or a['user_id'] != user_id:
            raise PermissionError('Attempt unavailable.')
        if question_id not in json.loads(a['question_ids_json']):
            raise KeyError(question_id)
        snapshot = json.loads(a['snapshot_json'])
        q = next((q for q in snapshot if q['id'] == question_id), None)
        if q is None:
            q = conn.execute('SELECT * FROM quiz_questions WHERE id=? AND quiz_id=?', (question_id,a['quiz_id'])).fetchone()
        if not q:
            raise KeyError(question_id)
        hints = json.loads(a['hints_json'])
        level = min(3, len(hints.get(question_id, [])) + 1)
        concept = catalog.concepts().get(q.get('concept'), {}).get('name', 'the system behavior')
        prompts = [
            f'Focus on {concept}. What must remain true before and after the operation?',
            'Trace the inputs, the component responsible for the change, and its downstream effects. Test each option against a failure case, not only the happy path.',
            'Use the cited evidence to check dependency direction and boundaries. Eliminate an option if it requires a guarantee the evidence does not provide; explain why the remaining option handles the failure case.',
        ]
        text = prompts[level-1]
        # Do not interpolate the explanation or correct choice, even on failed-attempt review.
        value = {'level': level, 'hint': text, 'evidence': json.loads(q['evidence_json'])}
        if len(hints.get(question_id, [])) < 3:
            hints.setdefault(question_id, []).append(value)
            conn.execute('UPDATE quiz_attempts SET hints_json=? WHERE id=?', (json.dumps(hints),attempt_id))
        return value
