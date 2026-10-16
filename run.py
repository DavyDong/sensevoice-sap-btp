from app.settings import Settings

if __name__ == '__main__':
    import os
    from pathlib import Path
    root = Path(__file__).resolve().parent
    os.chdir(root)
    for name, directory in {'HF_HOME':'huggingface', 'MODELSCOPE_CACHE':'modelscope',
                            'NUMBA_CACHE_DIR':'numba', 'MPLCONFIGDIR':'matplotlib'}.items():
        os.environ.setdefault(name, str(root / '.cache' / directory))
    import uvicorn
    settings = Settings()
    settings.validate()
    uvicorn.run('app.main:create_app', factory=True, host=settings.host, port=settings.port,
                workers=1, ws_max_size=18000, ws_max_queue=4, timeout_keep_alive=10,
                access_log=False)
