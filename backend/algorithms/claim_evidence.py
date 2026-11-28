"""Conservative lexical claim evidence selection, without model calls or I/O."""
import itertools
import re
import unicodedata


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.casefold().replace('đ','d')) if not unicodedata.combining(c))


_FORMS = {
    'location': ('takes place','dien ra','located','held','to chuc'),
    'room': ('room','rooms','phong','房间','教室'),
    'start': ('starts','start','begins','begin','opens','open','bat dau','开始'),
    'register': ('register','registration','dang ky','注册'),
    'limit': ('at most','maximum','toi da'),
    'bring': ('bring','brings','mang','携带'),
    'device': ('laptops','laptop','computers','computer','may tinh','电脑'),
    'practice': ('practice','practise','practical exercise','thuc hanh','练习'),
    'analyse': ('analysing','analyzing','analysis','analyse','analyze','phan tich','分析'),
    'spreadsheet': ('spreadsheet data','spreadsheets','spreadsheet','bang du lieu','电子表格'),
    'kit': ('workshop kits','workshop kit','kits','kit','bo tai lieu tap huan','bo tai lieu','培训资料'),
    'prepare': ('prepares','prepared','prepare','chuan bi','准备'),
    'receive': ('receives','received','receive','nhan','获得'),
    'logistics': ('logistics team','logistics','ban hau can'),
    'team': ('teams','team','groups','group','nhom'),
    'each': ('each','every','moi'),
    'before': ('before','truoc ngay','truoc'),
    'entry': ('entry','vao cua'),
    'badge': ('badge',),
    'negative': ('not','never','no','khong','chua'),
    'conditional': ('if','unless','when','provided','neu','khi'),
    'possible': ('may','might','could','co the'),
}
_STOP=set('by luc each the a an is are was were be been being this that those these it its they their them he she we you should must required requires need needs to for of in on at from with into go attend attends participants participant learners learner attendees attendee people person persons workshop workshops session sessions training event buoi tap huan nguoi tham du hoc vien can phai den tai vao de la duoc co mot nhung cac va cua nay viec cung mang theo ngay ngay thang nam which what where how when why dien toi organized organised take takes place cung cap so number numbers quantity amount has have there will ngay duoc'.split())
_MONTHS={'january':'1','february':'2','march':'3','april':'4','may':'5','june':'6','july':'7','august':'8','september':'9','october':'10','november':'11','december':'12'}
_GENERIC_CAPS=set('The A An Participants Participant Each Every Entry Logistics Ban Buoi Nguoi Moi There It This English Vietnamese'.split())
_PREDICATES=set(_FORMS)-{'each','team','before','negative','conditional','possible'}
_QUALIFIERS={'negative','conditional','possible','limit','before'}


def anchors(text):
    original=text
    text=normalize(text)
    identifiers=set(re.findall(r'(?<![a-z0-9_])(?:[a-z]+[-_]?\d+[a-z\d_-]*|\d+[a-z]+)(?![a-z0-9_])',text))
    clocks=set(re.findall(r'\b\d{1,2}:\d{2}\b',text))
    numbers=set(re.findall(r'\d+(?:\.\d+)?',re.sub(r'\b\d{1,2}:\d{2}\b','',text)))
    numbers.update(value for month,value in _MONTHS.items() if re.search(r'\b'+('May' if month=='may' else month)+r'\b',original,0 if month=='may' else re.I))
    return identifiers|clocks|numbers


