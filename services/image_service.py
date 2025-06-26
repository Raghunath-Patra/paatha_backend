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
            
            # Extract text content
            extracted_content = ""
            if response.choices and len(response.choices) > 0:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    extracted_content = response.choices[0].message.content or ""
                elif isinstance(response.choices[0], dict):
                    message = response.choices[0].get('message', {})
                    extracted_content = message.get('content', '') if isinstance(message, dict) else ""
            
            # Extract usage statistics - handle both object and dict formats
            usage = {
                'ocr_prompt_tokens': 0,
                'ocr_completion_tokens': 0,
                'ocr_total_tokens': 0
            }
            
            if hasattr(response, 'usage') and response.usage:
                usage_data = response.usage
                
                # Handle both object attributes and dictionary access
                if hasattr(usage_data, 'prompt_tokens'):
                    # Object with attributes
                    usage['ocr_prompt_tokens'] = usage_data.prompt_tokens or 0
                    usage['ocr_completion_tokens'] = usage_data.completion_tokens or 0
                    usage['ocr_total_tokens'] = usage_data.total_tokens or 0
                elif isinstance(usage_data, dict):
                    # Dictionary format
                    usage['ocr_prompt_tokens'] = usage_data.get('prompt_tokens', 0)
                    usage['ocr_completion_tokens'] = usage_data.get('completion_tokens', 0)
                    usage['ocr_total_tokens'] = usage_data.get('total_tokens', 0)
            
            return extracted_content.strip(), usage
            
        except Exception as e:
            print(f"Error processing image with GPT-4O: {str(e)}")
            # Log more details for debugging
            print(f"Error type: {type(e)}")
            print(f"Error args: {e.args}")
            return "", {}

image_service = ImageService()