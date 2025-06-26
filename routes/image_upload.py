# backend/api/student/image_upload.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer
import base64
import io
from PIL import Image
import logging
from services.quiz_image_service import image_service
from config.database import get_db
from config.security import get_current_user
from models import User

router = APIRouter(prefix="/api/student", tags=["student-image-upload"])
security = HTTPBearer()
logger = logging.getLogger(__name__)

def get_user_id(current_user):
    """Helper function to get user ID from current_user (handles both dict and object)"""
    if isinstance(current_user, dict):
        return current_user.get('id') or current_user.get('user_id')
    else:
        return getattr(current_user, 'id', None)

@router.post("/process-image")
async def process_image_for_text(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Process an uploaded image to extract text and visual descriptions
    """
    try:
        # Get user ID safely
        user_id = get_user_id(current_user)
        
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read and validate file size (limit to 10MB)
        contents = await file.read()
        if len(contents) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(status_code=400, detail="Image file too large (max 10MB)")
        
        # Convert to base64 for OpenAI API
        try:
            # Validate that it's a valid image
            image = Image.open(io.BytesIO(contents))
            
            # Convert to RGB if necessary (for JPEG compatibility)
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            
            # Convert to JPEG format for consistency
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=85)
            img_buffer.seek(0)
            
            # Encode to base64
            image_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # Process image using the image service
        try:
            extracted_text, usage_stats = image_service.process_image(image_base64)
            
            if not extracted_text:
                extracted_text = "No text or content could be extracted from this image."
            
            logger.info(f"Image processed successfully for user {user_id}. "
                       f"Tokens used: {usage_stats.get('ocr_total_tokens', 0)}")
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "usage_stats": usage_stats,
                "message": "Image processed successfully"
            }
            
        except Exception as e:
            logger.error(f"Error in image service: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Traceback: ", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to process image. Please try again or contact support."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in image processing: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Traceback: ", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

@router.post("/process-image-base64")
async def process_image_from_base64(
    image_data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Process a base64 encoded image (useful for camera captures)
    Expected format: {"image": "base64_string_without_data_prefix"}
    """
    try:
        # Get user ID safely
        user_id = get_user_id(current_user)
        
        if "image" not in image_data:
            raise HTTPException(status_code=400, detail="Missing 'image' field in request")
        
        base64_string = image_data["image"]
        
        # Remove data URL prefix if present
        if base64_string.startswith('data:image'):
            base64_string = base64_string.split(',')[1]
        
        # Validate base64 format
        try:
            image_bytes = base64.b64decode(base64_string)
            if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
                raise HTTPException(status_code=400, detail="Image too large (max 10MB)")
            
            # Validate it's a valid image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            
            # Re-encode as JPEG for consistency
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=85)
            img_buffer.seek(0)
            
            # Get final base64
            final_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error decoding base64 image: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        
        # Process with image service
        try:
            extracted_text, usage_stats = image_service.process_image(final_base64)
            
            if not extracted_text:
                extracted_text = "No text or content could be extracted from this image."
            
            logger.info(f"Base64 image processed successfully for user {user_id}. "
                       f"Tokens used: {usage_stats.get('ocr_total_tokens', 0)}")
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "usage_stats": usage_stats,
                "message": "Image processed successfully"
            }
            
        except Exception as e:
            logger.error(f"Error in image service: {str(e)}")
            logger.error(f"Error type: {type(e)}")  
            logger.error(f"Traceback: ", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail="Failed to process image. Please try again."
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in base64 image processing: {str(e)}")
        logger.error(f"Error type: {type(e)}")
        logger.error(f"Traceback: ", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")