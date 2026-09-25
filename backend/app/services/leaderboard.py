"""Canonical all-time scoring derived from persisted completion and quiz records.

Items award their plan XP once. Quizzes award 30 + floor(40 * first-pass score)
once; failed attempts and unverified client events award no XP. Ties use completed
items, then stable user ID. This deliberately does not infer mastery from activity.

Managers are excluded even when they hold an `onboarding_members` row (path creation
auto-enrolls the creator, who may be a manager building a path for their team) — the
leaderboard ranks employee/learner progress, not manager authorship.
"""
import datetime as dt
import json
from ..db import db


def leaderboard(org_id: str, project_id: str | None = None, path_id: str | None = None) -> list[dict]:
    with db() as conn:
        sql = """SELECT m.user_id,CASE WHEN u.leaderboard_visible THEN u.display_name ELSE 'Private learner' END AS display_name,p.id,p.plan_json FROM onboarding_members m
                 JOIN users u ON u.id=m.user_id JOIN onboarding_paths p ON p.id=m.path_id
                 JOIN projects w ON w.id=p.project_id WHERE w.org_id=? AND u.org_id=? AND u.app_role<>'manager'"""
        args = [org_id,org_id]
        if project_id:sql += ' AND p.project_id=?';args.append(project_id)
        if path_id:sql += ' AND p.id=?';args.append(path_id)
        paths = conn.execute(sql,args).fetchall()
        people = {}
        for path in paths:
            uid = path['user_id']
            row = people.setdefault(uid, {'user_id':uid,'display_name':path['display_name'],'xp':0,'completed_items':0,'passed_quizzes':0,'total_items':0,'days':set()})
            plan = json.loads(path['plan_json'])
            items = {i['id']:i for m in plan.get('modules',[]) for i in m.get('items',[])}
            items.update({i['id']:i for i in plan.get('exercises',[])})
            row['total_items'] += len(items)
            passes = conn.execute("""SELECT DISTINCT ON (q.item_id) q.item_id,a.score,a.submitted_at
                FROM quiz_attempts a JOIN quizzes q ON q.id=a.quiz_id
                WHERE q.path_id=? AND a.user_id=? AND a.status='graded' AND a.passed=1
                ORDER BY q.item_id,a.submitted_at,a.id""",(path['id'],uid)).fetchall()
            for p in passes:
                if p['item_id'] not in items:continue
                row['xp'] += 30 + int(40 * p['score'])
                row['completed_items'] += 1
                row['passed_quizzes'] += 1
                row['days'].add(p['submitted_at'].date())
            completions = conn.execute("SELECT item_id,updated_at FROM path_progress WHERE path_id=? AND user_id=? AND status='completed'",(path['id'],uid)).fetchall()
            for p in completions:
                item = items.get(p['item_id'])
                if not item or item.get('type') == 'quiz':continue
                row['xp'] += max(0,int(item.get('xp') or 100))
                row['completed_items'] += 1
                row['days'].add(p['updated_at'].date())
        out = []
        today = dt.datetime.now(dt.timezone.utc).date()
        for row in people.values():
            days = row.pop('days')
            day = today if today in days else today - dt.timedelta(days=1)
            streak = 0
            while day in days:
                streak += 1;day -= dt.timedelta(days=1)
            row['streak'] = streak
            row['progress'] = row['completed_items'] / max(1,row.pop('total_items'))
            out.append(row)
    return sorted(out,key=lambda r:(-r['xp'],-r['completed_items'],r['user_id']))
