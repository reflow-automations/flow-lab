from openrouter_guide import model_choices,SUGGESTIONS

def test_shortlist_excludes_missing_models_and_keeps_existing_choice():
    keys=list(SUGGESTIONS)
    models=[{'id':keys[0],'name':'Example A'},{'id':'example/current:free','name':'Current'},
            {'id':'example/paid','name':'Paid'},{'id':'example/other:free','name':'Other'}]
    assert [m['id'] for m in model_choices(models,'example/current:free')]==[keys[0],'example/current:free']
    assert len(model_choices(models,show_all=True))==3
    assert 'example/paid' not in {m['id'] for m in model_choices(models,show_all=True)}

def test_catalogue_change_never_recommends_an_unavailable_id():
    models=[{'id':'example/general-'+str(i)+':free','name':str(i)} for i in range(10)]
    choices=model_choices(models)
    assert len(choices)==3 and all(m['id'] in {r['id'] for r in models} for m in choices)
    assert all('geen gemeten ranglijst' in m['hint'] for m in choices)

def test_code_model_is_not_a_default_fallback_recommendation():
    assert not model_choices([{'id':'example/coder:free','name':'Code'}])
