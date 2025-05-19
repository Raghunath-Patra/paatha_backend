#!/usr/bin/env python3

import os
import sys
import re
import json
import argparse
from pathlib import Path
import logging
from typing import List, Dict, Set
from datetime import datetime
import uuid

# Add parent directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from models import Question
from config.database import SessionLocal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 50  # Number of questions to commit at once

class QuestionProcessor:
    def __init__(self):
        self.processed_files: Set[str] = set()
        self.questions_count = {}
        self.processed_questions: Set[str] = set()
        
        self.category_mapping = {
            'gen': 'generated',
            'ic': 'in_chapter',
            'ec': 'exercise'
        }

    def initialize_chapter_counts(self, chapter_num: int):
        """Initialize or reset question counts for a new chapter"""
        self.questions_count[chapter_num] = {
            'generated': 0,
            'in_chapter': 0,
            'exercise': 0
        }

    def clean_question_text(self, text: str) -> str:
        """Remove question numbers and clean text"""
        text = re.sub(r'^\d+\.\s*', '', text)
        text = text.strip()
        return text

    def determine_category(self, file_name: str) -> str:
        """Determine the category based on the file name"""
        if 'exercise' in file_name:
            return 'exercise'
        elif 'all_questions' in file_name:
            return 'in_chapter'
        elif 'intext' in file_name:
            return 'in_chapter'
        elif 'section' in file_name:
            return 'in_chapter'
        else:
            return 'generated'

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

    def generate_human_readable_id(self, board: str, grade: str, subject: str,
                                 chapter: int, category: str, number: int) -> str:
        """Generate human readable ID for questions"""
        category_prefix = {
            'generated': 'g',
            'in_chapter': 'ic',
            'exercise': 'ec'
        }[category]
        
        return f"{board}_{grade}_{subject}_c{chapter}_{category_prefix}{number:03d}"

    def process_file(self, file_path: Path, db: Session, board: str, grade: str,
                    subject: str) -> None:
        """Process a single question file"""
        if str(file_path) in self.processed_files:
            return
        
        logger.info(f"Processing {file_path}")
        
        # Extract chapter number from file name
        chapter_num = self.extract_chapter_number(file_path.name)
        if chapter_num == 0:
            logger.warning(f"Could not extract chapter number from {file_path.name}")
            return
            
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
                
            batch = []
            
            # Initialize counts for this chapter if not already done
            if chapter_num not in self.questions_count:
                self.initialize_chapter_counts(chapter_num)
            
            for q_data in questions:
                # Clean question text
                if 'question_text' in q_data:
                    q_data['question_text'] = self.clean_question_text(q_data['question_text'])
                else:
                    logger.warning(f"Question missing 'question_text' field: {q_data}")
                    continue
                
                # Make sure we have the required fields
                if 'correct_answer' not in q_data:
                    logger.warning(f"Question missing 'correct_answer' field: {q_data}")
                    continue
                    
                # Determine category based on source field if available
                if 'source' in q_data:
                    source = q_data['source'].lower()
                    if 'exercise' in source:
                        category = 'exercise'
                    elif 'generated' in source or 'gen' in source:
                        category = 'generated'
                    else:
                        category = 'in_chapter'
                else:
                    # Fall back to filename-based categorization
                    category = self.determine_category(file_path.name)
                
                # Use existing question_id if available, otherwise generate one
                if 'question_id' in q_data and q_data['question_id']:
                    human_readable_id = q_data['question_id']
                else:
                    # Use chapter-specific count
                    human_readable_id = self.generate_human_readable_id(
                        board, grade, subject, chapter_num, category, 
                        self.questions_count[chapter_num][category] + 1
                    )
                
                if human_readable_id in self.processed_questions:
                    continue
                
                # Set default values for optional fields
                difficulty = q_data.get('difficulty', 'Medium')
                q_type = q_data.get('type', 'Text')
                options = q_data.get('options', [])
                explanation = q_data.get('explanation', '')
                topic = q_data.get('topic', '')
                bloom_level = q_data.get('bloom_level', '')
                
                question = Question(
                    id=uuid.uuid4(),  # Generate new UUID
                    human_readable_id=human_readable_id,
                    file_source=str(file_path),
                    question_text=q_data['question_text'],
                    type=q_type,
                    difficulty=difficulty,
                    options=options,
                    correct_answer=q_data['correct_answer'],
                    explanation=explanation,
                    topic=topic,
                    bloom_level=bloom_level,
                    board=board,
                    class_level=grade,
                    subject=subject,
                    chapter=chapter_num,
                    category=category,
                    created_at=datetime.utcnow()
                )
                
                batch.append(question)
                self.processed_questions.add(human_readable_id)
                self.questions_count[chapter_num][category] += 1
                
                if len(batch) >= BATCH_SIZE:
                    self.commit_batch(db, batch)
                    batch = []
            
            if batch:
                self.commit_batch(db, batch)
            
            self.processed_files.add(str(file_path))
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")

    def process_subject(self, subject_dir: str, db: Session, board: str, grade: str, subject: str, pattern: str = None, exclude: str = None) -> None:
        """Process all questions in a specific subject folder"""
        subject_path = Path(subject_dir)
        if not subject_path.exists():
            raise ValueError(f"Subject directory not found: {subject_dir}")
            
        logger.info(f"Processing subject {subject} in {grade}")
        
        try:
            # Process all json files in the subject directory
            json_files = list(subject_path.glob('*.json'))
            
            # Apply pattern filter if provided
            if pattern:
                import fnmatch
                json_files = [f for f in json_files if fnmatch.fnmatch(f.name, pattern)]
            
            # Apply exclude filter if provided
            if exclude:
                import fnmatch
                json_files = [f for f in json_files if not fnmatch.fnmatch(f.name, exclude)]
            
            for file_path in sorted(json_files):
                # Skip chapters.json file
                if file_path.name == 'chapters.json':
                    continue
                self.process_file(file_path, db, board, grade, subject)
                
        except Exception as e:
            logger.error(f"Error processing subject {subject}: {str(e)}")

    def commit_batch(self, db: Session, batch: List[Question]) -> None:
        """Commit a batch of questions"""
        try:
            db.add_all(batch)
            db.commit()
            logger.info(f"Successfully committed batch of {len(batch)} questions")
        except IntegrityError as e:
            logger.error(f"Error committing batch: {str(e)}")
            db.rollback()
            # Try to commit one by one
            for question in batch:
                try:
                    db.add(question)
                    db.commit()
                except IntegrityError:
                    db.rollback()
                    logger.error(f"Failed to insert question {question.human_readable_id}")
        except Exception as e:
            logger.error(f"Unexpected error committing batch: {str(e)}")
            db.rollback()

    def delete_questions(self, db: Session, board: str, grade: str, subject: str, chapter_num: int = None):
        """Delete questions based on board, grade, subject, and optionally chapter"""
        try:
            query = db.query(Question).filter(
                Question.board == board,
                Question.class_level == grade,
                Question.subject == subject
            )
            
            if chapter_num is not None:
                query = query.filter(Question.chapter == chapter_num)
                
            count = query.count()
            if count == 0:
                logger.info(f"No questions found to delete for {board}/{grade}/{subject}" + 
                           (f"/chapter-{chapter_num}" if chapter_num else ""))
                return 0
                
            logger.info(f"Deleting {count} questions for {board}/{grade}/{subject}" + 
                       (f"/chapter-{chapter_num}" if chapter_num else ""))
            query.delete()
            db.commit()
            return count
        except Exception as e:
            logger.error(f"Error deleting questions: {str(e)}")
            db.rollback()
            return 0

