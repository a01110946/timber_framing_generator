# File: timber_framing_generator/dev_utils/reload_modules.py

import sys
import importlib
import os

def clear_module_cache(project_root):
    """
    Walks through the project directory and removes all __pycache__ directories.
    
    Args:
        project_root: Path to your project's root directory
    """
    for root, dirs, files in os.walk(project_root):
        if '__pycache__' in dirs:
            cache_dir = os.path.join(root, '__pycache__')
            try:
                for cache_file in os.listdir(cache_dir):
                    cache_path = os.path.join(cache_dir, cache_file)
                    os.remove(cache_path)
                os.rmdir(cache_dir)
                print(f"Cleared cache in: {cache_dir}")
            except Exception as e:
                print(f"Error clearing cache in {cache_dir}: {e}")

def reload_project_modules(project_root):
    """
    Reloads all project modules that have been imported.
    
    Args:
        project_root: Path to your project's root directory
    """
    # Get the project name from the root directory
    project_name = os.path.basename(project_root)
    
    # Find and reload all project modules
    for module_name in list(sys.modules.keys()):
        if module_name.startswith(project_name) or module_name.startswith('src.'):
            try:
                if module_name in sys.modules:
                    importlib.reload(sys.modules[module_name])
                    print(f"Reloaded module: {module_name}")
            except Exception as e:
                print(f"Error reloading {module_name}: {e}")