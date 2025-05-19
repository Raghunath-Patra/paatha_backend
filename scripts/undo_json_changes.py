#!/usr/bin/env python3

import os
import sys
import argparse
import logging
from pathlib import Path
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def undo_changes(chapter_dir: str) -> None:
    """Undo changes by removing new files and renaming backup files"""
    chapter_path = Path(chapter_dir)
    if not chapter_path.exists():
        raise ValueError(f"Chapter directory not found: {chapter_dir}")
        
    try:
        # Find all JSON files and their backups
        json_files = list(chapter_path.glob('*.json'))
        
        # Group files by their base name (without backup timestamp)
        file_groups = {}
        for file_path in json_files:
            # Extract base name (e.g., 'gen_qa_sec01' from 'gen_qa_sec01_backup_20250124_130704.json')
            base_name = re.match(r'(.*?)(?:_backup_\d{8}_\d{6})?\.json$', file_path.name).group(1)
            
            if base_name not in file_groups:
                file_groups[base_name] = {'original': None, 'backup': None}
                
            if '_backup_' in file_path.name:
                file_groups[base_name]['backup'] = file_path
            else:
                file_groups[base_name]['original'] = file_path
        
        # Process each group
        for base_name, files in file_groups.items():
            if files['original'] and files['backup']:
                # Remove the current file
                logger.info(f"Removing {files['original']}")
                files['original'].unlink()
                
                # Rename backup to original name
                new_name = files['original']
                logger.info(f"Renaming {files['backup']} to {new_name}")
                files['backup'].rename(new_name)
            else:
                logger.warning(f"Incomplete file pair for {base_name}")

    except Exception as e:
        logger.error(f"Error processing chapter {chapter_dir}: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description='Undo JSON cleaning changes')
    parser.add_argument('chapter', type=str, help='Chapter to process (e.g., jesc101)')
    args = parser.parse_args()

    base_path = Path("backend/questions/cbse/x/science")
    chapter_dir = base_path / args.chapter
    
    if not chapter_dir.exists():
        logger.error(f"Chapter directory not found: {chapter_dir}")
        sys.exit(1)
    
    try:
        logger.info(f"Processing chapter: {args.chapter}")
        undo_changes(str(chapter_dir))
        logger.info("Successfully undid changes")
    except Exception as e:
        logger.error(f"Error undoing changes: {e}")
        raise

if __name__ == "__main__":
    main()