def canonical(text):
    value=re.sub(r'\bthẻ\b','badge',text,flags=re.I)
    for month,number in _MONTHS.items():value=re.sub(r'\b'+('May' if month=='may' else month)+r'\b',number,value,flags=0 if month=='may' else re.I)
    for form,replacement in (('没有',' negative '),('不得',' negative '),('不',' negative '),('如果',' conditional '),('可能',' possible '),('将在',' '),('将',' '),('应该',' '),('应当',' '),('参加',' '),('举办地点',' location '),('地点',' location '),('为',' '),('研讨会',' '),('工作坊',' '),('参与者',' '),('参加者',' '),('学员',' '),
            ('举行',' location '),('举办',' location '),('位于',' location '),('房间',' room '),('教室',' room '),
            ('开始',' start '),('携带',' bring '),('电脑',' device '),('培训资料',' kit '),('准备',' prepare '),
            ('在',' '),('的',' '),('是',' '),('于',' '),('需要',' '),('必须',' '),('应',' '),('前往',' '),('请',' '),('该',' '),('本',' '),('年',' '),('月',' '),('日',' ')):
        value=value.replace(form,replacement)
    value=normalize(value)
    value=value.replace('duoc chi dinh',' ')
    value=re.sub(r'\b(register|registration) by\b',r'\1 before',value)
    for form,concept in sorted(((form,key) for key,forms in _FORMS.items() for form in forms),key=lambda p:len(p[0]),reverse=True):
        value=re.sub(r'(?<!\w)'+re.escape(form)+r'(?!\w)',concept,value)
    return value


def units(text):
    return set(re.findall(r'[a-z]+(?:[-_]?[a-z\d]+)*|\d+(?:\.\d+)?|[\u3400-\u9fff]+',canonical(text)))-_STOP


def statements(text):
    return [s.strip() for s in re.split(r'\n+|(?<=[.!?。！？])\s+',text) if s.strip() and not re.search(r'(?:page|trang)\s+\d+\s*(?:of|/)\s*\d+',s,re.I)]


def clauses(text):
    result=[]
    for sentence in statements(text):
        parts=re.split(r'\s+(?:and|while|whereas|và|còn)\s+|;\s*|,\s+(?=(?:each|every|mỗi)\b)',sentence,flags=re.I)
        if len(parts)>1 and all(units(p)&_PREDICATES for p in parts):result.extend(parts)
        else:result.append(sentence)
    return result


def _entities(text):
    words=re.findall(r'[^\W\d_\u3400-\u9fff]+',text)
    forms={w for values in _FORMS.values() for value in values for w in value.split()}
    return {normalize(w) for w in words if w[0].isupper() and w not in _GENERIC_CAPS and normalize(w) not in _STOP|set(_MONTHS)|forms}


def _supports(claim,chunk):
    if chunk is None:return False
    needed=units(claim);hard=anchors(claim)
    # Source metadata may scope a named subject; it never supplies a value or predicate.
    entities=_entities(claim)
    scope={normalize(w) for w in re.findall(r'[^\W\d_\u3400-\u9fff]+',chunk.doc_name+' '+chunk.text)}
    if not entities<=scope:return False
    required=needed-entities
    if not required:return False
    for sentence in statements(chunk.text):
        offered=units(sentence)
        if (offered&_QUALIFIERS)!=(required&_QUALIFIERS):continue
        if required<=offered and hard<=anchors(sentence):return True
    return False


def _different_values(text,labels,chunks):
    # Only an explicit binary property comparison admits this bounded proof.
    match=re.fullmatch(r'(?:the )?two (?:opening )?(schedules|times|dates|rooms|counts|quantities) (?:differ|are different)[.!]?',normalize(text).strip())
    if not match:return []
    kind=match.group(1);values={}
    for label in labels:
        chunk=chunks[label-1]
        if chunk is None:continue
        found=set()
        for statement in statements(chunk.text):
            tokens=units(statement)
            if tokens&_QUALIFIERS:continue
            if kind in ('schedules','times','dates') and 'start' in tokens:
                clocks=set(re.findall(r'\b\d{1,2}:\d{2}\b',statement))
                if len(clocks)==1:found.add(('start',tuple(sorted(anchors(statement)))))
            elif kind=='rooms' and 'room' in tokens:
                ids={a for a in anchors(statement) if re.search(r'[a-z]',a)}
                if len(ids)==1:found.add(('room',tuple(ids)))
        if len(found)==1:values[label]=next(iter(found))
    for a,b in itertools.combinations(labels,2):
        if a in values and b in values and chunks[a-1].doc_id!=chunks[b-1].doc_id and values[a][0]==values[b][0] and values[a][1]!=values[b][1]:return [a,b]
    return []


