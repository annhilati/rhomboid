import os

def clean_environment():
    # Only remove known sensitive keys. Wiping the entire environment on Linux
    # breaks multiprocessing pipes, dynamic linking (LD_LIBRARY_PATH), etc.
    for key in list(os.environ.keys()):
        key_upper = key.upper()
        if 'TOKEN' in key_upper or 'SECRET' in key_upper or 'PASSWORD' in key_upper or 'KEY' in key_upper:
            del os.environ[key]