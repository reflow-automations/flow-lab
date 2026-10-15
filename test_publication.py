from publication_guard import validate_public_files

def test_private_file_rejected_even_if_added_to_allowlist():
    assert validate_public_files({'data/personal.json':b'{}'},['data/personal.json'])

def test_unknown_file_rejected():
    assert validate_public_files({'notes.txt':b'private'},[])

def test_credentials_and_user_paths_are_rejected():
    private_path='C:'+chr(92)+'Users'+chr(92)+'Example'+chr(92)+'private.txt'
    for text in ['sk-proj-'+('a'*30),'ghp_'+('b'*30),private_path,'person'+'@gmail.com']:
        assert validate_public_files({'app.py':text.encode()},['app.py'])

def test_only_empty_environment_example_allowed():
    assert not validate_public_files({'.env.example':b'# local only\nOPENAI_API_KEY=\n'},['.env.example'])
    assert validate_public_files({'.env.example':b'OPENAI_API_KEY=not-empty'},['.env.example'])

def test_generic_source_allowed():
    assert not validate_public_files({'app.py':b'print("hello")'},['app.py'])
