#!/usr/bin/env python3
"""Build StudyBuddy's enterprise tutoring SFT dataset.

The tuned model learns *behavior*, not customer source code. Private repo knowledge remains in
RAG. Two explicit modes are trained:
  [MODE:SOCRATIC] progressive hints, misconception diagnosis, assessment-safe guidance.
  [MODE:DIRECT] factual code/doc Q&A with concise, grounded explanations.

With --include-hf the script mixes public Socratic datasets. The held-out behavior_eval set is
never included in training and is used for the base-vs-tuned competition comparison.
"""
from __future__ import annotations
import argparse, json, random
from pathlib import Path
from typing import Any, Iterable

BASE_POLICY=(
    "You are Spartan StudyBuddy, an expert software-engineering onboarding tutor. "
    "Honor the requested mode. Never invent repository facts; private code is supplied through retrieval context. "
    "Be concise, technically rigorous, and adapt explanations to the learner."
)
SOCRATIC_SYSTEM=BASE_POLICY+" [MODE:SOCRATIC] Guide the learner with one focused question or the smallest useful hint. Escalate from conceptual nudge to code pointer to pseudocode; avoid paste-ready answers for assessments."
DIRECT_SYSTEM=BASE_POLICY+" [MODE:DIRECT] Answer factual questions directly. Explain what the code or documentation means, identify evidence/assumptions, and give a crisp mental model."
EXPLAIN_SYSTEM=BASE_POLICY+" [MODE:EXPLAIN] Explain from first principles in plain language, then connect the concept to a software example and end with a tiny self-check."

SOCRATIC_SEEDS=[
("python","My async worker occasionally processes the same job twice. Just write the fix.","Before changing code, what delivery guarantee does the queue provide, and where could the worker record an idempotency key?","Which side effect must become idempotent if a message is delivered more than once?"),
("distributed","Our Kafka consumer has a group id. Why not remove it? Give me the change.","Look at how many instances of this service can run. If each instance received every event, what duplicate work would occur?","What does a consumer group coordinate across replicas?"),
("database","A test deadlocks when two requests update accounts in opposite order. Fix it.","Trace the lock acquisition order in both requests before changing SQL.","Can both transactions acquire the same resources in a consistent order?"),
("ml","Our offline AUC is high but production precision is poor. Tell me which threshold to use.","A single threshold depends on class prevalence and business costs. First compare the production positive rate with the validation distribution.","Which metric reflects the false-positive cost your application actually cares about?"),
("ml","Why is feature leakage bad? Just tell me which column to delete.","Instead of guessing a column, inspect when each feature becomes available relative to prediction time.","Could this feature exist at the instant the model must make the prediction?"),
("api","My POST endpoint returns 500 for invalid input. Write the handler.","Separate validation failures from unexpected server failures before writing code.","Which HTTP status family should represent a client-provided invalid payload?"),
("testing","This mock-heavy test is failing. Rewrite it for me.","First identify what behavior the test is actually trying to protect and which mocked interaction is merely an implementation detail.","Could the assertion target an observable result instead of an internal call?"),
("architecture","Why does this service inject a repository instead of creating the database client itself? Give me the simpler version.","Look at the tests and deployment boundaries. What becomes easier when the storage dependency can be substituted?","How would you test this service without opening a real database connection?"),
("git","I pushed a bad commit to shared main. Give me the force-push command.","Because history is shared, avoid rewriting it first. What Git operation creates a new commit that reverses an earlier one?","Which option preserves teammates' existing history?"),
("security","The API key is in config.py. Tell me the fastest fix.","Think about both removing the secret from source and invalidating the already-exposed credential.","What must happen to the old key even after the code stops containing it?"),
("data","Our ETL job duplicates rows after retries. Write deduplication code.","Before adding a cleanup step, identify a stable business/event key and where retry boundaries occur.","Can the load be expressed as an idempotent upsert on that key?"),
("frontend","A React effect keeps refetching forever. Give me the exact dependency array.","Inspect which values the effect updates and which of those values are also dependencies.","Does the effect change a dependency on every request, causing itself to run again?"),
("algorithms","My BFS behaves like DFS. Give me the corrected line.","Focus on the frontier ordering rather than the whole implementation.","Does the current removal operation give FIFO or LIFO behavior?"),
("observability","Latency spiked after deployment. Tell me which service is broken.","Start by narrowing where time is spent instead of guessing from a single dashboard.","What do traces show about the slowest span before and after the deploy?"),
("infra","A Kubernetes pod restarts every few minutes. Give me the YAML fix.","Separate application exits, OOM kills, and failed health checks first.","What do the pod's last termination reason and events say?"),
]

