#!/usr/bin/env python3

import os
import sys
import json
import argparse
import logging
import shutil
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def contains_latex(text: str) -> bool:
    """Check if text contains any LaTeX markers"""
    latex_patterns = [
        r'\\text\{',      # \text command
        r'\\times',       # \times command
        r'\\frac',        # \frac command
        r'\\[a-zA-Z]+{',  # Other commands with braces
        r'\\[a-zA-Z]+\[', # Commands with square brackets
        r'\\[()]',        # Delimiters
        r'\\rightarrow',  # Specific commands
        r'_[0-9]',        # Subscripts
        r'\^[0-9]',       # Superscripts
        r'\\left',        # \left command
        r'\\right',       # \right command
        r'\\begin',       # \begin command
        r'\\end',         # \end command
        r'\\sqrt',        # \sqrt command
        r'\\Delta',       # \Delta command
        r'\\sum',         # \sum command
        r'\\int'          # \int command
    ]
    
    if not isinstance(text, str):
        return False
        
    for pattern in latex_patterns:
        if re.search(pattern, text):
            return True
    return False

class JSONChemCleaner:
    def __init__(self):
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def clean_question(self, question: dict, index: int) -> dict:
        """Clean a single question using the GPT-4 model"""
        # Check if any field contains LaTeX
        needs_cleaning = False
        for field in ['question_text', 'correct_answer', 'explanation']:
            if field in question and contains_latex(question.get(field, '')):
                needs_cleaning = True
                break
        
        if not needs_cleaning:
            logger.info(f"Question {index + 1} contains no LaTeX, skipping...")
            return question
            
        print(f"\n{'='*80}\nProcessing Question {index + 1}")
        print(f"Original question:\n{json.dumps(question, ensure_ascii=False, indent=2)}")
        input("Press Enter to process this question...")
        
        logger.debug(f"Sending question {index + 1} to GPT-4o-mini")
        
        # Convert the question dict to a JSON string
        input_json = json.dumps(question, ensure_ascii=False)
        
        prompt = f"""Format this in unicode only, without using latex. Keep all fields and content exactly the same, just convert any LaTeX notation to unicode characters.

    Example Input 1:
    {{
    "question_text": "\\( \\text{{CH}}_4 + \\text{{O}}_2 \\rightarrow \\text{{CO}}_2 + \\text{{H}}_2\\text{{O}} \\)"
    }}

    Example Output:
    {{
    "question_text": "CH₄ + O₂ → CO₂ + H₂O"
    }}

    Example Input 2:  frac{{9l}}{{A}}, Example output 2: (9l / A). 
    Example Input 3:  \\( V_1 = 2\\,\\text{{V}} \\), \\( V_2 = 3\\,\\text{{V}} \\), Example Output 3: V₁ = 2 V, V₂ = 3 V.
    Example Input 4: \( R_s = 15\,Ω + 5\,Ω = 20\,Ω \),  Example Output 4: Rs = 15 Ω + 5 Ω = 20 Ω.
    {input_json}

    Return ONLY the cleaned JSON object with all fields preserved, exactly as in the input but with LaTeX converted to unicode."""

        try:
            print(prompt)
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )
            
            if not hasattr(response, 'choices') or not response.choices:
                logger.error("No choices in API response")
                return question
                
            cleaned_text = response.choices[0].message.content.strip()
            logger.debug(f"Raw API response:\n{cleaned_text}")
            
            # Try to find JSON in the response if it's not pure JSON
            json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
            if not json_match:
                logger.error(f"Could not find JSON object in response. Full response:\n{cleaned_text}")
                return question
                
            json_str = json_match.group(0)
            logger.debug(f"Extracted JSON string:\n{json_str}")
            
            try:
                cleaned_question = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                logger.error(f"Failed to parse JSON:\n{json_str}")
                return question
                
            # Verify that all original keys are present
            missing_keys = [key for key in question.keys() if key not in cleaned_question]
            if missing_keys:
                logger.error(f"Missing keys in cleaned question: {missing_keys}")
                return question
            
            print(f"\nCleaned question:\n{json.dumps(cleaned_question, ensure_ascii=False, indent=2)}")
            return cleaned_question
                
        except Exception as e:
            logger.error(f"Error cleaning question: {str(e)}")
            logger.error(f"Error occurred while processing:\n{json.dumps(question, ensure_ascii=False, indent=2)}")
            return question
        
    def process_file(self, file_path: Path) -> None:
        """Process a single JSON file"""
        try:
            logger.info(f"Processing {file_path}")
            
            # Create backup with -old suffix
            backup_path = file_path.with_suffix('.json-old')
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup at {backup_path}")
            
            # Read and parse the JSON file
            with open(file_path, 'r', encoding='utf-8') as f:
                questions = json.load(f)
                
            if not questions:
                logger.warning(f"No questions found in {file_path}")
                return
                
            logger.info(f"Found {len(questions)} questions in {file_path}")
            
            # Process questions sequentially
            cleaned_questions = []
            for i, question in enumerate(questions):
                cleaned_question = self.clean_question(question, i)
                cleaned_questions.append(cleaned_question)

            # Save cleaned questions
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(cleaned_questions, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved cleaned questions to {file_path}")
            except Exception as e:
                logger.error(f"Error saving cleaned questions: {str(e)}")
                # Try to restore from backup
                shutil.copy2(backup_path, file_path)
                logger.info(f"Restored original file from backup")
                raise
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")

    def process_chapter(self, chapter_dir: str, specific_file: str = None) -> None:
        """Process all JSON files in a specific chapter folder or a specific file"""
        chapter_path = Path(chapter_dir)
        if not chapter_path.exists():
            raise ValueError(f"Chapter directory not found: {chapter_dir}")
            
        try:
            if specific_file:
                file_path = chapter_path / specific_file
                if not file_path.exists():
                    raise ValueError(f"File not found: {file_path}")
                if not file_path.name.endswith('-old.json'):  # Skip backup files
                    self.process_file(file_path)
            else:
                # Process all JSON files in the chapter
                for file_path in chapter_path.glob('*.json'):
                    if not file_path.name.endswith('-old.json'):  # Skip backup files
                        self.process_file(file_path)
                
        except Exception as e:
            logger.error(f"Error processing chapter {chapter_dir}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Clean chemistry equations in JSON files using GPT-4')
    parser.add_argument('chapter', type=str, help='Chapter to process (e.g., jesc101)')
    parser.add_argument('file', type=str, nargs='?', help='Specific file to process (optional)')
    args = parser.parse_args()

    base_path = Path("backend/questions/cbse/x/science")
    chapter_dir = base_path / args.chapter
    
    if not chapter_dir.exists():
        logger.error(f"Chapter directory not found: {chapter_dir}")
        sys.exit(1)
        
    cleaner = JSONChemCleaner()
    
    try:
        logger.info(f"Processing chapter: {args.chapter}")
        cleaner.process_chapter(str(chapter_dir), args.file)
    except Exception as e:
        logger.error(f"Error processing questions: {e}")
        raise

if __name__ == "__main__":
    main()