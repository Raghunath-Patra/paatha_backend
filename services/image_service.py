# backend/services/image_service.py
import os
import base64
from typing import Tuple, Dict
from dotenv import load_dotenv
import openai

load_dotenv()

class ImageService:
    def __init__(self):
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
    def process_image(self, image_data: str) -> Tuple[str, Dict]:
        """Process image using GPT-4O to extract text and describe visual content in a single output"""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system", 
                        "content": """You are an AI that processes student responses from images.
                        
                        Your task is to:
                        1. Extract any handwritten text from the image in unicode format.
                        2. Identify and describe any drawings, diagrams, charts, or visual elements in detail. Use unicode text only. 
                        
                        Format your response as a single coherent description that includes both the transcribed text and descriptions of any visual elements. If there are diagrams or drawings, explicitly mention and describe them.
                        
                        Keep descriptions clear and educational, focusing on academic relevance."""
                    },
                    {
                        "role": "user", 
                        "content": [
                            {
                                "type": "text", 
                                "text": "Extract all content from this student's answer, including both handwritten text and descriptions of any drawings, diagrams, or visual elements."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_data}"
                                }
                            }
                        ]
                    }
                ]
            )
            
            # Extract text and usage statistics
            extracted_content = response.choices[0].message.content
            usage = {
                'ocr_prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                'ocr_completion_tokens': response.usage.completion_tokens if response.usage else 0,
                'ocr_total_tokens': response.usage.total_tokens if response.usage else 0
            }
            
            return extracted_content.strip(), usage
            
        except Exception as e:
            print(f"Error processing image with GPT-4O: {str(e)}")
            return "", {}

image_service = ImageService()