def select_sources(text,source_ids,chunks,translation=None):
    """Return a minimum evidence cover or no cover; never add a candidate ID.

    Whole clauses require explicit lexical/value support. This is bounded anchor
    agreement, not universal semantic entailment. Ambiguous claims fail locally.
    """
    if not isinstance(text,str) or not text.strip() or not isinstance(source_ids,list):return []
    labels=list(dict.fromkeys(n for n in source_ids if type(n) is int and 1<=n<=len(chunks)))
    if translation is None:
        compared=_different_values(text,labels,chunks)
        if compared:return compared
    claims=clauses(text)
    if translation is not None:
        if not isinstance(translation,str) or anchors(text)!=anchors(translation):return []
        # Both variants must be supported, rather than letting a translation add facts.
        claims+=clauses(translation)
    if not claims:return []
    coverage={n:{i for i,c in enumerate(claims) if _supports(c,chunks[n-1])} for n in labels}
    labels=[n for n in labels if coverage[n]]
    target=set(range(len(claims)))
    for size in range(1,len(labels)+1):
        for subset in itertools.combinations(labels,size):
            if set().union(*(coverage[n] for n in subset))==target:return list(subset)
    return []



def _names(text):
    return (_entities(text)-{'summarize','summarise','summary','tom','tat','compare','answer','respond','reply','please','according','theo','tai','lieu','nguon','source','document'})-{re.match(r'[a-z]+',a).group() for a in anchors(text) if re.match(r'[a-z]+',a)}


def _segments(text):
    """Coordinate boundaries and property heads, retaining original source text."""
    result=[]
    for sentence in statements(text):
        parts=re.split(r'\s+(?:and|while|whereas|but|và|còn|nhưng)\s+|;\s*|,\s*(?:with\s+)?(?=(?:each|every|mỗi)\b)',sentence,flags=re.I)
        if len(parts)>1 and all(units(s)&_PREDICATES for s in parts):result.extend((s,sentence) for s in parts)
        else:result.append((sentence,sentence))
    return result


def _frames(text,default_names=frozenset()):
    """Bound relation/value/subject components, never an unordered value bag."""
    result=[];scope=set(default_names)
    for segment,original in _segments(text):
        if not units(segment)&_PREDICATES:continue
        previous_scope=set(scope);previous_count=len(result)
        names=_names(segment)
        if names:scope=names
        value=canonical(segment);q=units(segment)&{'negative','conditional','possible'}
        condition=''
        conditional=re.match(r'\s*(?:if|when|unless|nếu|khi)\b(.+?)[,:]',segment,re.I)
        if conditional:condition=normalize(conditional.group(0))
        date=re.search(r'(?<!\d)(\d{1,2})[ /.-]+(\d{1,2})[ /.-]+(\d{4})(?!\d)',value)
        date=tuple(date.groups()) if date else ()
        def add(role,payload,at):
            result.append(dict(role=role,value=tuple(payload),names=frozenset(scope),qualifiers=frozenset(q),condition=condition,temporal=date,quote=original,segment=segment,at=at))
        located=('location' in units(segment) or bool(re.search(r'\b(?:go|attend|den|tai)|(?:in|at)\s+room\b',value)) or bool(re.search(r'^\s*(?:the\s+)?room\s*(?:is|la|:)',value)))
        identifier=r'([a-z]+[-_]?\d+[a-z\d_-]*)'
        copular=re.search(r'\broom\b[^.!?;]*?\b(?:is|are|la)\s+(?:(?:the|room)\s+)*'+identifier+r'\b',value)
        assigned=set()
        if located:
            for match in re.finditer(r'\broom\s+(?:(?:is|la)\s+|:\s*)?'+identifier+r'\b',value):
                add('room',(match[1],),match.start());assigned.add(match[1])
        if copular and copular[1] not in assigned:add('room',(copular[1],),copular.start())
        start=re.search(r'\bstart\b',value);clock=re.search(r'\b\d{1,2}:\d{2}\b',value)
        if start and clock:add('start',(clock.group(),*date),start.start())
        registration=re.search(r'\bregister\b',value)
        if registration and date and 'before' in units(segment):add('registration',date,registration.start())
        limit=re.search(r'\blimit\s+(\d+)\s*([^\s.,;]*)',value)
        if limit:
            unit='person' if limit[2] in ('participants','participant','people','person','nguoi') else limit[2]
            # Permission phrasing does not change an explicitly stated upper bound.
            add('limit',(limit[1],unit),limit.start());result[-1]['qualifiers']=frozenset(q-{'possible'})
        quantities=list(re.finditer(r'\b(\d+)\s+kit\b',value))
        verbs=list(re.finditer(r'\b(prepare|receive)\b',value))
        for quantity in quantities:
            if not verbs:continue
            distance=lambda verb:min(abs(quantity.start()-verb.end()),abs(verb.start()-quantity.end()))
            ranked=sorted(verbs,key=distance)
            if len(ranked)>1 and distance(ranked[0])==distance(ranked[1]):continue
            add(ranked[0][1],(quantity[1],'kit'),quantity.start())
        if 'bring' in units(segment) and 'device' in units(segment):
            purpose=tuple(sorted(units(segment)&{'practice','analyse','spreadsheet'}))
            add('bring',('device',*purpose),value.find('bring'))
        if 'entry' in units(segment) and 'badge' in units(segment):add('entry',('badge',),value.find('entry'))
        if len(result)==previous_count:scope=previous_scope
    return result


