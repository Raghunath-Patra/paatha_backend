# backend/config/subjects.py

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel

class SubjectType(Enum):
    SHARED = "shared"    # Shared across boards
    BOARD_SPECIFIC = "board_specific"  # Unique to a board

class ChapterMapping(BaseModel):
    source_board: str
    source_class: str
    source_subject: str

class Subject(BaseModel):
    name: str           # Display name
    code: str          # URL/directory name (e.g., 'science')
    type: SubjectType
    shared_mapping: Optional[ChapterMapping] = None  # For shared subjects
    description: Optional[str] = None
    icon: Optional[str] = None

class ClassLevel(BaseModel):
    display_name: str
    code: str          # URL/directory name
    subjects: List[Subject]

class Board(BaseModel):
    display_name: str
    code: str          # URL/directory name
    classes: Dict[str, ClassLevel]


# Update the SUBJECT_CONFIG in backend/config/subjects.py

SUBJECT_CONFIG = {
    "cbse": Board(
        display_name="CBSE",
        code="cbse",
        classes={
            # Keep existing CBSE classes
            "viii": ClassLevel(
                display_name="Class VIII",
                code="viii",
                subjects=[
                    Subject(
                        name="Science",
                        code="hesc1dd",
                        type=SubjectType.SHARED,
                    ),
                    Subject(
                        name="Mathematics",
                        code="hemh1dd",
                        type=SubjectType.SHARED,
                    )
                ]
            ),
            "ix": ClassLevel(
                display_name="Class IX",
                code="ix",
                subjects=[
                    Subject(
                        name="Science",
                        code="iesc1dd",
                        type=SubjectType.SHARED,
                    ),
                    Subject(
                        name="Mathematics",
                        code="iemh1dd",
                        type=SubjectType.SHARED,
                    )
                ]
            ),
            "x": ClassLevel(
                display_name="Class X",
                code="x",
                subjects=[
                    Subject(
                        name="Science",
                        code="jesc1dd",
                        type=SubjectType.SHARED,
                    ),
                    Subject(
                        name="Mathematics",
                        code="jemh1dd",
                        type=SubjectType.SHARED,
                    )
                ]
            ),
            # Keep existing XI and XII classes
        }
    ),
    "karnataka": Board(
        display_name="Karnataka State Board",
        code="karnataka",
        classes={
            "8th": ClassLevel(
                display_name="8th Class",
                code="8th",
                subjects=[
                    Subject(
                        name="Science",
                        code="science",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="viii",
                            source_subject="hesc1dd"
                        )
                    ),
                    Subject(
                        name="Mathematics",
                        code="mathematics",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="viii",
                            source_subject="hemh1dd"
                        )
                    )
                ]
            ),
            "9th": ClassLevel(
                display_name="9th Class",
                code="9th",
                subjects=[
                    Subject(
                        name="Science",
                        code="science",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="ix",
                            source_subject="iesc1dd"
                        )
                    ),
                    Subject(
                        name="Mathematics",
                        code="mathematics",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="ix",
                            source_subject="iemh1dd"
                        )
                    )
                ]
            ),
            "10th": ClassLevel(
                display_name="10th Class",
                code="10th",
                subjects=[
                    Subject(
                        name="Science",
                        code="science",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="x",
                            source_subject="jesc1dd"
                        )
                    ),
                    Subject(
                        name="Mathematics",
                        code="mathematics",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="x",
                            source_subject="jemh1dd"
                        )
                    )
                ]
            ),
            "puc-1": ClassLevel(
                display_name="PUC-I",
                code="puc-1",
                subjects=[
                    Subject(
                        name="Physics",
                        code="physics",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xi",
                            source_subject="keph1dd"
                        )
                    ),
                    Subject(
                        name="Chemistry",
                        code="chemistry",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xi",
                            source_subject="kech1dd"
                        )
                    ),
                    Subject(
                        name="Biology",
                        code="biology",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xi",
                            source_subject="kebo1dd"
                        )
                    ),
                    Subject(
                        name="Mathematics",
                        code="mathematics",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xi",
                            source_subject="kemh1dd"
                        )
                    )
                ]
            ),
            "puc-2": ClassLevel(
                display_name="PUC-II",
                code="puc-2",
                subjects=[
                    Subject(
                        name="Physics Part I",
                        code="physics-1",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="leph1dd"
                        )
                    ),
                    Subject(
                        name="Physics Part II",
                        code="physics-2",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="leph2dd"
                        )
                    ),
                    Subject(
                        name="Chemistry Part I",
                        code="chemistry-1",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="lech1dd"
                        )
                    ),
                    Subject(
                        name="Chemistry Part II",
                        code="chemistry-2",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="lech2dd"
                        )
                    ),
                    Subject(
                        name="Biology",
                        code="biology",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="lebo1dd"
                        )
                    ),
                    Subject(
                        name="Mathematics Part I",
                        code="mathematics-1",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="lemh1dd"
                        )
                    ),
                    Subject(
                        name="Mathematics Part II",
                        code="mathematics-2",
                        type=SubjectType.SHARED,
                        shared_mapping=ChapterMapping(
                            source_board="cbse",
                            source_class="xii",
                            source_subject="lemh2dd"
                        )
                    )
                ]
            )
        }
    )
}