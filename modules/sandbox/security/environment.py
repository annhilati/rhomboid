import os

def clean_environment():
    # Keep only absolute bare minimum for Python to run
    allowed = {'PATH', 'SYSTEMROOT', 'USERPROFILE', 'LANG', 'LC_ALL'}
    for key in list(os.environ.keys()):
        if key not in allowed:
            del os.environ[key]