def _same_component(claim,source):
    if claim['role']!=source['role'] or claim['names'] and claim['names']!=source['names']:return False
    if claim['qualifiers']!=source['qualifiers'] or claim['condition']!=source['condition']:return False
    if claim.get('temporal') and source.get('temporal') and claim['temporal']!=source['temporal']:return False
    if claim['role']=='bring':return set(claim['value'])<=set(source['value'])
    if claim['role']=='start':return source['value'][:len(claim['value'])]==claim['value']
    return claim['value']==source['value']


def _source_frames(chunks,names):
    result=[]
    for label,c in enumerate(chunks,1):
        if c is None:continue
        doc_id=getattr(c,'doc_id',c.doc_name)
        doc_text=' '.join(x.text for x in chunks if x is not None and getattr(x,'doc_id',x.doc_name)==doc_id)
        scope={n for n in names if re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',normalize(c.doc_name+' '+doc_text))}
        for frame in _frames(c.text,scope):result.append(dict(frame,label=label))
    return result


def _excerpt(text,language):
    prefix={'vi':'Theo tài liệu nguồn:','en':'According to the source document:','zh':'根据源文档：'}[language]
    # Inline source literals cannot introduce extra citation chips.
    return prefix+' `'+text.replace('`','\\`').replace('\n',' ')+'`'


def bind_fact(text,source_ids,chunks,translation=None,languages=('en',)):
    """Preserve supported components; use attributable exact wording if uncertain.

    Candidate relation, value, entity and qualifications must stay bound. A source
    excerpt is not a semantic approval of an uncertain generated paraphrase.
    """
    empty=lambda state:dict(items=[],state=state,components=[])
    if not isinstance(text,str) or not isinstance(source_ids,list):return empty('error')
    labels=list(dict.fromkeys(n for n in source_ids if type(n) is int and 1<=n<=len(chunks) and chunks[n-1] is not None))
    if not labels:return empty('error')
    claims=_frames(text);names=set().union(*(c['names'] for c in claims)) if claims else _names(text)
    sources=_source_frames(chunks,names);sources=[s for s in sources if s['label'] in labels]
    matches=[];unresolved=[]
    for claim in claims:
        found=[s for s in sources if _same_component(claim,s)]
        if found:matches.append((claim,found))
        else:
            related=[s for s in sources if s['role']==claim['role'] and (not claim['names'] or s['names']==claim['names'])]
            unresolved.append('contradicted' if related and any(s['value']!=claim['value'] or s['qualifiers']!=claim['qualifiers'] for s in related) else 'uncertain' if related else 'absent')
    if translation is not None:
        if not isinstance(translation,str) or anchors(text)!=anchors(translation):return empty('uncertain')
        translated=_frames(translation)
        if len(translated)!=len(claims) or not all(any(_same_component(t,c) for c in claims) for t in translated):return empty('uncertain')
    # Preserve an atomic paraphrase only after relation/value binding and the
    # existing restrictive prose check agree. Unknown prose becomes a quotation.
    approved=sorted({s['label'] for _,found in matches for s in found},key=labels.index) if claims else [n for n in labels if normalize(text).strip().rstrip('.') in {normalize(s).strip().rstrip('.') for s in statements(chunks[n-1].text)}]
    strict=select_sources(text,approved,chunks,translation)
    if strict and (len(claims)==1 and not unresolved or not claims and normalize(text).strip().rstrip('.') in {normalize(s).strip().rstrip('.') for n in labels for s in statements(chunks[n-1].text)}):
        coverage=[dict(source,value=claim['value']) for claim,found in matches for source in found if source['label'] in strict]
        return dict(items=[dict(text=text,translation=translation,sources=strict,kind='paraphrase',coverage=coverage)],state='supported',components=claims)
    if not claims:
        compared=_different_values(text,labels,chunks)
        if compared:return dict(items=[dict(text=text,translation=translation,sources=compared,kind='bounded_comparison')],state='supported',components=[])
        return empty('uncertain')
    items=[];seen=set()
    for claim,found in matches:
        # Each chosen passage already supports this component. Reuse one when
        # equivalent evidence is redundant, without dropping other components.
        source=next((s for s in found if (s['label'],s['quote']) in seen),found[0])
        key=(source['label'],source['quote'])
        if key in seen:continue
        seen.add(key)
        item=dict(text=_excerpt(source['quote'],languages[0]),sources=[source['label']],kind='source_excerpt',coverage=[s for s in sources if s['label']==source['label'] and s['quote']==source['quote']])
        if translation is not None:item['translation']=_excerpt(source['quote'],languages[1])
        items.append(item)
    state='partial_'+unresolved[0] if items and unresolved else unresolved[0] if unresolved else 'supported_extractively'
    return dict(items=items,state=state,components=claims)


def _coverage_key(frame):
    """Property coverage anchored to its exact request-local evidence location.

    A subjectless claim inherits scope only from its accepted source statement.
    Explicit source entities remain distinct even within the same passage.
    """
    return (frame['label'],frame['quote'],tuple(sorted(_names(frame['segment']))),
            frame['role'],tuple(frame['value']),tuple(sorted(frame['qualifiers'])),
            frame['condition'],tuple(frame.get('temporal',())))


def deduplicate_items(items):
    """Remove equivalent accepted claims, retaining different facts on one page."""
    result=[];covered=set();literal=set()
    for original in items:
        item=dict(original,sources=list(dict.fromkeys(original['sources'])))
        keys={_coverage_key(frame) for frame in item.get('coverage',[])}
        signature=(item['text'],item.get('translation'),tuple(item['sources']))
        if signature in literal or keys and keys<=covered:continue
        result.append(item);covered.update(keys);literal.add(signature)
    return result


def summary_excerpts(query,chunks,items,languages=('en',)):
    """Fill explicitly requested summary properties from verbatim source facts."""
    q=normalize(query)
    if not re.search(r'\b(?:summarize|summarise|summary)\b|tom tat',q):return []
    roles=set()
    if re.search(r'\b(?:time|date|when)\b|thoi gian|ngay',q):roles.add('start')
    if re.search(r'\b(?:location|room|place)\b|dia diem|phong',q):roles.add('room')
    if re.search(r'\b(?:preparation|requirements|prepare)\b|chuan bi|yeu cau',q):roles.update(('bring','registration','limit'))
    if re.search(r'\b(?:counts|quantities|numbers)\b|so luong|bao nhieu',q):roles.update(('prepare','receive'))
    names=_names(query);sources=_source_frames(chunks,names)
    covered={_coverage_key(frame) for item in items for frame in item.get('coverage',[])}
    added=[];seen=set()
    for source in sources:
        if source['role'] not in roles:continue
        if names and not names<=source['names']:continue
        if _coverage_key(source) in covered:continue
        key=(source['label'],source['quote'])
        if key in seen:continue
        seen.add(key);coverage=[s for s in sources if s['label']==source['label'] and s['quote']==source['quote']]
        covered.update(_coverage_key(s) for s in coverage)
        item=dict(text=_excerpt(source['quote'],languages[0]),sources=[source['label']],kind='summary_source_excerpt',coverage=coverage)
        if len(languages)==2:item['translation']=_excerpt(source['quote'],languages[1])
        added.append(item)
    return added
