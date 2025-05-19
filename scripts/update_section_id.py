#!/usr/bin/env python3

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List
import re

# Add parent directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from sqlalchemy import text
from sqlalchemy.orm import Session
from models import Question  # Assuming this exists in your codebase
from config.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SectionIDUpdater:
    def __init__(self):
        self.processed_files = set()
        self.updated_count = 0
        self.errors = 0
        self.skipped = 0
        self.not_found = 0
        self.question_map = {}  # Map of human_readable_id to section_id
        
    def extract_chapter_number(self, file_name: str) -> int:
        """Extract chapter number from file names of different subject patterns"""
        # Handle kebo101, lebo101, keph101, etc.
        match = re.search(r'[kl]e(?:bo|ph|ch|mh)(\d)??(\d{2,3})_', file_name)
        if match:
            chapter_num = match.group(2)
            return int(chapter_num)
        
        # Fallback extraction - look for any 2-3 digit number in the filename
        digits_match = re.search(r'(\d{2,3})_all_questions', file_name)
        if digits_match:
            return int(digits_match.group(1))
            
        return 0
        
    def add_section_id_column(self, db: Session) -> bool:
        """Add section_id column to the questions table if it doesn't exist"""
        try:
            # Check if the column already exists
            result = db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'questions' AND column_name = 'section_id'"
            )).fetchone()
            
            if result:
                logger.info("section_id column already exists")
                return True
                
            # Add the column
            db.execute(text(
                "ALTER TABLE questions ADD COLUMN section_id text"
            ))
            db.commit()
            logger.info("Successfully added section_id column")
            return True
        except Exception as e:
            logger.error(f"Error adding section_id column: {str(e)}")
            db.rollback()
            return False
            
    def process_file(self, file_path: Path) -> None:
        """Process a single question file to collect section_id data"""
        if str(file_path) in self.processed_files:
            return
        
        logger.info(f"Processing {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                try:
                    questions = json.load(f)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON file {file_path}: {str(e)}")
                    return
                
            if not questions:
                logger.warning(f"No valid questions found in {file_path}")
                return
                
            # Ensure questions is a list
            if not isinstance(questions, list):
                questions = [questions]
                
            for q_data in questions:
                # Skip questions without question_id or section_id
                if 'question_id' not in q_data or 'section_id' not in q_data:
                    self.skipped += 1
                    continue
                    
                question_id = q_data['question_id']
                section_id = q_data['section_id']
                
                # Store the mapping
                self.question_map[question_id] = section_id
                
            self.processed_files.add(str(file_path))
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")
            self.errors += 1
            
    def process_subject(self, subject_dir: str) -> None:
        """Process all questions in a specific subject folder"""
        subject_path = Path(subject_dir)
        if not subject_path.exists():
            raise ValueError(f"Subject directory not found: {subject_dir}")
            
        logger.info(f"Processing subject directory: {subject_dir}")
        
        try:
            # Process all json files in the subject directory
            json_files = list(subject_path.glob('*.json'))
            
            for file_path in sorted(json_files):
                # Skip chapters.json file
                if file_path.name == 'chapters.json':
                    continue
                self.process_file(file_path)
                
        except Exception as e:
            logger.error(f"Error processing subject directory: {str(e)}")
            
    def update_database(self, db: Session) -> None:
        """Update the database with section_id values"""
        if not self.question_map:
            logger.warning("No section_id data collected, nothing to update")
            return
            
        logger.info(f"Updating database with {len(self.question_map)} section_id values")
        
        # Create a batch update query for better performance
        batch_size = 100
        items = list(self.question_map.items())
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i+batch_size]
            try:
                for human_readable_id, section_id in batch:
                    result = db.execute(text(
                        "UPDATE questions SET section_id = :section_id "
                        "WHERE human_readable_id = :human_readable_id"
                    ), {"section_id": section_id, "human_readable_id": human_readable_id})
                    
                    if result.rowcount == 0:
                        self.not_found += 1
                    else:
                        self.updated_count += result.rowcount
                
                db.commit()
                logger.info(f"Updated batch of {len(batch)} questions")
            except Exception as e:
                logger.error(f"Error updating section_id batch: {str(e)}")
                db.rollback()
                self.errors += 1

def main():
    parser = argparse.ArgumentParser(description='Update section_id field for questions')
    parser.add_argument('--board', type=str, default='cbse', help='Board name (default: cbse)')
    parser.add_argument('--class', dest='class_level', type=str, required=True, 
                        help='Class level (e.g., xi, xii, viii)')
    parser.add_argument('--subject', type=str, required=True, 
                        help='Subject code (e.g., leph1dd, lech1dd, hemh1dd)')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Just process files without updating the database')
    args = parser.parse_args()

    board = args.board.lower()
    class_level = args.class_level.lower()
    subject = args.subject.lower()
    
    # Questions directory is at the same level as scripts in the backend folder
    script_dir = Path(os.path.dirname(os.path.abspath(__file__)))
    backend_dir = script_dir.parent
    base_path = backend_dir / "questions"
    subject_dir = base_path / board / class_level / subject
    
    if not subject_dir.exists():
        logger.error(f"Subject directory not found: {subject_dir}")
        sys.exit(1)
        
    updater = SectionIDUpdater()
    
    try:
        # Process all JSON files to collect section_id data
        logger.info(f"Processing subject: {subject} for {board} {class_level}")
        updater.process_subject(str(subject_dir))
        
        if args.dry_run:
            logger.info(f"Dry run completed. Found {len(updater.question_map)} section_id values.")
            return
            
        # Update the database
        db = SessionLocal()
        
        # Add the section_id column if it doesn't exist
        if not updater.add_section_id_column(db):
            logger.error("Failed to add section_id column, aborting")
            return
            
        # Update the database with collected section_id values
        updater.update_database(db)
        
        # Log summary
        logger.info("\nUpdate Summary:")
        logger.info(f"Total section_id values found: {len(updater.question_map)}")
        logger.info(f"Total rows updated: {updater.updated_count}")
        logger.info(f"Questions not found: {updater.not_found}")
        logger.info(f"Files processed: {len(updater.processed_files)}")
        logger.info(f"Questions skipped: {updater.skipped}")
        logger.info(f"Errors: {updater.errors}")
                    
    except Exception as e:
        logger.error(f"Error updating section_id values: {e}")
        raise
    finally:
        if 'db' in locals():
            db.close()

if __name__ == "__main__":
    main()