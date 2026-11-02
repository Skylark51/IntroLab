"""CLI commands for manual research exchange."""
import json
from . import workflow as w
from .store import timestamp


def register(commands):
    p = commands.add_parser('project')
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('show')
    sub.add_parser('set').add_argument('file')
    p = commands.add_parser('campaign')
    sub = p.add_subparsers(dest='operation', required=True)
    q = sub.add_parser('plan'); q.add_argument('--rounds', type=int, default=10)
    sub.add_parser('list')
    q = sub.add_parser('prompt'); q.add_argument('id', type=int); q.add_argument('--out', default='chatgpt_research_prompt.md')
    q = sub.add_parser('review'); q.add_argument('id', type=int); q.add_argument('--note', required=True)
    commands.add_parser('import').add_argument('file')
    commands.add_parser('review').add_argument('--out', default='.introlab/review.json')
    p = commands.add_parser('sentence')
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('list')
    for op in ('add', 'edit'):
        q = sub.add_parser(op)
        if op == 'edit': q.add_argument('id', type=int)
        q.add_argument('text'); q.add_argument('--claims', type=int, nargs='+', required=True)
    q = sub.add_parser('review'); q.add_argument('id', type=int); q.add_argument('--note', required=True)
    p = commands.add_parser('relation')
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('list')
    q = sub.add_parser('add')
    q.add_argument('source', type=int); q.add_argument('target', type=int)
    q.add_argument('--kind', choices=w.RELATIONS, required=True); q.add_argument('--note', required=True)
    p = commands.add_parser('result')
    sub = p.add_subparsers(dest='operation', required=True)
    sub.add_parser('list')
    q = sub.add_parser('add'); q.add_argument('--label', required=True)
    q.add_argument('--text', required=True); q.add_argument('--source', required=True)


def dispatch(args, db, write):
    cmd = args.command
    if cmd == 'project':
        if args.operation == 'set': w.configure(db, w.read_json(args.file))
        print(json.dumps(w.project(db), ensure_ascii=False, indent=2))
    elif cmd == 'campaign':
        if args.operation == 'plan': w.plan(db, args.rounds)
        elif args.operation == 'prompt': write(args.out, w.batch_prompt(db, args.id))
        elif args.operation == 'review': w.review_batch(db, args.id, args.note)
        for row in db.execute('SELECT id,journal,status,reviewed_at FROM batches ORDER BY id'): print(dict(row))
    elif cmd == 'import': print(w.import_research(db, w.read_json(args.file)))
    elif cmd == 'review':
        report = {'warning': 'Imports are candidates. Check source access, evidence, DOI and independent follow-up.',
                  'requirements': ['paper add DOI: Crossref', 'paper check --kind publisher: source read',
                                   'claim review: evidence support', 'paper check --kind followup: later literature',
                                   'sentence review: Korean wording and citation entailment'],
                  'claims': [dict(r) for r in db.execute('SELECT c.*,p.title,p.metadata_verified,p.publisher_checked_at,p.followup_checked_at FROM claims c JOIN papers p ON c.doi=p.doi')],
                  'relations': [dict(r) for r in db.execute('SELECT * FROM relations')],
                  'sentences': [dict(r) for r in db.execute('SELECT * FROM sentences')]}
        write(args.out, json.dumps(report, ensure_ascii=False, indent=2))
    elif cmd == 'sentence':
        if args.operation in ('add', 'edit'): print('Sentence #', w.save_sentence(db, getattr(args, 'id', None), args.text, args.claims))
        elif args.operation == 'review': w.review_sentence(db, args.id, args.note)
        else:
            for r in db.execute('SELECT * FROM sentences'): print(dict(r))
    elif cmd == 'relation':
        if args.operation == 'add':
            with db:
                db.execute('INSERT INTO relations(source,target,kind,note,created_at) VALUES (?,?,?,?,?)',
                           (args.source, args.target, args.kind, w.nonempty(args.note), timestamp()))
        else:
            for r in db.execute('SELECT * FROM relations'): print(dict(r))
    elif cmd == 'result':
        if args.operation == 'add':
            with db:
                db.execute('INSERT INTO project_results(label,text,source,created_at) VALUES (?,?,?,?)',
                           (w.nonempty(args.label), w.nonempty(args.text), w.nonempty(args.source), timestamp()))
        else:
            for r in db.execute('SELECT * FROM project_results'): print(dict(r))
    else: return False
    return True
