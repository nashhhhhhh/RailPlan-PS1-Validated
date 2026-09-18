"""Create a source-only release ZIP. Never packages environment files or dependencies."""
import argparse
import os
from pathlib import Path
import zipfile

EXCLUDED_DIRS = {'node_modules','dist','.next','.git','.venv','venv','__pycache__',
                 '.pytest_cache','.mypy_cache','.ruff_cache','.cache','.wrangler','.vite',
                 '.openai','coverage','htmlcov','test-tmp','.test-tmp','ui-screenshots','logs'}

def excluded(path):
    name=path.name
    return (any(p in EXCLUDED_DIRS or p.endswith('.egg-info') or p.startswith('pytest-cache-files-') for p in path.parts)
            # Root build/ contains licensed build-plugin SOURCE, not build output.
            or 'frontend/build' in path.as_posix()
            or name.startswith('.env') or name in {'.DS_Store','.npmrc','.coverage','next-env.d.ts'}
            or path.suffix in {'.pyc','.pyo','.tsbuildinfo','.log','.pem','.key','.zip'}
            or name.startswith('credentials') or name.startswith('secrets'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    files=[]
    for directory,dirs,names in os.walk(root):
        dirs[:]=sorted(d for d in dirs if not excluded(Path(directory).relative_to(root)/d))
        for name in sorted(names):
            path=Path(directory)/name
            if not path.is_symlink() and not excluded(path.relative_to(root)):
                files.append(path)
    with zipfile.ZipFile(args.output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path,Path('RailPlan-PS1-Validated')/path.relative_to(root))
    with zipfile.ZipFile(args.output) as archive:
        assert archive.testzip() is None
        assert all(not excluded(Path(name)) for name in archive.namelist())
    print(f'Packaged {len(files)} source files: {args.output} ({args.output.stat().st_size} bytes)')

if __name__=='__main__':
    main()
