"""Explicit CF staging step: prefetch pinned models into the app before droplet creation.

pip builds this local project in place. PIP_NO_CACHE_DIR in the manifest ensures
this step is rerun for each staging operation. No model downloads happen at startup.
"""
import subprocess
import sys
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py


class PrefetchModels(build_py):
    def run(self):
        app = Path(__file__).resolve().parents[1]
        script = app / 'scripts' / 'download_models.py'
        subprocess.run([sys.executable, str(script)], cwd=app, check=True)
        subprocess.run([sys.executable, str(script), '--verify'], cwd=app, check=True)
        super().run()


setup(name='sensevoice-cf-model-stage', version='1.0.0',
      py_modules=['sensevoice_cf_model_stage'], cmdclass={'build_py': PrefetchModels})
