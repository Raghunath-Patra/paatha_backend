#!/usr/bin/env python3

import os
import sys
import json
import argparse
import logging
from pathlib import Path
import re
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QuestionCleaner:
    def __init__(self):
        load_dotenv()
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def clean_json_text(self, text: str) -> str:
        """Clean text content to be valid JSON"""
        text = text.replace('\\"', '"')
        text = re.sub(r'\\[a-zA-Z]+', lambda m: '\\\\' + m.group(0)[1:], text)
        text = text.replace('\\', '\\\\')
        text = text.replace('"', '\\"')
        text = text.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
        return text

    def extract_json_from_markdown(self, content: str) -> List[Dict]:
        """Extract JSON content from markdown file"""
        questions = []
        json_blocks = re.finditer(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        
        for block in json_blocks:
            try:
                raw_json = block.group(1).strip()
                try:
                    questions_data = json.loads(raw_json)
                except json.JSONDecodeError:
                    # Handle malformed JSON
                    json_str = '['
                    lines = raw_json.split('\n')
                    in_question = False
                    question_lines = []
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                            
                        if line.startswith('['):
                            continue
                        elif line.startswith(']'):
                            if question_lines:
                                question_text = ''.join(question_lines)
                                question_text = self.clean_json_text(question_text)
                                json_str += question_text.rstrip(',') + ']'
                                break
                        elif line.startswith('{'):
                            if in_question:
                                question_text = ''.join(question_lines)
                                question_text = self.clean_json_text(question_text)
                                json_str += question_text + ','
                                question_lines = []
                            in_question = True
                            question_lines.append(line)
                        elif in_question:
                            question_lines.append(line)
                    
                    try:
                        questions_data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse processed JSON: {str(e)}")
                        continue
                
                if isinstance(questions_data, list):
                    questions.extend(questions_data)
                else:
                    questions.append(questions_data)
                    
            except Exception as e:
                logger.error(f"Error processing JSON block: {str(e)}")
                continue
                
        return questions

    def clean_question(self, question: Dict) -> Dict:
        """Clean a single question using the GPT-4 model"""
        prompt = """Please clean and format this chemistry question according to these rules:

1. Remove ALL markdown formatting (###, ##, etc) and question numbers (1., 2., etc) from the start of questions
2. Do not change the answer logic, only its formatting
3. Format multiple questions as bullet points with "-" prefix
4. Convert ALL LaTeX chemical equations to plain text with proper subscripts and arrows:
   - Convert \( 2HNO_3 + Ca(OH)_2 \) to 2HNO₃ + Ca(OH)₂
   - Convert \text{Na(s)} to Na(s)  
   - Convert \rightarrow to →
5. Remove ALL LaTeX delimiters (\[, \], \(, \))
6. Format subquestions with bullet points
7. Keep subscripts (₁, ₂, ₃, ₄) and superscripts (⁰, ¹, ², ³) 
8. Maintain the original JSON structure - VERY IMPORTANT: Return the complete JSON object

IMPORTANT: Your response must be a valid JSON object with all the original fields.

Examples of proper formatting:

Input question text:
"### 3. A solution of substance 'X' is used..."
Should become:
"A solution of substance 'X' is used..."

Input chemical equation:
"\[ 4\text{Na(s)} + \text{O}_2\text{(g)} \rightarrow 2\text{Na}_2\text{O(s)} \]"  
Should become:
"4Na(s) + O₂(g) → 2Na₂O(s)"

Input multiple questions:
"1. Name substance X
2. Write its formula"
Should become:
"- Name substance X
- Write its formula"

Original JSON:
{input_text}

Return ONLY the cleaned JSON object with all fields preserved."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that cleans and formats chemistry questions. Always return valid JSON."},
                    {"role": "user", "content": prompt.format(input_text=json.dumps(question, ensure_ascii=False, indent=2))}
                ],
                temperature=0.3
            )
            
            cleaned_text = response.choices[0].message.content
            
            # Try to find JSON in the response if it's not pure JSON
            json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
            if json_match:
                cleaned_text = json_match.group(0)
            
            try:
                cleaned_question = json.loads(cleaned_text)
                # Verify that all original keys are present
                if not all(key in cleaned_question for key in question.keys()):
                    logger.error(f"Missing keys in cleaned question. Original keys: {question.keys()}, Cleaned keys: {cleaned_question.keys()}")
                    return question
                return cleaned_question
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse model response as JSON: {cleaned_text[:200]}...")
                logger.error(f"JSON error: {str(e)}")
                return question
                
        except Exception as e:
            logger.error(f"Error cleaning question: {str(e)}")
            logger.error(f"Full error: {type(e).__name__}: {str(e)}")
            return question

    def process_file(self, file_path: Path) -> None:
        """Process a single question file"""
        try:
            logger.info(f"Processing {file_path}")
            
            # Read and parse the markdown file
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
                
            questions = self.extract_json_from_markdown(content)
            if not questions:
                logger.warning(f"No valid questions found in {file_path}")
                return
                
            # Clean questions in parallel
            with ThreadPoolExecutor(max_workers=5) as executor:
                cleaned_questions = list(tqdm(
                    executor.map(self.clean_question, questions),
                    total=len(questions),
                    desc="Cleaning questions"
                ))
            
            # Save cleaned questions
            output_path = file_path.with_suffix('.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned_questions, f, ensure_ascii=False, indent=2)
                
            logger.info(f"Saved cleaned questions to {output_path}")
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {str(e)}")

    def process_chapter(self, chapter_dir: str) -> None:
        """Process all questions in a specific chapter folder"""
        chapter_path = Path(chapter_dir)
        if not chapter_path.exists():
            raise ValueError(f"Chapter directory not found: {chapter_dir}")
            
        try:
            # Process all markdown files in the chapter
            for file_path in chapter_path.glob('*.md'):
                self.process_file(file_path)
                
        except Exception as e:
            logger.error(f"Error processing chapter {chapter_dir}: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description='Clean question files using GPT-4')
    parser.add_argument('chapter', type=str, help='Chapter to process (e.g., jesc101)')
    args = parser.parse_args()

    base_path = Path("backend/questions/cbse/x/science")
    chapter_dir = base_path / args.chapter
    
    if not chapter_dir.exists():
        logger.error(f"Chapter directory not found: {chapter_dir}")
        sys.exit(1)
        
    cleaner = QuestionCleaner()
    
    try:
        logger.info(f"Processing chapter: {args.chapter}")
        cleaner.process_chapter(str(chapter_dir))
    except Exception as e:
        logger.error(f"Error processing questions: {e}")
        raise

if __name__ == "__main__":
    main()