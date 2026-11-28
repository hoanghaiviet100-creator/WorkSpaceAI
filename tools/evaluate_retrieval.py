"""Compare fixed RRF weights on existing independent retrieval labels."""
import hashlib,json,os,runpy,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def evaluate(out):
    os.environ.update(F1_EMBEDDING_BACKEND='fastembed_cpu',F1_CPU_ENCODER=str(ROOT/'.runtime/cpu-embedding/qwen3-0.6b-int8/encoder.json'),F1_RUNTIME_DIR=str(out),F1_SESSION_B='true',PYTHON_DOTENV_DISABLED='1')
    from backend.providers.embedding_provider import embedding_provider
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.services.document_service import DocumentService
    source=ROOT/'benchmarks/f1_latency/cases.source.json';dataset=json.loads(source.read_text(encoding='utf-8'))
    repo=WorkspaceRepository(embedding_provider.get_embed_fn());service=DocumentService(repo)
    for doc in dataset['pdfs']:
        path=source.parent/doc['path'];content=path.read_bytes()
        if hashlib.sha256(content).hexdigest()!=doc['sha256']:raise ValueError('Independent fixture hash mismatch')
        service.ingest_file(path.name,content)
    vi=[]
    for case in dataset['cases']:
        golds=[{c.chunk_id for c in repo.chunks if c.doc_name==g['file'] and c.page_number==g['page'] and g['quote'] in c.text} for g in case['gold_evidence']]
        if not all(golds):raise ValueError('Independent gold does not match extracted source')
        vi.append((case['scenario'],'vi',case['question'],case['pdfs'],golds))
    upstream=ROOT/'validation/pa2-20261127/upstream/surfsense_local/backend/modules/embedding/search_check.py'
    questions=runpy.run_path(str(upstream))['QUESTIONS']
    en_repo=WorkspaceRepository(embedding_provider.get_embed_fn())
    for i,(_,answer,decoy) in enumerate(questions):
        en_repo.ingest_text_document(f'answer-{i}',f'answer-{i}.txt',[(1,answer)])
        en_repo.ingest_text_document(f'decoy-{i}',f'decoy-{i}.txt',[(1,decoy)])
    en=[(f'EN-{i+1}','en',q,list(en_repo.documents),[{c.chunk_id for c in en_repo.chunks if c.doc_id==f'answer-{i}'}]) for i,(q,_,_) in enumerate(questions)]
    configs={'balanced':(.5,.5),'semantic_heavy':(.35,.65),'keyword_heavy':(.65,.35)}
    rows=[]
    for active,cases in ((repo,vi),(en_repo,en)):
        for case_id,language,query,selection,golds in cases:
            captured={}
            def profile(frame,event,arg):
                if event=='return' and frame.f_code is active.search.__func__.__code__ and frame.f_locals.get('self') is active:
                    for key in ('rank_bm25','rank_dense','scored_chunks'):captured[key]=frame.f_locals[key]
            sys.setprofile(profile)
            try:baseline=active.search(query,top_k=12,selected_doc_ids=selection)
            finally:sys.setprofile(None)
            rankings={};measurements={}
            for name,(bm,dense) in configs.items():
                ranked=sorted(captured['scored_chunks'],key=lambda c:(round(bm/(60+captured['rank_bm25'][c.chunk_id])+dense/(60+captured['rank_dense'][c.chunk_id]),6),c.score),reverse=True)[:12]
                ids=[c.chunk_id for c in ranked];rankings[name]=ids
                recalls={str(k):sum(bool(g&set(ids[:k])) for g in golds)/len(golds) for k in (1,5,12)}
                first=next((i for i,cid in enumerate(ids,1) if any(cid in gold for gold in golds)),None)
                measurements[name]=dict(recall=recalls,reciprocal_rank=1/first if first else 0)
            assert rankings['balanced']==[c.chunk_id for c in baseline]
            rows.append(dict(id=case_id,language=language,query=query,selected=selection,gold_chunk_sets=[sorted(g) for g in golds],bm25_ranks=captured['rank_bm25'],dense_ranks=captured['rank_dense'],rankings=rankings,metrics=measurements))
    summary={}
    for config in configs:
        summary[config]={}
        for language in ('all','vi','en'):
            subset=[r for r in rows if language=='all' or r['language']==language]
            summary[config][language]=dict(n=len(subset),MRR=sum(r['metrics'][config]['reciprocal_rank'] for r in subset)/len(subset),**{f'Recall@{k}':sum(r['metrics'][config]['recall'][str(k)] for r in subset)/len(subset) for k in (1,5,12)})
    result=dict(configurations=configs,k=60,candidate_depth=12,encoder_identity=embedding_provider.index_id,
        source_hashes={str(source.relative_to(ROOT)):hashlib.sha256(source.read_bytes()).hexdigest(),str(upstream.relative_to(ROOT)):hashlib.sha256(upstream.read_bytes()).hexdigest()},
        selected='balanced',reason='Independent evidence is small and lacks cross-lingual, long-document and date-labelled coverage; retain baseline rather than claim a general optimum.',
        coverage=dict(vietnamese=5,english=10,cross_lingual=0,long_document=0,dates=0,identifiers='Room B204 and database port 5432 are present; no general identifier/date benchmark is claimed.'),summary=summary,cases=rows)
    (out/'retrieval-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    embedding_provider.close()
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    destination=Path(args.output);destination.mkdir(parents=True,exist_ok=True);evaluate(destination)
