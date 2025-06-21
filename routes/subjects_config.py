# Add this to main.py or create a new routes/subjects_config.py file

from fastapi import APIRouter, Depends,  HTTPException, status
from config.subjects import SUBJECT_CONFIG, SubjectType
from config.security import get_current_user
from typing import Dict, List, Optional
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

# If creating a separate file, use this router
router = APIRouter(prefix="/api", tags=["subjects-config"])

# Pydantic models for response structure
class SubjectInfo(BaseModel):
    code: str
    name: str
    display_name: str
    type: str  # 'REGULAR' or 'SHARED'
    shared_mapping: Optional[Dict[str, str]] = None

class ClassInfo(BaseModel):
    code: str
    display_name: str
    subjects: List[SubjectInfo]

class BoardInfo(BaseModel):
    code: str
    display_name: str
    classes: Dict[str, ClassInfo]

class SubjectsConfigResponse(BaseModel):
    boards: Dict[str, BoardInfo]

# If adding to main.py, use @app.get
# If using separate file, use @router.get
@router.get("/api/subjects-config", response_model=SubjectsConfigResponse)
async def get_subjects_configuration(
    current_user: Dict = Depends(get_current_user)
):
    """
    Get complete subjects configuration including boards, classes, and subjects.
    This endpoint reads from config/subjects.py and provides the full hierarchy.
    """
    try:
        boards_dict = {}
        
        # Iterate through the SUBJECT_CONFIG
        for board_code, board_config in SUBJECT_CONFIG.items():
            classes_dict = {}
            
            # Iterate through classes in each board
            for class_code, class_config in board_config.classes.items():
                subjects_list = []
                
                # Iterate through subjects in each class
                for subject in class_config.subjects:
                    subject_info = SubjectInfo(
                        code=subject.code,
                        name=subject.name,
                        display_name=subject.display_name,
                        type=subject.type.value if hasattr(subject.type, 'value') else str(subject.type)
                    )
                    
                    # Add shared mapping if it's a shared subject
                    if subject.type == SubjectType.SHARED and subject.shared_mapping:
                        subject_info.shared_mapping = {
                            "source_board": subject.shared_mapping.source_board,
                            "source_class": subject.shared_mapping.source_class,
                            "source_subject": subject.shared_mapping.source_subject
                        }
                    
                    subjects_list.append(subject_info)
                
                classes_dict[class_code] = ClassInfo(
                    code=class_code,
                    display_name=class_config.display_name,
                    subjects=subjects_list
                )
            
            boards_dict[board_code] = BoardInfo(
                code=board_code,
                display_name=board_config.display_name,
                classes=classes_dict
            )
        
        return SubjectsConfigResponse(boards=boards_dict)
        
    except Exception as e:
        logger.error(f"Error getting subjects configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting subjects configuration: {str(e)}"
        )

# Additional endpoint for just getting available subjects for a specific board/class
@router.get("/api/subjects/{board}/{class_level}")
async def get_subjects_for_class(
    board: str,
    class_level: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get available subjects for a specific board and class"""
    try:
        board_lower = board.lower()
        class_lower = class_level.lower()
        
        if board_lower not in SUBJECT_CONFIG:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Board '{board}' not found"
            )
        
        board_config = SUBJECT_CONFIG[board_lower]
        
        if class_lower not in board_config.classes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Class '{class_level}' not found for board '{board}'"
            )
        
        class_config = board_config.classes[class_lower]
        
        subjects = []
        for subject in class_config.subjects:
            subject_info = {
                "code": subject.code,
                "name": subject.name,
                "display_name": subject.display_name,
                "type": subject.type.value if hasattr(subject.type, 'value') else str(subject.type)
            }
            
            if subject.type == SubjectType.SHARED and subject.shared_mapping:
                subject_info["shared_mapping"] = {
                    "source_board": subject.shared_mapping.source_board,
                    "source_class": subject.shared_mapping.source_class,
                    "source_subject": subject.shared_mapping.source_subject
                }
            
            subjects.append(subject_info)
        
        return {
            "board": {
                "code": board_lower,
                "display_name": board_config.display_name
            },
            "class": {
                "code": class_lower,
                "display_name": class_config.display_name
            },
            "subjects": subjects
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting subjects for {board}/{class_level}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting subjects: {str(e)}"
        )

# Endpoint to get just the boards (simpler version)
@router.get("/api/boards-simple")
async def get_boards_simple(
    current_user: Dict = Depends(get_current_user)
):
    """Get simplified list of available boards"""
    try:
        boards = []
        for board_code, board_config in SUBJECT_CONFIG.items():
            boards.append({
                "code": board_code,
                "display_name": board_config.display_name,
                "classes_count": len(board_config.classes)
            })
        
        return {"boards": boards}
        
    except Exception as e:
        logger.error(f"Error getting boards: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting boards: {str(e)}"
        )

# Endpoint to get classes for a specific board
@router.get("/api/classes/{board}")
async def get_classes_for_board(
    board: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get available classes for a specific board"""
    try:
        board_lower = board.lower()
        
        if board_lower not in SUBJECT_CONFIG:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Board '{board}' not found"
            )
        
        board_config = SUBJECT_CONFIG[board_lower]
        
        classes = []
        for class_code, class_config in board_config.classes.items():
            classes.append({
                "code": class_code,
                "display_name": class_config.display_name,
                "subjects_count": len(class_config.subjects)
            })
        
        return {
            "board": {
                "code": board_lower,
                "display_name": board_config.display_name
            },
            "classes": classes
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error getting classes for board {board}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting classes: {str(e)}"
        )