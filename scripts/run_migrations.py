#!/usr/bin/env python3

import sys
import os
import subprocess
import argparse

def run_command(command):
    """Run a shell command and print output"""
    print(f"Running: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    else:
        print(result.stdout)
    return result

def main():
    parser = argparse.ArgumentParser(description='Run database migrations and seed data')
    parser.add_argument('--skip-migrations', action='store_true', help='Skip running alembic migrations')
    parser.add_argument('--skip-seed', action='store_true', help='Skip seeding chapter data')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(script_dir)
    
    # Change to backend directory
    os.chdir(backend_dir)
    
    # Run migrations if not skipped
    if not args.skip_migrations:
        print("Running database migrations...")
        # Skip the problematic migration
        run_command(["alembic", "stamp", "d0caf7350242"])
        # Run any migrations after that one
        run_command(["alembic", "upgrade", "head"])
    
    # Seed chapter data if not skipped
    if not args.skip_seed:
        print("Seeding chapter data...")
        run_command(["python", "scripts/seed_chapters.py"])
    
    print("Done!")

if __name__ == "__main__":
    main()