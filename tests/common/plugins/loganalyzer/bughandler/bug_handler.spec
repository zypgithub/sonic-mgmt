# -*- mode: python ; coding: utf-8 -*-
# Optimized PyInstaller spec for SONiC Bug Handler

a = Analysis(
    ['bug_handler.py'],
    pathex=["../../../../../../devts/"],
    binaries=[],
    datas=[
        # Essential data files for log analysis
        ("../loganalyzer_common_match.txt", "."),
        ("../loganalyzer_common_ignore.txt", "."),
        ("../loganalyzer_common_expect.txt", "."),
        ("../../loganalyzer_dynamic_errors_ignore", "./tests/common/plugins/loganalyzer_dynamic_errors_ignore"),
        ("../../../../../ngts/helpers/bug_handler/sonic_bug_handler.conf", "./ngts/helpers/bug_handler/")
    ],
    hiddenimports=[
        # Explicitly include modules that might not be auto-detected
        'paramiko.transport',
        'paramiko.client', 
        'paramiko.channel',
        'six.moves',
        'perscache'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy unused modules to reduce build size
        'matplotlib',        # Plotting library (not used)
        'scipy',            # Scientific computing (not used) 
        'numpy.f2py',       # Fortran interface (not used)
        'numpy.distutils',  # Build utilities (not used)
        'pandas.plotting',  # Plotting functionality (not used)
        'pandas.io.excel',  # Excel I/O (not used)
        'pandas.io.sql',    # SQL I/O (not used)
        'tkinter',          # GUI toolkit (not used)
        'PyQt5',            # GUI toolkit (not used)
        'PyQt6',            # GUI toolkit (not used)
        'PySide2',          # GUI toolkit (not used)
        'PySide6',          # GUI toolkit (not used)
        'IPython',          # Interactive Python (not used)
        'jupyter',          # Jupyter notebook (not used)
        'notebook',         # Jupyter notebook (not used)
    ],
    noarchive=False,
    optimize=2,  # Increased optimization level
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='bug_handler',
    debug=False,                      # Disable debug for smaller size
    bootloader_ignore_signals=False,
    strip=True,                       # Strip symbols for smaller size
    upx=True,                         # Compress with UPX
    console=True,                     # Console application
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
    strip=True,                       # Strip binaries for smaller size
    upx=True,                         # Compress binaries with UPX
    upx_exclude=[
        # Exclude problematic binaries from UPX compression
        'vcruntime*.dll',
        'msvcp*.dll', 
        'api-ms-win*.dll',
    ],
    name='bug_handler',
)
