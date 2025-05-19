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
        if 'gen_qa' in file_name:
            return 'generated'
        elif 'exercise' in file_name:
            return 'exercise'
        else:
            return 'in_chapter'

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
                    subject: str, chapter_num: int) -> None:
        """Process a single question file"""
        if str(file_path) in self.processed_files:
            return
        
        logger.info(f"Processing {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                try:
                    questions = json.load(f)
                    if not isinstance(questions, list):
                        questions = [questions]
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON file {file_path}: {str(e)}")
                    return
                
            if not questions:
                logger.warning(f"No valid questions found in {file_path}")
                return
                
            batch = []
            category = self.determine_category(file_path.name)
            
            # Initialize counts for this chapter if not already done
            if chapter_num not in self.questions_count:
                self.initialize_chapter_counts(chapter_num)
            
            for q_data in questions:
                q_data['question_text'] = self.clean_question_text(q_data['question_text'])
                
                # Use chapter-specific count
                human_readable_id = self.generate_human_readable_id(
                    board, grade, subject, chapter_num, category, 
                    self.questions_count[chapter_num][category] + 1
                )
                
                if human_readable_id in self.processed_questions:
                    continue
                
                question = Question(
                    human_readable_id=human_readable_id,
                    file_source=str(file_path),
                    question_text=q_data['question_text'],
                    type=q_data['type'],
                    difficulty=q_data['difficulty'],
                    options=q_data.get('options'),
                    correct_answer=q_data['correct_answer'],
                    explanation=q_data.get('explanation'),
                    topic=q_data.get('topic'),
                    bloom_level=q_data.get('bloom_level'),
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

    def process_chapter(self, chapter_dir: str, db: Session) -> None:
        """Process all questions in a specific chapter folder"""
        chapter_path = Path(chapter_dir)
        if not chapter_path.exists():
            raise ValueError(f"Chapter directory not found: {chapter_dir}")
            
        chapter_num = int(re.search(r'jesc(\d+)', chapter_path.name).group(1))
        logger.info(f"Processing chapter {chapter_num}")
        
        try:
            # Process general questions
            gen_files = sorted(chapter_path.glob('gen_qa_sec*.json'))
            for file_path in gen_files:
                self.process_file(file_path, db, 'cbse', 'x', 'science', chapter_num)
                
            # Process in-chapter questions
            ic_files = sorted(chapter_path.glob(f'jesc{chapter_num:03d}_sec*_answers.json'))
            for file_path in ic_files:
                if not 'exercise' in file_path.name:
                    self.process_file(file_path, db, 'cbse', 'x', 'science', chapter_num)
                
            # Process exercise questions
            ex_files = sorted(chapter_path.glob(f'jesc{chapter_num:03d}_exercise_answers.json'))
            for file_path in ex_files:
                self.process_file(file_path, db, 'cbse', 'x', 'science', chapter_num)
                
        except Exception as e:
            logger.error(f"Error processing chapter {chapter_num}: {str(e)}")

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

def main():
    parser = argparse.ArgumentParser(description='Process questions from a specific chapter')
    parser.add_argument('chapter', type=str, help='Chapter to process (e.g., jesc101 for chapter 1)')
    args = parser.parse_args()

    base_path = Path("backend/questions/cbse/x/science")
    chapter_dir = base_path / args.chapter
    
    if not chapter_dir.exists():
        logger.error(f"Chapter directory not found: {chapter_dir}")
        sys.exit(1)
        
    processor = QuestionProcessor()
    
    try:
        db = SessionLocal()
        
        logger.info(f"Processing chapter: {args.chapter}")
        processor.process_chapter(str(chapter_dir), db)
        
        # Log summary for the specific chapter
        chapter_num = int(re.search(r'jesc(\d+)', args.chapter).group(1))
        if chapter_num in processor.questions_count:
            logger.info("\nProcessing Summary:")
            total = sum(processor.questions_count[chapter_num].values())
            logger.info(f"Total questions processed: {total}")
            for category, count in processor.questions_count[chapter_num].items():
                logger.info(f"{category.capitalize()}: {count} questions")
                    
    except Exception as e:
        logger.error(f"Error processing questions: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()