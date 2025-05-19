# services/token_service.py
import tiktoken
from typing import Tuple

class TokenService:
    def __init__(self):
        # Use cl100k_base encoder which is used by many models including GPT-4
        self.encoder = tiktoken.get_encoding("cl100k_base")
        
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the text"""
        if not text:
            return 0
        
        # Convert text to tokens
        tokens = self.encoder.encode(text)
        return len(tokens)
    
    def check_input_limit(self, text: str, limit: int) -> bool:
        """Check if input is within token limit"""
        token_count = self.count_tokens(text)
        return token_count <= limit
    
    def validate_input(self, text: str, limit: int, buffer: int = 1000) -> Tuple[bool, int]:
        """Validate if input is within token limit with buffer"""
        token_count = self.count_tokens(text)
        valid = token_count <= (limit - buffer)
        return valid, token_count

# Create a singleton instance
token_service = TokenService()