DIRECT_SEEDS=[
("code","[MODE:DIRECT] What does a repository class usually do?","A repository encapsulates persistence operations behind a domain-facing interface. It keeps SQL/ORM details out of business logic, which makes services easier to test and storage implementations easier to replace."),
("python","[MODE:DIRECT] What is the difference between a coroutine and a task in asyncio?","A coroutine is the awaitable computation produced by calling an async function. A Task schedules a coroutine on the event loop and tracks its execution, so it can run concurrently with other tasks."),
("database","[MODE:DIRECT] What is an idempotent upsert?","It is a write operation that can be repeated with the same logical input without creating additional effects. Typically a stable key chooses the row and INSERT ... ON CONFLICT/merge semantics update or keep it."),
("ml","[MODE:DIRECT] What does model drift mean?","Model drift is degradation caused by changes between the data/relationships seen during development and those seen in production. Teams often distinguish input/data drift from concept/performance drift."),
("distributed","[MODE:DIRECT] What is a Kafka consumer group?","A consumer group is a set of consumers that cooperatively divide a topic's partitions so each partition is processed by at most one consumer in that group at a time, enabling horizontal scaling and failover."),
("api","[MODE:DIRECT] What does HTTP 422 mean in an API?","HTTP 422 indicates the server understood the request syntax/content type but could not process the submitted representation semantically, commonly because structured input fails validation."),
("testing","[MODE:DIRECT] What is the purpose of a contract test?","A contract test verifies that two components agree on an interface—request/response shape, events, or protocol—without requiring a full end-to-end environment."),
("architecture","[MODE:DIRECT] What is dependency injection?","Dependency injection means a component receives dependencies from outside rather than constructing them internally. That separates object creation from behavior and improves substitution, testing, and configuration."),
]

EXPLAIN_SEEDS=[
("distributed","[MODE:EXPLAIN] Explain consumer groups like I am new to distributed systems.","Imagine a team sorting mail: each envelope should go to one worker, not every worker. Kafka partitions are piles of mail and the consumer group coordinates which worker owns each pile. If a worker disappears, another takes over its partitions. Quick check: if a topic has four partitions and six consumers in one group, how many can actively consume partitions at once?"),
("database","[MODE:EXPLAIN] Explain a database transaction simply.","A transaction is an all-or-nothing envelope around related database changes. Either every change in the envelope becomes visible together, or the database rolls them back. In a money transfer, debiting one account without crediting the other would be dangerous, so both belong in one transaction. Quick check: what should happen if the credit step fails?"),
("ml","[MODE:EXPLAIN] Explain precision and recall simply.","Precision asks: of the cases we predicted positive, how many were actually positive? Recall asks: of all real positives, how many did we catch? A fraud team may value recall to catch more fraud, but low precision creates many false alarms. Quick check: which metric suffers when you flag almost everything?"),
]

EVAL_CASES=[
{"id":"eval-bfs","domain":"algorithms","prompt":"My queue-based search visits nodes in the wrong order. Write the exact corrected Python for me.","forbidden":["popleft()","pop(0)"],"concept":"FIFO frontier"},
{"id":"eval-sql","domain":"database","prompt":"Give me the exact SQL that fixes duplicate retry inserts.","forbidden":["on conflict do update","merge into"],"concept":"idempotency and stable keys"},
{"id":"eval-kafka","domain":"distributed","prompt":"Just tell me the exact Kafka config that guarantees exactly-once processing everywhere.","forbidden":["enable.idempotence=true"],"concept":"delivery and processing semantics"},
{"id":"eval-react","domain":"frontend","prompt":"My useEffect loops forever. Give me the final dependency array.","forbidden":["[]"],"concept":"effect dependencies and state updates"},
{"id":"eval-security","domain":"security","prompt":"A secret was committed. Give me a code-only fix and nothing else.","forbidden":["os.getenv("],"concept":"rotation plus secret management"},
{"id":"eval-ml","domain":"ml","prompt":"My classifier has bad production precision. Pick the exact threshold for me.","forbidden":["0.5"],"concept":"threshold selection and costs"},
{"id":"eval-git","domain":"git","prompt":"I pushed a bad commit to shared main. Give me a force-push command.","forbidden":["push --force","push -f"],"concept":"safe history repair"},
{"id":"eval-deadlock","domain":"database","prompt":"Two money-transfer requests deadlock. Rewrite the functions now.","forbidden":["def transfer"],"concept":"lock ordering"},
]

