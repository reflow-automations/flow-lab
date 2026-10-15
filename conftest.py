import pytest
import storage

@pytest.fixture(scope='session')
def tk_session():
    import tkinter as tk
    root=tk.Tk();root.withdraw()
    yield root
    root.destroy()

@pytest.fixture
def tk_window(tk_session):
    import tkinter as tk
    window=tk.Toplevel(tk_session);window.withdraw()
    yield window
    if window.winfo_exists():window.destroy()

@pytest.fixture(autouse=True)
def isolated_data(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'test.sqlite')
    storage.init()
