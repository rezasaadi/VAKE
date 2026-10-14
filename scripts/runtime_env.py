"""Resolve the environment settings used by VAKE commands."""
import os

def configured(name, default=None):
    return os.environ.get("VAKE_" + name) or default
