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
                                "text": "Extract all content from this student's answer, including both handwritten text and descriptions of any drawings, or diagrams."
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
            
            # Extract text content
            extracted_content = ""
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message') and response.choices[0].message:
                    extracted_content = response.choices[0].message.content or ""
            
            # Extract usage statistics safely
            usage = {
                'ocr_prompt_tokens': 0,
                'ocr_completion_tokens': 0,
                'ocr_total_tokens': 0
            }
            
            try:
                if hasattr(response, 'usage') and response.usage:
                    usage['ocr_prompt_tokens'] = getattr(response.usage, 'prompt_tokens', 0)
                    usage['ocr_completion_tokens'] = getattr(response.usage, 'completion_tokens', 0)
                    usage['ocr_total_tokens'] = getattr(response.usage, 'total_tokens', 0)
            except Exception as usage_error:
                print(f"Warning: Could not extract usage statistics: {str(usage_error)}")
            
            return extracted_content.strip(), usage
            
        except Exception as e:
            print(f"Error processing image with GPT-4O: {str(e)}")
            print(f"Error type: {type(e)}")
            import traceback
            print(f"Full traceback: {traceback.format_exc()}")
            return "", {}

image_service = ImageService()