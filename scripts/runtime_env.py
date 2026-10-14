import os

def configured(name, default=None):
    return os.environ.get("VAKE_" + name) or default
