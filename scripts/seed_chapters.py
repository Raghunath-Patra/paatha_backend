#!/usr/bin/env python3

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from models import ChapterDefinition
from config.database import SessionLocal
import uuid
from config.subjects import SUBJECT_CONFIG, SubjectType

def extract_chapter_names_from_files():
    """Extract chapter names from chapters.json files in questions directory"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    questions_dir = os.path.join(base_dir, "questions")
    
    print(f"Looking for chapters in: {questions_dir}")
    if not os.path.exists(questions_dir):
        print(f"ERROR: Questions directory not found at: {questions_dir}")
        return []
    
    chapter_data = []
    
    # Walk through board/class/subject directories
    for board in os.listdir(questions_dir):
        board_path = os.path.join(questions_dir, board)
        if not os.path.isdir(board_path):
            continue
            
        print(f"Checking board: {board}")
        for class_level in os.listdir(board_path):
            class_path = os.path.join(board_path, class_level)
            if not os.path.isdir(class_path):
                continue
                
            print(f"  Checking class: {class_level}")
            for subject in os.listdir(class_path):
                subject_path = os.path.join(class_path, subject)
                if not os.path.isdir(subject_path):
                    continue
                
                print(f"    Checking subject: {subject}")
                # Look for chapters.json file
                chapters_file = os.path.join(subject_path, 'chapters.json')
                print(f"    Looking for: {chapters_file}")
                
                if not os.path.exists(chapters_file):
                    print(f"    WARNING: chapters.json not found for {board}/{class_level}/{subject}")
                    continue
                
                try:
                    with open(chapters_file, 'r', encoding='utf-8') as f:
                        print(f"    Reading: {chapters_file}")
                        chapters_json = json.load(f)
                        
                    # Extract chapters from file
                    if 'chapters' in chapters_json and isinstance(chapters_json['chapters'], list):
                        for chapter in chapters_json['chapters']:
                            if 'number' in chapter and 'name' in chapter:
                                entry = {
                                    "board": board,
                                    "class_level": class_level,
                                    "subject_code": subject,
                                    "chapter_number": chapter['number'],
                                    "chapter_name": chapter['name']
                                }
                                chapter_data.append(entry)
                                print(f"      Found chapter: {board}/{class_level}/{subject} - {chapter['number']}: {chapter['name']}")
                    else:
                        print(f"    WARNING: Invalid format in {chapters_file}, no 'chapters' list found")
                        print(f"    File content: {json.dumps(chapters_json, indent=2)[:200]}...")
                except Exception as e:
                    print(f"    ERROR reading chapters file {chapters_file}: {str(e)}")
    
    print(f"Total chapters found: {len(chapter_data)}")
    return chapter_data

def seed_chapters(dry_run=False):
    """Seed chapter definitions into database"""
    # Extract chapter information from files
    file_based_chapters = extract_chapter_names_from_files()
    print(f"Extracted {len(file_based_chapters)} chapters from files")
    
    if dry_run:
        print("DRY RUN: Would insert these chapters into database:")
        for ch in file_based_chapters:
            print(f"  {ch['board']}/{ch['class_level']}/{ch['subject_code']} - Chapter {ch['chapter_number']}: {ch['chapter_name']}")
        return
    
    # If not a dry run, proceed with database operations
    db = SessionLocal()
    try:
        # Check if we already have data
        existing_count = db.query(ChapterDefinition).count()
        print(f"Found {existing_count} existing chapter definitions in database")
        
        # Create chapter definitions
        chapters = []
        for data in file_based_chapters:
            # Check if this chapter already exists
            existing = db.query(ChapterDefinition).filter(
                ChapterDefinition.board == data["board"],
                ChapterDefinition.class_level == data["class_level"],
                ChapterDefinition.subject_code == data["subject_code"],
                ChapterDefinition.chapter_number == data["chapter_number"]
            ).first()
            
            if existing:
                print(f"Chapter already exists: {data['board']}/{data['class_level']}/{data['subject_code']} - {data['chapter_number']}")
                continue
            
            chapter = ChapterDefinition(
                id=uuid.uuid4(),
                board=data["board"],
                class_level=data["class_level"],
                subject_code=data["subject_code"],
                chapter_number=data["chapter_number"],
                chapter_name=data["chapter_name"]
            )
            chapters.append(chapter)
        
        # Insert chapters in batches
        if chapters:
            batch_size = 50
            for i in range(0, len(chapters), batch_size):
                batch = chapters[i:i+batch_size]
                db.add_all(batch)
                db.commit()
                print(f"Inserted chapters {i+1} to {i+len(batch)}")
            
            print(f"Successfully seeded {len(chapters)} chapter definitions")
        else:
            print("No new chapters to insert")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding chapters: {str(e)}")
    finally:
        db.close()
        
if __name__ == "__main__":
    # Add a command-line flag to do a dry run (print chapters but don't insert)
    if len(sys.argv) > 1 and sys.argv[1] == '--dry-run':
        seed_chapters(dry_run=True)
    else:
        seed_chapters()