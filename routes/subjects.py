# backend/routes/subjects.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, List, Dict
import os
import json
from pathlib import Path

from config.database import get_db
from config.security import get_current_user
from models import User, ChapterDefinition
from sqlalchemy import text

router = APIRouter(prefix="/api", tags=["subjects"])

# Define Enum values as constants for clarity
SUBJECT_TYPE_SHARED = "SHARED"
SUBJECT_TYPE_BOARD_SPECIFIC = "BOARD_SPECIFIC"

async def get_subject_data(
    board: str,
    class_: str,
    subject_code: str,
    db: Session = Depends(get_db)
) -> Optional[dict]:
    """Get subject data, handling shared subjects appropriately"""
    try:
        print(f"\n=== Getting subject data for {board}/{class_}/{subject_code} ===")
        
        # Query the database for the subject
        query = text("""
            SELECT s.id, s.code, s.display_name, s.type, 
                   s.source_board, s.source_class, s.source_subject
            FROM subjects s
            JOIN class_levels cl ON s.class_level_id = cl.id
            JOIN boards b ON cl.board_id = b.id
            WHERE b.code = :board AND cl.code = :class AND s.code = :subject_code
            AND s.active = true AND cl.active = true AND b.active = true
        """)
        
        result = db.execute(query, {
            "board": board,
            "class": class_,
            "subject_code": subject_code
        }).fetchone()
        
        if not result:
            print(f"Subject {subject_code} not found in database")
            return None
            
        # Check if this is a shared subject
        if result.type == SUBJECT_TYPE_SHARED and result.source_board and result.source_class and result.source_subject:
            print(f"Subject type: {result.type}")
            print(f"Shared mapping: {result.source_board}/{result.source_class}/{result.source_subject}")
            
            # Try to get chapters from the file system (as before)
            # This part can eventually be moved to the database as well
            
            # Try multiple base directories in order
            base_dirs = [
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Original approach
                os.getcwd(),  # Current working directory
                "/app"  # Common path in containerized environments
            ]
            
            print(f"Trying {len(base_dirs)} possible base directories...")
            chapters_data = None
            
            for base_dir in base_dirs:
                print(f"Trying base_dir: {base_dir}")
                
                # Try to get data from the source mapping
                source_path = os.path.join(
                    base_dir,
                    "questions",
                    result.source_board,
                    result.source_class,
                    result.source_subject,
                    'chapters.json'
                )
                print(f"Checking shared content path: {source_path}")
                print(f"Path exists: {os.path.exists(source_path)}")
                
                if os.path.exists(source_path):
                    try:
                        with open(source_path, 'r') as f:
                            chapters_data = json.load(f)
                            if chapters_data:
                                print(f"Found chapters data at {source_path}")
                                break
                    except Exception as e:
                        print(f"Error reading file: {str(e)}")
            
            if chapters_data:
                # Add source information for shared subjects
                if isinstance(chapters_data, dict):
                    chapters_data['metadata'] = {
                        'source_board': result.source_board,
                        'actual_board': board,
                        'actual_class': class_,
                        'is_shared': True
                    }
                return chapters_data
        else:
            # For board-specific subjects, try the direct path
            # Try multiple base directories in order
            base_dirs = [
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Original approach
                os.getcwd(),  # Current working directory
                "/app"  # Common path in containerized environments
            ]
            
            for base_dir in base_dirs:
                board_path = os.path.join(
                    base_dir,
                    "questions",
                    board,
                    class_,
                    subject_code,
                    'chapters.json'
                )
                print(f"Checking board-specific path: {board_path}")
                print(f"Path exists: {os.path.exists(board_path)}")
                
                if os.path.exists(board_path):
                    try:
                        with open(board_path, 'r') as f:
                            chapters_data = json.load(f)
                            if chapters_data:
                                print(f"Found chapters data at {board_path}")
                                return chapters_data
                    except Exception as e:
                        print(f"Error reading file: {str(e)}")
                
        return None

    except Exception as e:
        print(f"Error in get_subject_data: {str(e)}")
        return None

