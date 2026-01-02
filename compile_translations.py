#!/usr/bin/env python3
"""
Script to compile Qt translation files (.ts) to binary files (.qm)
Run this script after updating translation files to make them available to the application.
"""

import subprocess
import sys
from pathlib import Path

def compile_translations():
    """Compile all .ts files in the translations directory to .qm files"""
    
    # Get the translations directory
    script_dir = Path(__file__).parent
    translations_dir = script_dir / "restictray" / "translations"
    
    if not translations_dir.exists():
        print(f"Error: Translations directory not found: {translations_dir}")
        return False
    
    # Find all .ts files
    ts_files = list(translations_dir.glob("*.ts"))
    
    if not ts_files:
        print(f"No .ts files found in {translations_dir}")
        return False
    
    print(f"Found {len(ts_files)} translation file(s) to compile:")
    
    success_count = 0
    failed_count = 0
    
    for ts_file in ts_files:
        qm_file = ts_file.with_suffix(".qm")
        print(f"\nCompiling: {ts_file.name} -> {qm_file.name}")
        
        try:
            # Try lrelease-qt6 first, then lrelease
            lrelease_cmd = None
            for cmd in ['lrelease-qt6', 'pyside6-lrelease', '/usr/lib/python3/dist-packages/PySide6/lrelease']:
                try:
                    result = subprocess.run([cmd, '--version'], 
                                 capture_output=True)
                    # If command exists (whether exit code is 0 or not), use it
                    if result.returncode is not None:
                        lrelease_cmd = cmd
                        break
                except FileNotFoundError:
                    continue
            
            if not lrelease_cmd:
                print("Error: lrelease command not found. Please install Qt tools.")
                print("  Ubuntu/Debian: sudo apt install qt6-tools-dev")
                print("  Fedora: sudo dnf install qt6-linguist")
                print("  Arch: sudo pacman -S qt6-tools")
                print("  pip: pip install PySide6 (includes lrelease)")
                failed_count += 1
                continue
            
            # Compile the translation file
            result = subprocess.run(
                [lrelease_cmd, str(ts_file), '-qm', str(qm_file)],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✓ Successfully compiled {ts_file.name}")
                success_count += 1
            else:
                print(f"✗ Failed to compile {ts_file.name}")
                print(f"  Error: {result.stderr}")
                failed_count += 1
                
        except Exception as e:
            print(f"✗ Error compiling {ts_file.name}: {e}")
            failed_count += 1
    
    print(f"\n{'='*60}")
    print(f"Compilation complete:")
    print(f"  Success: {success_count}")
    print(f"  Failed: {failed_count}")
    print(f"{'='*60}")
    
    return failed_count == 0

if __name__ == "__main__":
    success = compile_translations()
    sys.exit(0 if success else 1)
