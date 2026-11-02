"""Hub-compatible missing-item questions with source-bound answer recording.

Follows User-designed building's key/default, proposal, explicit acceptance
pattern. Does not import Hub, call an LLM, or alter/release structural geometry.
"""
import copy
from .pilots.model import stable_hash


def questions(package):
    if not isinstance(package.get('review'),dict) or 'source_package_sha256' not in package['review']:
        raise ValueError('Coordination questions require a source-bound physical review package')
    items=[dict(id=i['id'],kind='default' if i.get('proposed') else 'key',path='physical_review/'+i['id'],
        question=i['title'],evidence=i['basis'],default=i.get('proposed'),value=None,accepted=False) for i in package['review']['items'] if i['status']!='resolved']
    return dict(schema='steltic.physical_review_questions',building_id=package['building_id'],
        source_package_sha256=package['review']['source_package_sha256'],model_sha256=stable_hash(package),groups=[dict(id='physical_data',title='Physical-model coordination',items=items)])


def record_answers(package,document,answers):
    """Validate an explicit answer list and retain it for a recipe revision.

    Answering does not prove geometry now implements an answer. Only rebuilding
    and checking a revised source-bound recipe may close the underlying issue.
    """
    expected=questions(package)
    for field in ['building_id','source_package_sha256','model_sha256']:
        if document.get(field)!=expected[field]: raise ValueError('Stale or mismatched review '+field)
    known={i['id'] for g in expected['groups'] for i in g['items']}; seen=set(); result=[]
    for answer in answers:
        iid=answer.get('id')
        if iid not in known or iid in seen: raise ValueError('Unknown or duplicate review answer '+str(iid))
        if answer.get('accepted') is not True or not isinstance(answer.get('value'),str) or not answer['value'].strip():
            raise ValueError('Answer needs an explicit accepted value')
        if not answer.get('accepted_by'): raise ValueError('Answer needs accepted_by attribution')
        seen.add(iid); result.append(copy.deepcopy(answer))
    return dict(schema='steltic.physical_review_answers',building_id=package['building_id'],source_package_sha256=expected['source_package_sha256'],
        model_sha256=expected['model_sha256'],answers=result,status='awaiting_recipe_implementation_and_recheck')
