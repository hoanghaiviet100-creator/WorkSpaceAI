"""Requested-language constraints and literal-aware CJK validation."""
import re
from .claim_evidence import anchors,normalize,statements,_entities

_CJK=re.compile(r'[\u3400-\u9fff\uf900-\ufaff\U00020000-\U0003134f]')


def requested_languages(query):
    bilingual=bool(re.search(r'\bbilingual\b|song ngữ',query,re.I) or
        (re.search(r'\b(?:answer|respond|reply)\b|trả lời',query,re.I) and
         re.search(r'Vietnamese|tiếng Việt',query,re.I) and re.search(r'English|tiếng Anh',query,re.I)))
    if bilingual:return ('en','vi')
    vietnamese=bool(re.search(r'[\u0102-\u01b0\u1ea0-\u1ef9]',query))
    if re.search(r'in Chinese|bằng tiếng (?:Trung|Hoa)|用中文|中文回答|请用中文',query,re.I):return ('zh',)
    if re.search(r'in English|bằng tiếng Anh',query,re.I):return ('en',)
    if re.search(r'in Vietnamese|bằng tiếng Việt',query,re.I):return ('vi',)
    if _CJK.search(query) and not vietnamese:return ('zh',)
    return ('vi',) if vietnamese else ('en',)


def language_constraint(languages):
    if len(languages)==2:return 'Response languages: English in text; Vietnamese in translation. Both variants express exactly the same fact and use the same sources. All prose in each field must stay in its designated language; never mix Chinese prose into either field. Preserve exact identifiers, proper names, filenames and explicitly quoted original source text.'
    name={'vi':'Vietnamese','en':'English','zh':'Chinese'}[languages[0]]
    return f'Response language: {name}. Write ALL answer prose in {name}, with natural complete sentences. Preserve exact identifiers, proper names, filenames and explicitly quoted original source text. Do not switch languages or mix Chinese prose into a non-Chinese answer.'


def language_valid(text,language,chunks):
    if language=='zh':return True
    sources='\n'.join(c.text for c in chunks)
    value=re.sub(r'\[(?:citation:\s*)?\d+\]','',text)
    # Only exact source literals are exempt, never arbitrary generated quotations.
    def quote(match):
        literal=match.group(1) or match.group(2) or match.group(3)
        return '' if literal in sources else match.group(0)
    value=re.sub(r'"([^"\n]+)"|“([^”\n]+)”|`([^`\n]+)`',quote,value)
    for chunk in chunks:value=value.replace(chunk.doc_name,'')
    names=re.findall(r'(?:name|named|author|姓名|名称|名字|项目|作者|họ tên|tên)\s*[:：]\s*([^\s,.;]+)',sources,re.I)
    for name in names:value=value.replace(name,'')
    # Mixed-script technical IDs are literals only when present in an actual source.
    for token in re.findall(r'[\w.-]+',value):
        if _CJK.search(token) and re.search(r'[A-Za-z]',token) and re.search(r'[0-9_.-]',token) and token in sources:
            value=value.replace(token,'')
    return not _CJK.search(value)


def repair_preserves(original,repaired,chunks):
    """Repair may choose exact source wording with the original factual anchors.

    The deliberately extractive rule cannot authorize a new paraphrased claim.
    Cross-language repairs without such wording fall back instead of guessing.
    """
    key=anchors(original)
    if not key or anchors(repaired)!=key:return False
    candidates={normalize(line).strip().rstrip('.。') for c in chunks for line in statements(c.text)
                if anchors(line)==key and _entities(original)<=_entities(line)}
    return len(candidates)==1 and normalize(repaired).strip().rstrip('.。') in candidates
