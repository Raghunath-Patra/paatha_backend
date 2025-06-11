#!/usr/bin/env python3
"""
Quick script to generate sections.json files for a specific subject directory.

Usage: 
    python simple_sections_generator.py questions/cbse/ix/iemh1dd
"""

import os
import json
import re
import sys
from collections import defaultdict

def main():
    # Get subject directory from command line or use default
    if len(sys.argv) > 1:
        subject_dir = sys.argv[1]
    else:
        subject_dir = input("Enter subject directory path (e.g., questions/cbse/ix/iemh1dd): ").strip()
    
    if not os.path.exists(subject_dir):
        print(f"❌ Directory not found: {subject_dir}")
        return
    
    if not os.path.exists(os.path.join(subject_dir, "chapters.json")):
        print(f"❌ No chapters.json found in {subject_dir}")
        return
    
    print(f"🔍 Processing: {subject_dir}")
    
    # Find all section files
    files = os.listdir(subject_dir)
    section_files = [f for f in files if '_section_' in f and f.endswith('_questions.json')]
    
    print(f"📁 Found {len(section_files)} section files")
    
    # Group sections by chapter
    chapters = defaultdict(list)
    
    for filename in section_files:
        # Extract chapter and section numbers
        match = re.search(r'_section_(\d+)_(\d+)_questions\.json$', filename)
        if not match:
            print(f"⚠️  Skipping: {filename} (pattern not matched)")
            continue
        
        chapter_num = int(match.group(1))
        section_num = int(match.group(2))
        
        # Read section name from first question
        try:
            with open(os.path.join(subject_dir, filename), 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            questions = data if isinstance(data, list) else data.get('questions', [])
            
            if questions:
                section_name = questions[0].get('section_name', f'Section {section_num}')
            else:
                section_name = f'Section {section_num}'
            
            chapters[chapter_num].append((section_num, section_name))
            print(f"   ✅ Chapter {chapter_num}, Section {section_num}: {section_name}")
            
        except Exception as e:
            print(f"   ❌ Error reading {filename}: {e}")
    
    # Create sections.json files
    created_count = 0
    for chapter_num, sections in chapters.items():
        # Sort sections by number
        sections.sort()
        
        # Create chapter directory
        chapter_dir = os.path.join(subject_dir, f"chapter-{chapter_num}")
        os.makedirs(chapter_dir, exist_ok=True)
        
        # Create sections.json
        sections_data = {
            "sections": [
                {"number": num, "name": name}
                for num, name in sections
            ]
        }
        
        sections_file = os.path.join(chapter_dir, "sections.json")
        with open(sections_file, 'w', encoding='utf-8') as f:
            json.dump(sections_data, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Created: {sections_file}")
        created_count += 1
    
    print(f"\n🎉 Success! Created {created_count} sections.json files")
    print(f"📂 Files created in: {subject_dir}/chapter-*/sections.json")

if __name__ == "__main__":
    main()