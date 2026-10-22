# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\project\\noisekit\\apps\\desktop\\main.py'],
    pathex=['E:\\project\\noisekit'],
    binaries=[],
    datas=[('d:\\Python311\\Lib\\site-packages\\_sounddevice_data', '_sounddevice_data')],
    hiddenimports=['_sounddevice_data', 'sounddevice'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'pytest', 'IPython', 'notebook', 'jupyter', 'PyQt5', 'PyQt6', 'torch', 'torchvision', 'cv2', 'transformers', 'onnxruntime', 'duckdb', 'openvino', 'pandas', 'babel', 'matplotlib', 'numba', 'llvmlite', 'sympy', 'sklearn', 'tensorflow', 'jax', 'h5py', 'tables', 'numexpr'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NoiseKit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NoiseKit',
)
