from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user, verify_service_auth
import httpx
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-generation"])

VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://localhost:8001")  # Your video service URL

@router.post("/generate-script")
async def generate_script(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Proxy endpoint for script generation"""
    try:
        body = await request.body()
        
        # Add user context to the request
        user_context = {
            "user_id": current_user["id"],
            "user_email": current_user["email"],
            "user_role": current_user.get("role")
        }
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"{VIDEO_SERVICE_URL}/api/generate-script",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Key": os.getenv("SERVICE_API_KEY"),
                    "X-User-Context": str(user_context)
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Video service error: {response.text}"
                )
            
            # Log the project creation in your database if needed
            project_data = response.json()
            await log_video_project(db, current_user["id"], project_data)
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Video service timeout")
    except Exception as e:
        logger.error(f"Video generation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Video generation failed")

@router.post("/generate-video")
async def generate_video(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Proxy endpoint for video generation"""
    try:
        body = await request.body()
        
        user_context = {
            "user_id": current_user["id"],
            "user_email": current_user["email"],
            "user_role": current_user.get("role")
        }
        
        async with httpx.AsyncClient(timeout=600.0) as client:  # Longer timeout for video
            response = await client.post(
                f"{VIDEO_SERVICE_URL}/api/generate-video",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Service-Key": os.getenv("SERVICE_API_KEY"),
                    "X-User-Context": str(user_context)
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Video service error: {response.text}"
                )
            
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Video generation timeout")
    except Exception as e:
        logger.error(f"Video generation error: {str(e)}")
        raise HTTPException(status_code=500, detail="Video generation failed")

@router.get("/projects")
async def get_user_projects(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's video projects"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{VIDEO_SERVICE_URL}/api/projects",
                headers={
                    "X-Service-Key": os.getenv("SERVICE_API_KEY"),
                    "X-User-Id": current_user["id"]
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Video service error: {response.text}"
                )
            
            return response.json()
            
    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch projects")

@router.get("/video/{project_id}")
async def stream_video(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Stream video file"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{VIDEO_SERVICE_URL}/api/video/{project_id}",
                headers={
                    "X-Service-Key": os.getenv("SERVICE_API_KEY"),
                    "X-User-Id": current_user["id"]
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Video not found or access denied"
                )
            
            return StreamingResponse(
                response.iter_bytes(),
                media_type="video/mp4",
                headers={
                    "Content-Disposition": f"inline; filename=video_{project_id}.mp4"
                }
            )
            
    except Exception as e:
        logger.error(f"Error streaming video: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to stream video")

# Helper function to log video projects
async def log_video_project(db: Session, user_id: str, project_data: Dict[Any, Any]):
    """Log video project creation in database"""
    try:
        # You can create a video_projects table or log in existing tables
        # This is optional based on your tracking needs
        pass
    except Exception as e:
        logger.error(f"Error logging video project: {str(e)}")