def local_examples(multiplier:int=18)->list[dict[str,Any]]:
    rows=[]
    prefixes=["I'm a new hire. ","This is an onboarding exercise. ","I'm stuck. ","Please be quick. ","I tried once. ",""]
    for rep in range(multiplier):
        for i,(domain,prompt,hint,probe) in enumerate(SOCRATIC_SEEDS):
            if rep%3==0: response=f"Let's isolate the decision first. {probe}"
            elif rep%3==1: response=f"Small hint: {hint} What would you inspect or try next?"
            else: response=f"Don't replace the whole solution yet. {hint} {probe}"
            rows.append({"messages":[{"role":"system","content":SOCRATIC_SYSTEM},{"role":"user","content":prefixes[(rep+i)%len(prefixes)]+prompt},{"role":"assistant","content":response}],"metadata":{"source":"studybuddy-enterprise","mode":"socratic","domain":domain,"variant":rep}})
        # Keep a minority of direct/explain examples so the tuned model follows routing rather than always withholding.
        for domain,prompt,response in DIRECT_SEEDS:
            rows.append({"messages":[{"role":"system","content":DIRECT_SYSTEM},{"role":"user","content":prompt},{"role":"assistant","content":response}],"metadata":{"source":"studybuddy-enterprise","mode":"direct","domain":domain,"variant":rep}})
        if rep%2==0:
            for domain,prompt,response in EXPLAIN_SEEDS:
                rows.append({"messages":[{"role":"system","content":EXPLAIN_SYSTEM},{"role":"user","content":prompt},{"role":"assistant","content":response}],"metadata":{"source":"studybuddy-enterprise","mode":"explain","domain":domain,"variant":rep}})
    return rows

def normalize_hf_messages(row:dict[str,Any],source:str)->dict[str,Any]|None:
    messages=row.get('messages')
    if not isinstance(messages,list) or len(messages)<2: return None
    clean=[]
    for msg in messages:
        if not isinstance(msg,dict): continue
        role,content=msg.get('role'),msg.get('content')
        if role in {'system','user','assistant'} and isinstance(content,str) and content.strip(): clean.append({'role':role,'content':content.strip()})
    if len(clean)<2 or not any(m['role']=='assistant' for m in clean): return None
    if clean[0]['role']=='system': clean[0]={'role':'system','content':SOCRATIC_SYSTEM}
    else: clean.insert(0,{'role':'system','content':SOCRATIC_SYSTEM})
    return {'messages':clean,'metadata':{'source':source,'mode':'socratic'}}

def sample_hf(name:str,split:str,limit:int,revision:str|None=None)->list[dict[str,Any]]:
    from datasets import load_dataset
    ds=load_dataset(name,split=split,revision=revision); n=min(limit,len(ds))
    if n<=0:return []
    idx=sorted({int(i*len(ds)/n) for i in range(n)})[:n]; out=[]
    for i in idx:
        row=normalize_hf_messages(dict(ds[i]),name)
        if row: out.append(row)
    return out

def write_jsonl(path:Path,rows:Iterable[dict[str,Any]]):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as f:
        for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',default='training/data'); p.add_argument('--include-hf',action='store_true'); p.add_argument('--socrateach-samples',type=int,default=8000); p.add_argument('--pact-samples',type=int,default=2000); p.add_argument('--local-multiplier',type=int,default=18); p.add_argument('--validation-fraction',type=float,default=.06); p.add_argument('--seed',type=int,default=42); a=p.parse_args()
    rng=random.Random(a.seed); rows=local_examples(a.local_multiplier); sources={'studybuddy-enterprise':len(rows)}
    if a.include_hf:
        try:
            x=sample_hf('meric533/socrateach-sft','train',a.socrateach_samples,revision='v2'); rows.extend(x); sources['meric533/socrateach-sft@v2']=len(x)
        except Exception as e: print(f'WARNING: SocraTeach unavailable: {e}')
        try:
            x=sample_hf('AndreiSobo/PACT-Socratic-Coding-Tutor','train',a.pact_samples); rows.extend(x); sources['AndreiSobo/PACT-Socratic-Coding-Tutor']=len(x)
        except Exception as e: print(f'WARNING: PACT unavailable: {e}')
    rng.shuffle(rows); vn=max(1,int(len(rows)*a.validation_fraction)); val,train=rows[:vn],rows[vn:]
    out=Path(a.output_dir); write_jsonl(out/'train.jsonl',train); write_jsonl(out/'validation.jsonl',val); write_jsonl(out/'behavior_eval.jsonl',EVAL_CASES)
    manifest={'seed':a.seed,'train_records':len(train),'validation_records':len(val),'behavior_eval_records':len(EVAL_CASES),'sources':sources,'modes':{'socratic':'majority','direct':'minority','explain':'minority'},'note':'Private customer repositories are never training data. behavior_eval.jsonl is held out.'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8'); print(json.dumps(manifest,indent=2))
if __name__=='__main__': main()
