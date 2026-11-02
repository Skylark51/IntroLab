"""Manual ChatGPT research exchange, audit trail and conservative drafting.

No model login, cookies, automatic browsing or scientific approval is implied.
"""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .crossref import normalize_doi
from .store import timestamp

JOURNALS = ['Journal of the American Chemical Society', 'Inorganic Chemistry',
            'ACS Catalysis', 'Angewandte Chemie International Edition',
            'Chemical Science', 'Dalton Transactions']
KINDS = ('experimental_fact', 'computed_mechanism', 'interpretation', 'unresolved')
RELATIONS = ('supports', 'contradicts', 'supersedes', 'unresolved')


def migrate(db):
    for table, name, definition in (
        ('papers', 'metadata_verified', 'INTEGER NOT NULL DEFAULT 1'),
        ('claims', 'kind', "TEXT NOT NULL DEFAULT 'interpretation'"),
        ('claims', 'source_url', "TEXT NOT NULL DEFAULT ''"),
        ('claims', 'access', "TEXT NOT NULL DEFAULT 'unknown'"),
        ('searches', 'result_dois', "TEXT NOT NULL DEFAULT '[]'"),
        ('searches', 'status', "TEXT NOT NULL DEFAULT 'ok'"),
        ('searches', 'note', "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in [r[1] for r in db.execute(f'PRAGMA table_info({table})')]:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
    db.executescript('''
    CREATE TABLE IF NOT EXISTS project(id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY, journal TEXT NOT NULL,
      query TEXT NOT NULL, purpose TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'planned',
      created_at TEXT NOT NULL, reviewed_at TEXT, note TEXT NOT NULL DEFAULT '',
      exclusions TEXT NOT NULL, start_year INTEGER, end_year INTEGER, offset INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS batch_papers(batch_id INTEGER REFERENCES batches(id),
      doi TEXT REFERENCES papers(doi), relevance TEXT NOT NULL, ligand_match INTEGER NOT NULL,
      urls TEXT NOT NULL, PRIMARY KEY(batch_id,doi));
    CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY, digest TEXT UNIQUE NOT NULL,
      batch_id INTEGER REFERENCES batches(id), payload TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS relations(id INTEGER PRIMARY KEY, source INTEGER REFERENCES claims(id),
      target INTEGER REFERENCES claims(id), kind TEXT NOT NULL, note TEXT NOT NULL,
      reviewed INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY, entity TEXT NOT NULL,
      entity_id TEXT NOT NULL, decision TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sentences(id INTEGER PRIMARY KEY, text TEXT NOT NULL,
      claim_ids TEXT NOT NULL, language TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS sentence_history(id INTEGER PRIMARY KEY,
      sentence_id INTEGER REFERENCES sentences(id), text TEXT NOT NULL, claim_ids TEXT NOT NULL,
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS project_results(id INTEGER PRIMARY KEY, label TEXT NOT NULL,
      text TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'preliminary',
      created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS gap_assessments(gap_id INTEGER PRIMARY KEY REFERENCES gaps(id),
      data TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate', created_at TEXT NOT NULL);
    ''')
    db.commit()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def url(value):
    if not isinstance(value, str) or urlsplit(value).scheme not in ('http', 'https') or not urlsplit(value).netloc:
        raise ValueError('A real source HTTP(S) URL is required')
    return value


def nonempty(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('A nonempty explanation is required')
    return value


def configure(db, data):
    if not isinstance(data, dict):
        raise ValueError('Project must be a JSON object')
    for key in ('field', 'metals', 'ligands', 'reactions', 'substrates', 'style_rules'):
        if key not in data:
            raise ValueError(f'Missing project field: {key}')
    nonempty(data['field'])
    for key in ('metals', 'ligands', 'reactions', 'substrates', 'style_rules'):
        if not isinstance(data[key], list) or not all(isinstance(x, str) for x in data[key]):
            raise ValueError(f'{key} must be a list of strings')
    db.execute('INSERT INTO project VALUES (1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
               (json.dumps(data, ensure_ascii=False),))
    db.commit()


def project(db):
    row = db.execute('SELECT data FROM project WHERE id=1').fetchone()
    if not row:
        raise ValueError('Configure project first: project set FILE')
    return json.loads(row[0])


def seen(db):
    return [r[0] for r in db.execute('SELECT DISTINCT doi FROM batch_papers ORDER BY doi')]


def plan(db, rounds=10):
    if rounds < 10:
        raise ValueError('A campaign requires at least 10 browsing rounds')
    cfg = project(db)
    journals = cfg.get('journals') or JOURNALS
    if not isinstance(journals, list) or not journals or not all(isinstance(j, str) and j.strip() for j in journals):
        raise ValueError('journals must be a nonempty list of journal names')
    query = ' '.join([cfg['field']] + cfg['metals'] + cfg['ligands'] + cfg['reactions'] + cfg['substrates'])
    with db:
        for i in range(rounds):
            db.execute('''INSERT INTO batches(journal,query,purpose,created_at,exclusions,start_year,end_year,offset)
              VALUES (?,?,?,?,?,?,?,?)''', (journals[i % len(journals)], query,
              'discovery', timestamp(), json.dumps(seen(db)), cfg.get('from_year'),
              cfg.get('to_year'), (i // len(journals)) * 10))


def batch_prompt(db, batch_id):
    batch = db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
    if not batch:
        raise ValueError('Unknown batch')
    cfg = project(db)
    excluded = seen(db) if batch['purpose'] == 'discovery' else []
    # Refresh just before each round; pre-generated prompts are never completion evidence.
    db.execute('UPDATE batches SET exclusions=? WHERE id=?', (json.dumps(excluded), batch_id))
    db.commit()
    results = [dict(r) for r in db.execute('SELECT * FROM project_results')]
    return f'''# ChatGPT 실제 웹조사 — 배치 {batch_id}
프로젝트: {json.dumps(cfg, ensure_ascii=False)}
저널: {batch['journal']}; 검색어: {batch['query']}
기간: {batch['start_year']} ~ {batch['end_year']}; offset 참고값: {batch['offset']}
이번 회차에 5–15편의 관련 논문을 실제 웹브라우징으로 읽는다.
다음 DOI는 신규 발굴 대상에서 제외한다: {json.dumps(excluded)}
중복 논문은 신규 조사 횟수/편수에 포함하지 않는다. 후속 해결 여부의 검증에서는
기존 논문도 다시 열 수 있으나, 별도의 검증으로 기록한다.
우리 리간드 사용 연구는 반드시 후보에 포함한다. 다른 리간드/금속/스핀에서
관심 반응을 다룬 연구도 포함한다. 아직 관심에 없던 반응의 전이 가능성도 조사한다.
리간드 일치 여부, 관련성 이유, 각 열람 URL을 기록한다. 설정되지 않은 리간드를 추측하지 않는다.
실험적 사실 / 계산 기전 / 해석 / 미해결 문제를 분리한다. 원문과 SI의 그림·표·페이지를
지정하고 접근 불가는 inaccessible로 표시한다. DOI, 수치, 인용문을 창작하지 않는다.
TS, spin crossover, O–O/C–C cleavage 등 구체적인 미규명 단계를 찾아 후속논문,
독립 연구, 반례를 전 저널에서 현재까지 확인한다. 해결된 문제는 제외한다.
JACS/Angewandte급 기여 가능성을 중요성·신규성·실험 연계·DFT 가능성·구별 가능한
예측으로 평가하고 각 점수에 근거를 쓴다. 게재 수준이나 신규성을 확정하지 않는다.
reactant/intermediate/TS/IRC/spin 검증 계획을 제안하되 기존 Gaussian 프로토콜은 변경하지 않는다.
기존 프로젝트 결과(미출판 예비 결과이며 문헌 근거와 구분): {json.dumps(results, ensure_ascii=False)}
Introduction 최초 초안은 한국어, 자동 인용 및 문장별 claim ID를 포함한다.
we/they/it/우리/그들은 등의 명시적 주어와 과장·상투 표현을 피하고 가능한 수동형으로 쓴다.
실험실 style_rules를 고정 적용하며 번역은 명시적으로 요청받을 때만 제시한다.
저장소 schemas/research-import.schema.json 형식의 JSON을 반환한다.
schema_version=1, batch_id={batch_id}; papers[].claims[].id는 이 파일 안의 고유 ID이다.
모든 결과는 후보이며 어떤 검증/승인 상태도 자동 부여하지 않는다.
프롬프트 생성이나 Crossref 검색을 실제 브라우징 완료로 보고하지 않는다.
'''


def import_research(db, payload):
    if not isinstance(payload, dict) or payload.get('schema_version') != 1:
        raise ValueError('Expected research schema_version 1')
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if db.execute('SELECT 1 FROM imports WHERE digest=?', (digest,)).fetchone():
        return 'Already imported (no changes)'
    batch_id = payload.get('batch_id')
    batch = db.execute('SELECT * FROM batches WHERE id=?', (batch_id,)).fetchone()
    if not batch or batch['status'] != 'planned':
        raise ValueError('Import requires a planned batch')
    papers = payload.get('papers')
    if not isinstance(papers, list) or not 5 <= len(papers) <= 15:
        raise ValueError('A browsing batch must contain 5–15 papers')
    for key in ('relations', 'sentences', 'gaps'):
        if not isinstance(payload.get(key, []), list):
            raise ValueError(f'{key} must be an array')
    local_ids, dois = {}, set()
    excluded = set(seen(db)) if batch['purpose'] == 'discovery' else set()
    with db:
        for p in papers:
            if not isinstance(p, dict):
                raise ValueError('Each paper must be an object')
            doi = normalize_doi(p['doi'])
            if doi in dois or doi in excluded:
                raise ValueError(f'Duplicate discovery DOI: {doi}')
            dois.add(doi)
            urls = p['urls']
            if not isinstance(urls, list) or not urls:
                raise ValueError('Record actual browsing URLs for every paper')
            for u in urls:
                url(u)
            if not isinstance(p['ligand_match'], bool):
                raise ValueError('ligand_match must be boolean')
            nonempty(p['relevance'])
            # Imported bibliographic text is untrusted until a separate Crossref lookup.
            db.execute('''INSERT OR IGNORE INTO papers(doi,title,authors_json,url,metadata_json,
              metadata_checked_at,metadata_verified) VALUES (?,?,?,? ,?,'',0)''',
              (doi, nonempty(p['title']), '[]', 'https://doi.org/' + doi, json.dumps(p, ensure_ascii=False)))
            db.execute('INSERT INTO batch_papers VALUES (?,?,?,?,?)',
                       (batch_id, doi, p['relevance'], int(p['ligand_match']), json.dumps(urls)))
            if not isinstance(p.get('claims', []), list):
                raise ValueError('claims must be an array')
            for c in p.get('claims', []):
                if not isinstance(c, dict):
                    raise ValueError('Each claim must be an object')
                if c['kind'] not in KINDS or c['access'] not in ('accessible', 'inaccessible', 'unknown'):
                    raise ValueError('Invalid claim kind/access')
                key = nonempty(c['id'])
                if key in local_ids:
                    raise ValueError('Duplicate local claim ID')
                cursor = db.execute('''INSERT INTO claims(doi,statement,locator,evidence,created_at,kind,source_url,access)
                  VALUES (?,?,?,?,?,?,?,?)''', (doi, nonempty(c['statement']), nonempty(c['locator']),
                  nonempty(c['evidence']), timestamp(), c['kind'], url(c['source_url']), c['access']))
                local_ids[key] = cursor.lastrowid
        for r in payload.get('relations', []):
            if r['kind'] not in RELATIONS:
                raise ValueError('Invalid relation')
            db.execute('INSERT INTO relations(source,target,kind,note,created_at) VALUES (?,?,?,?,?)',
                       (local_ids[r['source']], local_ids[r['target']], r['kind'], nonempty(r['note']), timestamp()))
        for s in payload.get('sentences', []):
            ids = [local_ids[x] for x in s['claim_ids']]
            save_sentence(db, None, s['text'], ids, 'ko', commit=False)
        for g in payload.get('gaps', []):
            related = [normalize_doi(d) for d in g['related_dois']]
            if not related or not all(db.execute('SELECT 1 FROM papers WHERE doi=?', (d,)).fetchone() for d in related):
                raise ValueError('Gap must link to registered papers')
            db.execute("INSERT INTO gaps(question,related_dois,status,created_at) VALUES (?,?,'candidate',?)",
                       (nonempty(g['question']), json.dumps(related), timestamp()))
        db.execute('INSERT INTO imports(digest,batch_id,payload,created_at) VALUES (?,?,?,?)',
                   (digest, batch_id, raw, timestamp()))
        db.execute("UPDATE batches SET status='imported' WHERE id=?", (batch_id,))
    return f'Imported {len(papers)} candidate papers; no approvals granted'


def audit(db, entity, entity_id, decision, note):
    nonempty(note)
    db.execute('INSERT INTO reviews(entity,entity_id,decision,note,created_at) VALUES (?,?,?,?,?)',
               (entity, str(entity_id), decision, note, timestamp()))


def review_batch(db, batch_id, note):
    row = db.execute('SELECT status FROM batches WHERE id=?', (batch_id,)).fetchone()
    if not row or row[0] != 'imported':
        raise ValueError('Review an imported batch after checking browsing records and relevance')
    with db:
        audit(db, 'batch', batch_id, 'completed', note)
        db.execute("UPDATE batches SET status='completed',reviewed_at=?,note=? WHERE id=?", (timestamp(), note, batch_id))


def save_sentence(db, sid, text, ids, language='ko', commit=True):
    nonempty(text)
    if language != 'ko' or not re.search('[가-힣]', text):
        raise ValueError('First-draft sentences must be Korean; translation is a separate requested step')
    if re.search(r'\b(we|they|it)\b|우리는|그들은', text, re.I):
        raise ValueError('Explicit pronoun subject conflicts with style rules')
    if not ids or not all(db.execute('SELECT 1 FROM claims WHERE id=?', (i,)).fetchone() for i in ids):
        raise ValueError('Every sentence must link to existing claim IDs')
    values = (text, json.dumps(ids), language)
    if sid is None:
        sid = db.execute('INSERT INTO sentences(text,claim_ids,language,created_at) VALUES (?,?,?,?)',
                         values + (timestamp(),)).lastrowid
    else:
        old = db.execute('SELECT * FROM sentences WHERE id=?', (sid,)).fetchone()
        if not old:
            raise ValueError('Unknown sentence')
        db.execute('INSERT INTO sentence_history(sentence_id,text,claim_ids,created_at) VALUES (?,?,?,?)',
                   (sid, old['text'], old['claim_ids'], timestamp()))
        db.execute("UPDATE sentences SET text=?,claim_ids=?,language=?,status='pending' WHERE id=?", values + (sid,))
    if commit:
        db.commit()
    return sid


def eligible(db, ids):
    if not ids:
        return False
    for cid in ids:
        row = db.execute('''SELECT c.*,p.metadata_verified,p.publisher_checked_at,p.followup_checked_at
          FROM claims c JOIN papers p ON p.doi=c.doi WHERE c.id=?''', (cid,)).fetchone()
        if not row or not (row['metadata_verified'] and row['publisher_checked_at'] and
                          row['followup_checked_at'] and row['review_status'] == 'supported'):
            return False
        if row['kind'] in ('interpretation', 'unresolved') or row['access'] == 'inaccessible':
            return False
        # Relations are candidates until explicitly reviewed; contested facts need adjudication.
        if db.execute("SELECT 1 FROM relations WHERE (source=? OR target=?) AND kind IN ('contradicts','supersedes')", (cid, cid)).fetchone():
            return False
    return True


def review_sentence(db, sid, note):
    s = db.execute('SELECT * FROM sentences WHERE id=?', (sid,)).fetchone()
    if not s or not eligible(db, json.loads(s['claim_ids'])):
        raise ValueError('Sentence lacks fully verified factual evidence or has a literature conflict')
    with db:
        audit(db, 'sentence', sid, 'approved', note)
        db.execute("UPDATE sentences SET status='approved' WHERE id=?", (sid,))


def korean_draft(db, title):
    refs, mapping, paragraphs = {}, [], []
    for s in db.execute("SELECT * FROM sentences WHERE status='approved' AND language='ko' ORDER BY id"):
        ids = json.loads(s['claim_ids'])
        if not eligible(db, ids):
            continue
        citations, sources = [], []
        for cid in ids:
            c = db.execute('SELECT * FROM claims WHERE id=?', (cid,)).fetchone()
            if c['doi'] not in refs:
                refs[c['doi']] = len(refs) + 1
            citations.append(refs[c['doi']])
            sources.append({'claim_id': cid, 'doi': c['doi'], 'locator': c['locator'], 'url': c['source_url']})
        paragraphs.append(s['text'] + ' [' + ', '.join(map(str, dict.fromkeys(citations))) + ']')
        mapping.append({'sentence_id': s['id'], 'text': s['text'], 'sources': sources})
    from .render import citation
    lines = [f'# {title}', '', '> 검증된 근거로 작성된 한국어 검토용 초안. 신규성·문체·인용 최종 검토 필요.', '']
    lines += paragraphs or ['검증 및 승인된 한국어 문장이 없습니다.']
    lines += ['', '## 참고문헌 (JACS 준용)', '']
    lines += [f'{n}. {citation(db.execute("SELECT * FROM papers WHERE doi=?", (doi,)).fetchone())}' for doi, n in refs.items()]
    return '\n\n'.join(lines), {'schema_version': 1, 'sentences': mapping}


def assess_gap(db, gid, data):
    if not db.execute('SELECT 1 FROM gaps WHERE id=?', (gid,)).fetchone():
        raise ValueError('Unknown gap')
    for key in ('importance', 'novelty', 'experiment_link', 'dft_feasibility', 'discriminating_prediction'):
        v = data[key]
        if type(v['score']) is not int or not 0 <= v['score'] <= 5:
            raise ValueError('Scores must be integers 0..5')
        nonempty(v['reason'])
    for key in ('reactant', 'intermediate', 'transition_state', 'irc', 'spin_states'):
        nonempty(data['plan'][key])
    for u in data['novelty_sources']:
        url(u)
    if not data['novelty_sources']:
        raise ValueError('Novelty assessment requires actual source URLs')
    nonempty(data['followup_scope'])
    if data['status'] not in ('candidate', 'resolved', 'conflicting', 'shortlisted'):
        raise ValueError('Invalid gap status')
    count = db.execute("SELECT count(*) FROM batches WHERE status='completed'").fetchone()[0]
    if data['status'] == 'shortlisted' and count < 10:
        raise ValueError('Shortlist requires at least 10 reviewed actual browsing batches')
    with db:
        db.execute('INSERT INTO gap_assessments VALUES (?,?,?,?) ON CONFLICT(gap_id) DO UPDATE SET data=excluded.data,status=excluded.status,created_at=excluded.created_at',
                   (gid, json.dumps(data, ensure_ascii=False), data['status'], timestamp()))
        db.execute('UPDATE gaps SET status=? WHERE id=?', (data['status'], gid))
        audit(db, 'gap', gid, data['status'], data['followup_scope'])


def resultlab_export(db):
    return {'schema_version': 1, 'target': 'ResultLab', 'project': project(db),
            'protocol_policy': 'Use researcher-provided protocol without modification',
            'results': [dict(r) for r in db.execute('SELECT * FROM project_results')],
            'candidates': [dict(dict(r), data=json.loads(r['data']), related_dois=json.loads(r['related_dois']))
                           for r in db.execute("SELECT g.*,a.data FROM gaps g JOIN gap_assessments a ON a.gap_id=g.id WHERE a.status='shortlisted'")]}
