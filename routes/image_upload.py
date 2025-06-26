# backend/api/student/image_upload.py
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer
import base64
import io
import logging
import traceback
from PIL import Image
from services.image_service import image_service
from config.database import get_db
from config.security import get_current_user
from models import User

router = APIRouter(prefix="/api/student", tags=["student-image-upload"])
security = HTTPBearer()
logger = logging.getLogger(__name__)

def validate_and_prepare_image(contents: bytes) -> str:
    """Validate image and prepare base64 string for processing"""
    try:
        # Validate that it's a valid image
        image = Image.open(io.BytesIO(contents))
        
        # Convert to RGB if necessary (for JPEG compatibility)
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        
        # Resize if too large (max 2048px on longest side for better processing)
        max_dimension = 2048
        if max(image.width, image.height) > max_dimension:
            ratio = max_dimension / max(image.width, image.height)
            new_width = int(image.width * ratio)
            new_height = int(image.height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.info(f"Resized image from original to {new_width}x{new_height}")
        
        # Convert to JPEG format for consistency
        img_buffer = io.BytesIO()
        image.save(img_buffer, format='JPEG', quality=85)
        img_buffer.seek(0)
        
        # Encode to base64
        image_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        return image_base64
        
    except Exception as e:
        logger.error(f"Error validating/preparing image: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid image file: {str(e)}"
        )

@router.post("/process-image")
async def process_image_for_text(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Process an uploaded image to extract text and visual descriptions
    """
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400, 
                detail="File must be an image (JPEG, PNG, WebP, or GIF)"
            )
        
        # Read and validate file size (limit to 10MB)
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Empty file uploaded")
            
        if len(contents) > 10 * 1024 * 1024:  # 10MB limit
            raise HTTPException(
                status_code=400, 
                detail="Image file too large (maximum 10MB allowed)"
            )
        
        # Validate and prepare image
        try:
            image_base64 = validate_and_prepare_image(contents)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error preparing image: {str(e)}")
            raise HTTPException(
                status_code=400, 
                detail="Failed to process image file. Please ensure it's a valid image."
            )
        
        # Process image using the image service
        try:
            extracted_text, usage_stats = image_service.process_image(image_base64)
            
            # Ensure we have valid data types
            if not isinstance(extracted_text, str):
                extracted_text = str(extracted_text) if extracted_text else ""
                
            if not isinstance(usage_stats, dict):
                usage_stats = {}
            
            # Handle case where no text was extracted
            if not extracted_text or extracted_text.strip() == "":
                extracted_text = "No text or readable content could be extracted from this image. The image may be too blurry, contain no text, or the handwriting may be unclear."
            
            logger.info(f"Image processed successfully for user {current_user.id}. "
                       f"Extracted {len(extracted_text)} characters. "
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
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Check if it's an API-related error
            if "API" in str(e) or "openai" in str(e).lower():
                raise HTTPException(
                    status_code=503, 
                    detail="AI service temporarily unavailable. Please try again in a moment."
                )
            else:
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to extract text from image. Please try with a clearer image."
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in image processing: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred while processing the image"
        )

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
        if "image" not in image_data:
            raise HTTPException(
                status_code=400, 
                detail="Missing 'image' field in request body"
            )
        
        base64_string = image_data["image"]
        
        if not base64_string or base64_string.strip() == "":
            raise HTTPException(
                status_code=400, 
                detail="Empty image data provided"
            )
        
        # Remove data URL prefix if present and clean the string
        if base64_string.startswith('data:image'):
            if ',' in base64_string:
                base64_string = base64_string.split(',')[1]
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid data URL format"
                )
        
        # Clean any whitespace
        base64_string = base64_string.strip()
        
        # Validate base64 format and decode
        try:
            image_bytes = base64.b64decode(base64_string)
            if len(image_bytes) == 0:
                raise HTTPException(
                    status_code=400, 
                    detail="Empty image data after decoding"
                )
                
            if len(image_bytes) > 10 * 1024 * 1024:  # 10MB limit
                raise HTTPException(
                    status_code=400, 
                    detail="Image too large (maximum 10MB allowed)"
                )
            
        except base64.binascii.Error as e:
            logger.error(f"Base64 decode error: {str(e)}")
            raise HTTPException(
                status_code=400, 
                detail="Invalid base64 image data format"
            )
        except ValueError as e:
            logger.error(f"Base64 validation error: {str(e)}")
            raise HTTPException(
                status_code=400, 
                detail="Invalid base64 image data"
            )
        
        # Validate and prepare the image
        try:
            final_base64 = validate_and_prepare_image(image_bytes)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error preparing base64 image: {str(e)}")
            raise HTTPException(
                status_code=400, 
                detail="Invalid image data. Please capture a new image."
            )
        
        # Process with image service
        try:
            extracted_text, usage_stats = image_service.process_image(final_base64)
            
            # Ensure we have valid data types
            if not isinstance(extracted_text, str):
                extracted_text = str(extracted_text) if extracted_text else ""
                
            if not isinstance(usage_stats, dict):
                usage_stats = {}
            
            # Handle case where no text was extracted
            if not extracted_text or extracted_text.strip() == "":
                extracted_text = "No text or readable content could be extracted from this image. Please try taking a clearer photo with better lighting."
            
            logger.info(f"Base64 image processed successfully for user {current_user.id}. "
                       f"Extracted {len(extracted_text)} characters. "
                       f"Tokens used: {usage_stats.get('ocr_total_tokens', 0)}")
            
            return {
                "success": True,
                "extracted_text": extracted_text,
                "usage_stats": usage_stats,
                "message": "Image processed successfully"
            }
            
        except Exception as e:
            logger.error(f"Error in image service for base64: {str(e)}")
            logger.error(f"Error type: {type(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Check if it's an API-related error
            if "API" in str(e) or "openai" in str(e).lower():
                raise HTTPException(
                    status_code=503, 
                    detail="AI service temporarily unavailable. Please try again in a moment."
                )
            else:
                raise HTTPException(
                    status_code=500, 
                    detail="Failed to extract text from image. Please try with a clearer image."
                )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in base64 image processing: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="An unexpected error occurred while processing the image"
        )