@router.get("/boards")
async def get_boards(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all active boards"""
    query = text("""
        SELECT id, code, display_name
        FROM boards 
        WHERE active = true
        ORDER BY display_name
    """)
    
    result = db.execute(query).fetchall()
    
    return {
        "boards": [
            {
                "code": row.code,
                "display_name": row.display_name
            } for row in result
        ]
    }

@router.get("/boards/{board_code}/classes")
async def get_classes(
    board_code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get class levels for a board"""
    query = text("""
        SELECT cl.id, cl.code, cl.display_name
        FROM class_levels cl
        JOIN boards b ON cl.board_id = b.id
        WHERE b.code = :board_code AND cl.active = true AND b.active = true
        ORDER BY cl.display_name
    """)
    
    result = db.execute(query, {"board_code": board_code}).fetchall()
    
    return {
        "classes": [
            {
                "code": row.code,
                "display_name": row.display_name
            } for row in result
        ]
    }

@router.get("/boards/{board_code}/classes/{class_code}/subjects")
async def get_subjects_by_board_class(
    board_code: str,
    class_code: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get subjects for a board and class level"""
    query = text("""
        SELECT s.id, s.code, s.display_name, s.type, 
               s.source_board, s.source_class, s.source_subject
        FROM subjects s
        JOIN class_levels cl ON s.class_level_id = cl.id
        JOIN boards b ON cl.board_id = b.id
        WHERE b.code = :board_code AND cl.code = :class_code 
              AND s.active = true AND cl.active = true AND b.active = true
        ORDER BY s.display_name
    """)
    
    result = db.execute(query, {
        "board_code": board_code,
        "class_code": class_code
    }).fetchall()
    
    return {
        "subjects": [
            {
                "code": row.code,
                "display_name": row.display_name,
                "type": row.type,
                "source_mapping": {
                    "source_board": row.source_board,
                    "source_class": row.source_class,
                    "source_subject": row.source_subject
                } if row.source_board else None
            } for row in result
        ]
    }

@router.get("/subjects/{board}/{class_}")
async def get_subjects(
    board: str,
    class_: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all subjects for a board and class level with their chapters"""
    try:
        print(f"Fetching subjects for board: {board}, class: {class_}")
        
        # First, check if the board and class exist
        board_class_query = text("""
            SELECT cl.id
            FROM class_levels cl
            JOIN boards b ON cl.board_id = b.id
            WHERE b.code = :board AND cl.code = :class
                  AND cl.active = TRUE AND b.active = TRUE
        """)
        
        board_class_result = db.execute(board_class_query, {
            "board": board,
            "class": class_
        }).fetchone()
        
        if not board_class_result:
            raise HTTPException(status_code=404, detail="Board or class not found")
            
        # Get subjects with improved query that handles SHARED type
        subjects_query = text("""
            WITH subject_data AS (
                -- Get regular subjects
                SELECT 
                    s.id, s.code, s.display_name, s.type, 
                    NULL as mapped_board, NULL as mapped_class, NULL as mapped_subject
                FROM subjects s
                JOIN class_levels cl ON s.class_level_id = cl.id
                JOIN boards b ON cl.board_id = b.id
                WHERE b.code = :board AND cl.code = :class
                    AND s.active = TRUE AND cl.active = TRUE AND b.active = TRUE
                    AND (s.type != 'SHARED' OR s.type IS NULL)
                
                UNION ALL
                
                -- Get shared subjects with their mappings
                SELECT 
                    s.id, s.code, s.display_name, s.type,
                    s.source_board, s.source_class, s.source_subject
                FROM subjects s
                JOIN class_levels cl ON s.class_level_id = cl.id
                JOIN boards b ON cl.board_id = b.id
                WHERE b.code = :board AND cl.code = :class
                    AND s.active = TRUE AND cl.active = TRUE AND b.active = TRUE
                    AND s.type = 'SHARED'
                    AND s.source_board IS NOT NULL
                    AND s.source_class IS NOT NULL
                    AND s.source_subject IS NOT NULL
            )
            SELECT * FROM subject_data
            ORDER BY display_name
        """)
        
        subjects_result = db.execute(subjects_query, {
            "board": board,
            "class": class_
        }).fetchall()
        
        subjects = []
        
        for subject in subjects_result:
            # For SHARED subjects, fetch chapters from the source
            if subject.type == 'SHARED' and subject.mapped_board and subject.mapped_class and subject.mapped_subject:
                # Fetch chapters from the source subject
                try:
                    source_chapters = db.query(
                        ChapterDefinition.chapter_number,
                        ChapterDefinition.chapter_name
                    ).filter(
                        ChapterDefinition.board == subject.mapped_board,
                        ChapterDefinition.class_level == subject.mapped_class,
                        ChapterDefinition.subject_code == subject.mapped_subject
                    ).order_by(
                        ChapterDefinition.chapter_number
                    ).all()
                    
                    chapters_list = [
                        {"number": ch[0], "name": ch[1]} 
                        for ch in source_chapters
                    ]
                    
                    # If no chapters found in the database, try to load from file
                    if not chapters_list:
                        try:
                            # Try to load chapters from file
                            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                            file_path = os.path.join(
                                base_path,
                                "questions",
                                subject.mapped_board,
                                subject.mapped_class,
                                subject.mapped_subject,
                                "chapters.json"
                            )
                            
                            if os.path.exists(file_path):
                                with open(file_path, 'r') as f:
                                    chapters_data = json.load(f)
                                    if 'chapters' in chapters_data and isinstance(chapters_data['chapters'], list):
                                        chapters_list = chapters_data['chapters']
                        except Exception as file_err:
                            print(f"Error loading chapters from file: {str(file_err)}")
                    
                except Exception as ch_err:
                    print(f"Error fetching source chapters: {str(ch_err)}")
                    chapters_list = []
            else:
                # Get chapters for regular subjects
                chapters = db.query(
                    ChapterDefinition.chapter_number,
                    ChapterDefinition.chapter_name
                ).filter(
                    ChapterDefinition.board == board,
                    ChapterDefinition.class_level == class_,
                    ChapterDefinition.subject_code == subject.code
                ).order_by(
                    ChapterDefinition.chapter_number
                ).all()
                
                chapters_list = [
                    {"number": ch[0], "name": ch[1]} 
                    for ch in chapters
                ]
                
                # If no chapters in database, try to load from file
                if not chapters_list:
                    try:
                        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        file_path = os.path.join(
                            base_path,
                            "questions",
                            board,
                            class_,
                            subject.code,
                            "chapters.json"
                        )
                        
                        if os.path.exists(file_path):
                            with open(file_path, 'r') as f:
                                chapters_data = json.load(f)
                                if 'chapters' in chapters_data and isinstance(chapters_data['chapters'], list):
                                    chapters_list = chapters_data['chapters']
                    except Exception as file_err:
                        print(f"Error loading chapters from file: {str(file_err)}")
            
            # Add logging to debug chapter loading
            print(f"Subject {subject.display_name} ({subject.code}): Found {len(chapters_list)} chapters")
            
            # Create subject data structure
            subject_data = {
                "name": subject.display_name,
                "code": subject.code,
                "chapters": chapters_list
            }
            
            subjects.append(subject_data)
        
        return {"subjects": subjects}
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error getting subjects: {str(e)}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching subjects: {str(e)}"
        )