"""Pure helpers for the opt-in evidence profile. No grammar or NLI changes."""
import hashlib
import json
import re
from backend.algorithms.f1_claim_support import (
    _prose_entities, _prose_words, _PROSE_FUNCTION_WORDS, _prose_operators, prose_statements,
)

PROFILE = 'evidence_centric_v0'
DISCLOSURE = ('Được hỗ trợ bởi nguồn trích dẫn. Chưa kiểm chứng đầy đủ mâu thuẫn '
              'trong toàn bộ phạm vi tài liệu được phép.')

def normalized(text):
    return ' '.join(text.split())

def manifest_hash(identities):
    return hashlib.sha256(json.dumps(sorted(identities),ensure_ascii=False,
        separators=(',',':')).encode('utf-8')).hexdigest()

def atoms(text):
    """Retain physical/sentence spans; whole-claim NLI also covers conjunctions."""
    rows=[];cursor=0
    for statement in prose_statements(text):
        start=text.find(statement,cursor)
        if start<0:raise ValueError('ATOM_SPAN_NOT_BOUND')
        rows.append(dict(text=statement,start=start,end=start+len(statement)))
        cursor=start+len(statement)
    if not rows:raise ValueError('NO_ASSERTIONS')
    return rows

def claim_queries(text):
    """Retrieval hints only. No synthesized facts, aliases, or query decomposition."""
    without_numbers=re.sub(r'(?<!\w)[+−-]?[0-9]+(?:[.,:/][0-9]+)*(?!\w)',' ',text)
    return tuple(dict.fromkeys(q.strip() for q in (text,normalized(without_numbers)) if q.strip()))

def retrieval_candidate(claim,statement):
    """A lexical retrieval filter, NEVER a distinctness or no-conflict proof.

    Missed aliases/paraphrases remain a disclosed coverage limitation. An actual
    detected contradiction is never discounted through this filter afterwards.
    """
    if normalized(claim)==normalized(statement):return False
    anchors=_prose_entities(claim) & _prose_entities(statement)
    left={w.casefold() for w in _prose_words(claim)}-_PROSE_FUNCTION_WORDS
    right={w.casefold() for w in _prose_words(statement)}-_PROSE_FUNCTION_WORDS
    return bool(anchors) and len(left & right)>=2

def physical_source_spans(text):
    """Exact physical proposal spans, retaining adjacent qualification context.

    This prepares source labels only. It neither proves support nor authorizes
    serving. No model-written excerpt or locator is repaired by this mapping.
    """
    lines=text.splitlines();seen=set();spans=[]
    for index,line in enumerate(lines):
        if not line.strip():continue
        first=last=index
        while first>0 and (lines[first-1].rstrip().endswith((':',',',';')) or any(_prose_operators(lines[first-1]))):
            first-=1
        if last+1<len(lines) and any(_prose_operators(lines[last+1])):last+=1
        key=first,last
        if key not in seen:
            seen.add(key);spans.append((first,last,'\n'.join(lines[first:last+1])))
    return tuple(spans)