def main():
    parser = argparse.ArgumentParser(description='Process questions for a specific subject')
    parser.add_argument('--board', type=str, default='cbse', help='Board name (default: cbse)')
    parser.add_argument('--class', dest='class_level', type=str, required=True, 
                        help='Class level (e.g., xi, xii)')
    parser.add_argument('--subject', type=str, required=True, 
                        help='Subject code (e.g., leph1dd, lech1dd)')
    parser.add_argument('--pattern', type=str, help='File pattern to include (e.g., "*all_questions.json")')
    parser.add_argument('--exclude', type=str, help='File pattern to exclude (e.g., "*all_questions.json")')
    parser.add_argument('--delete', action='store_true', help='Delete existing questions before processing')
    parser.add_argument('--delete-only', action='store_true', help='Only delete questions, don\'t process new ones')
    parser.add_argument('--chapter', type=int, help='Specific chapter to process/delete')
    args = parser.parse_args()

    board = args.board.lower()
    class_level = args.class_level.lower()
    subject = args.subject.lower()
    
    base_path = Path("questions")
    subject_dir = base_path / board / class_level / subject
    
    if not subject_dir.exists():
        logger.error(f"Subject directory not found: {subject_dir}")
        sys.exit(1)
        
    processor = QuestionProcessor()
    
    try:
        db = SessionLocal()
        
        # Delete existing questions if requested
        if args.delete or args.delete_only:
            deleted = processor.delete_questions(db, board, class_level, subject, args.chapter)
            logger.info(f"Deleted {deleted} questions")
            
            if args.delete_only:
                return
        
        logger.info(f"Processing subject: {subject} for {board} {class_level}")
        processor.process_subject(
            str(subject_dir), db, board, class_level, subject,
            args.pattern, args.exclude
        )
        
        # Log summary
        logger.info("\nProcessing Summary:")
        total = sum(sum(counts.values()) for counts in processor.questions_count.values())
        logger.info(f"Total questions processed: {total}")
        for chapter, counts in sorted(processor.questions_count.items()):
            chapter_total = sum(counts.values())
            logger.info(f"Chapter {chapter}: {chapter_total} questions")
            for category, count in counts.items():
                logger.info(f"  - {category.capitalize()}: {count} questions")
                    
    except Exception as e:
        logger.error(f"Error processing questions: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()