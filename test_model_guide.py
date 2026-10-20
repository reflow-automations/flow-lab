from model_guide import load_guide,guide_text
from engines import ASR_MODELS,FORMAT_MODELS

def test_every_selectable_model_has_explanation():
    guide=load_guide()
    assert set(guide['engines'])==set(ASR_MODELS)|{'parakeet','whisper','hybrid-parakeet'}
    assert set(guide['formatters'])=={'cloud-mini','local','verbatim','openrouter-free'}
    assert 'cloud-nano' not in guide['formatters']
    assert set(guide['desktop'])=={'local','verbatim','cloud-mini','openrouter-free'}

def test_measurements_are_route_level_with_limits():
    guide=load_guide()
    assert len(guide['measurements'])==6
    assert all(r['runs']>=3 and '+' in r['route'] for r in guide['measurements'])
    text=guide_text(guide)
    assert 'geen garanties' in text and 'opgewarmde' in text
    assert '0,55 s' in text and '1,02 s' in text
    assert 'niet per definitie het ruwe transcript' in text
