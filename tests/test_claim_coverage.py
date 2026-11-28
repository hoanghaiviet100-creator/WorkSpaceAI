"""Deterministic component and exact-source coverage contracts."""
from types import SimpleNamespace as C
from backend.algorithms.claim_evidence import bind_fact,summary_excerpts

def c(text,name='alpha.txt'):return C(text=text,doc_name=name,doc_id=name)

def test_joint_properties_and_partial_preservation():
    cs=[c('The Alpha workshop starts at 08:20 on 12 December 2026.'),c('The Alpha workshop takes place in room R207.')]
    result=bind_fact('The Alpha workshop starts at 08:20 on 12 December 2026 in room R207.',[1,2],cs)
    assert {n for i in result['items'] for n in i['sources']}=={1,2}
    assert all(i['kind']=='source_excerpt' for i in result['items'])
    partial=bind_fact('The Alpha workshop takes place in room R207 and prepares 90 kits.',[1,2],cs)
    assert partial['state'].startswith('partial_')
    assert 'R207' in str(partial['items']) and '90' not in str(partial['items'])

def test_subjects_values_conditions_and_negation_stay_bound():
    cs=[c('Alpha prepares 32 kits. Beta prepares 47 kits.')]
    assert not bind_fact('Alpha prepares 47 kits.',[1],cs)['items']
    assert not bind_fact('Alpha prepares 47 kits and Beta prepares 32 kits.',[1],cs)['items']
    cs=[c('If power fails, the Alpha workshop takes place in room R207.')]
    assert not bind_fact('The Alpha workshop takes place in room R207.',[1],cs)['items']
    assert bind_fact(cs[0].text,[1],cs)['items']
    cs=[c('Participants never bring laptops.')]
    assert not bind_fact('Participants bring laptops.',[1],cs)['items']
    assert bind_fact(cs[0].text,[1],cs)['items']

def test_deadline_limit_joint_sources_and_general_paraphrase():
    cs=[c('Participants must register by 12 December 2026.'),c('Each team may register at most 5 participants.')]
    b=bind_fact('Participants must register by 12 December 2026, with each team allowed to register at most 5 participants.',[1,2],cs)
    assert {n for i in b['items'] for n in i['sources']}=={1,2}
    assert not bind_fact('Participants must register by 11 December 2026.',[1],cs)['items']
    cs=[c('Participants bring laptops to practice analysing spreadsheet data.')]
    assert bind_fact('Participants are required to bring laptops for the practical exercise.',[1],cs)['items']

def test_summary_coverage_uses_exact_authorized_source_and_same_bilingual_refs():
    cs=[c('The Alpha workshop takes place in room R207.'),c('Participants bring laptops to practice analysing spreadsheet data.')]
    items=bind_fact(cs[0].text,[1,2],cs)['items']
    extra=summary_excerpts('Summarize the Alpha workshop location and preparation requirements.',cs,items,('en','vi'))
    assert len(extra)==1 and extra[0]['sources']==[2]
    assert cs[1].text in extra[0]['text'] and cs[1].text in extra[0]['translation']
    assert not summary_excerpts('Where is Alpha?',cs,items)
    assert not bind_fact(cs[0].text,[2],cs)['items']

def test_irrelevant_matching_room_and_unfiltered_fallback_are_rejected():
    cs=[c('The Alpha workshop takes place in room R207.'),c('Participants discuss room R207 while practising spreadsheet data.')]
    assert bind_fact(cs[0].text,[1,2],cs)['items'][0]['sources']==[1]
    assert not bind_fact('The tuition is 900 dollars.',[1,2],cs)['items']
    assert not bind_fact(cs[0].text,None,cs)['items']


def test_copular_property_subject_variants_use_the_same_source():
    cs=[c('Orion takes place in room J614.','orion.txt'),c('Orion prepares 43 kits.','orion.txt')]
    for text in ('Phòng học Orion là phòng J614.','Phòng của Orion là J614.','The assigned room for Orion is J614.', 'Orion is in room J614.','The room for Orion is room J614.'):
        b=bind_fact(text,[1,2],cs)
        assert b['items'] and {n for i in b['items'] for n in i['sources']}=={1}
        assert all('J614' in i['text'] for i in b['items'])

def test_copular_scope_does_not_erase_entity_condition_negation_or_date():
    source=c('Orion takes place in room J614.','orion.txt')
    for text in ('The room for Lyra is J614.','The room for Orion is not J614.'):
        assert not bind_fact(text,[1],[source])['items']
    assert not bind_fact('The room for Orion is J614.',[1],[c('If power fails, Orion takes place in room J614.')])['items']
    assert not bind_fact('Orion takes place in room J614 on 14 December 2026.',[1],[c('Orion takes place in room J614 on 13 December 2026.')])['items']
    assert not bind_fact('The room for Orion is J614.',[1],[c('Orion discusses room J614.')])['items']

def test_summary_coverage_uses_accepted_evidence_before_rendering():
    from backend.algorithms.claim_evidence import deduplicate_items
    cs=[c('Participants must register by 13 December 2026. Each team may register at most 6 participants. Participants bring laptops to practice analysing spreadsheet data.')]
    items=[]
    for text in ('Participants must register by 13 December 2026.','Each team may register at most 6 participants.','Participants bring laptops to practice analysing spreadsheet data.'):
        items+=bind_fact(text,[1],cs)['items']
    assert len(deduplicate_items(items+items))==3
    assert all(i['sources']==[1] for i in items)
    # Rendered wording is deliberately unavailable: accepted coverage is sufficient.
    assert not summary_excerpts('Summarize the preparation requirements.',cs,[dict(i,text='') for i in items])

def test_subjectless_coverage_stays_with_accepted_document():
    cs=[c('Participants must register by 13 December 2026.','orion.txt'),c('Participants must register by 13 December 2026.','lyra.txt')]
    items=bind_fact(cs[0].text,[1],cs)['items']
    additions=summary_excerpts('Summarize the preparation requirements.',cs,items)
    assert len(additions)==1 and additions[0]['sources']==[2]

def test_deduplication_does_not_globally_remove_same_page_citations():
    from backend.algorithms.claim_evidence import deduplicate_items
    cs=[c('The Alpha workshop takes place in room R207. The Alpha workshop starts at 08:20.')]
    items=[i for t in ('The Alpha workshop takes place in room R207.','The Alpha workshop starts at 08:20.') for i in bind_fact(t,[1,1],cs)['items']]
    kept=deduplicate_items(items+items)
    assert len(kept)==2 and all(i['sources']==[1] for i in kept)
