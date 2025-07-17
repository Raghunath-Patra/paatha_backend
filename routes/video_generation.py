# routes/video_generation.py - Enhanced Video Generation Backend
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user, verify_service_auth
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import httpx
import os
import logging
import json
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video", tags=["video-generation"])

VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://localhost:8001")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY")
REQUEST_TIMEOUT = 300.0  # 5 minutes for script generation
VIDEO_TIMEOUT = 900.0   # 15 minutes for video generation

# Pydantic models for request/response validation
class GenerateScriptRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=50000, description="Educational content to convert to video script")

class GenerateVideoRequest(BaseModel):
    projectId: str = Field(..., description="Project ID to generate video for")
    slides: List[Dict[str, Any]] = Field(..., description="Lesson steps/slides data")

class VideoProject(BaseModel):
    projectId: str
    title: str
    createdAt: str
    status: str
    lessonStepsCount: int
    speakers: List[str]
    visualFunctions: List[str]
    hasVideo: bool
    videoFiles: List[str]
    lessonSteps: Optional[List[Dict[str, Any]]] = None
    visualFunctionCode: Optional[Dict[str, str]] = None

class ApiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    projects: Optional[List[VideoProject]] = None
    error: Optional[str] = None
    message: Optional[str] = None
    projectId: Optional[str] = None
    videoUrl: Optional[str] = None

# In-memory storage for tracking generation status (in production, use Redis or database)
generation_status = {}

def get_user_context(current_user: dict) -> Dict[str, Any]:
    """Extract user context for video service"""
    return {
        "user_id": current_user["id"],
        "user_email": current_user["email"],
        "user_role": current_user.get("role", "user"),
        "timestamp": datetime.utcnow().isoformat()
    }

def get_service_headers(user_context: Dict[str, Any]) -> Dict[str, str]:
    """Get headers for video service requests"""
    headers = {
        "Content-Type": "application/json"
    }
    
    if SERVICE_API_KEY:
        headers["X-Service-Key"] = SERVICE_API_KEY
    
    headers["X-User-Context"] = json.dumps(user_context)
    
    return headers

async def log_video_activity(
    db: Session, 
    user_id: str, 
    activity_type: str, 
    project_id: str = None, 
    metadata: Dict[str, Any] = None
):
    """Log video generation activities (implement based on your database schema)"""
    try:
        # Example implementation - adjust based on your database schema
        log_data = {
            "user_id": user_id,
            "activity_type": activity_type,  # "script_generated", "video_generated", etc.
            "project_id": project_id,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow()
        }
        
        # Save to your database here
        logger.info(f"Video activity logged: {log_data}")
        
    except Exception as e:
        logger.error(f"Error logging video activity: {str(e)}")

@router.post("/generate-script", response_model=ApiResponse)
async def generate_script(
    request: GenerateScriptRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate video script from educational content"""
    try:
        user_context = get_user_context(current_user)
        user_id = current_user["id"]
        
        logger.info(f"Script generation requested by user {user_id} for content length: {len(request.content)}")
        
        # Validate content length and type
        if len(request.content.strip()) < 10:
            raise HTTPException(
                status_code=400, 
                detail="Content must be at least 10 characters long"
            )
        
        # Track generation status
        generation_id = f"script_{user_id}_{int(datetime.utcnow().timestamp())}"
        generation_status[generation_id] = {
            "status": "processing",
            "user_id": user_id,
            "started_at": datetime.utcnow(),
            "type": "script"
        }
        
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{VIDEO_SERVICE_URL}/api/generate-script",
                json=request.dict(),
                headers=get_service_headers(user_context)
            )
            
            if response.status_code == 200:
                result_data = response.json()
                
                # Update generation status
                generation_status[generation_id]["status"] = "completed"
                generation_status[generation_id]["completed_at"] = datetime.utcnow()
                
                # Log activity in background
                background_tasks.add_task(
                    log_video_activity,
                    db,
                    user_id,
                    "video_generated",
                    request.projectId,
                    {
                        "slides_count": len(request.slides),
                        "generation_id": generation_id,
                        "video_url": result_data.get("videoUrl")
                    }
                )
                
                return ApiResponse(**result_data)
            
            elif response.status_code == 400:
                error_detail = response.json().get("detail", "Invalid request")
                raise HTTPException(status_code=400, detail=error_detail)
            
            elif response.status_code == 429:
                raise HTTPException(
                    status_code=429, 
                    detail="Rate limit exceeded. Please try again later."
                )
            
            else:
                logger.error(f"Video service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Video service error: {response.text}"
                )
                
    except httpx.TimeoutException:
        generation_status[generation_id]["status"] = "timeout"
        raise HTTPException(
            status_code=504, 
            detail="Video generation timeout. This usually happens with complex projects. Please try again."
        )
    
    except httpx.RequestError as e:
        generation_status[generation_id]["status"] = "error"
        logger.error(f"Video service connection error: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="Video service temporarily unavailable"
        )
    
    except Exception as e:
        generation_status[generation_id]["status"] = "error"
        logger.error(f"Video generation error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Video generation failed. Please try again."
        )

@router.get("/projects", response_model=ApiResponse)
async def get_user_projects(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's video projects with caching"""
    try:
        user_context = get_user_context(current_user)
        user_id = current_user["id"]
        
        logger.info(f"Projects requested by user {user_id}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{VIDEO_SERVICE_URL}/api/projects",
                headers=get_service_headers(user_context)
            )
            
            if response.status_code == 200:
                result_data = response.json()
                
                # Add some metadata to projects
                if result_data.get("success") and result_data.get("projects"):
                    for project in result_data["projects"]:
                        # Add video URL if project has video
                        if project.get("hasVideo"):
                            project["videoUrl"] = f"/api/video/video/{project['projectId']}"
                
                return ApiResponse(**result_data)
            
            elif response.status_code == 404:
                # No projects found - return empty list
                return ApiResponse(success=True, projects=[])
            
            else:
                logger.error(f"Video service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to fetch projects: {response.text}"
                )
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    
    except httpx.RequestError as e:
        logger.error(f"Video service connection error: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail="Video service temporarily unavailable"
        )
    
    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch projects")

@router.get("/projects/{project_id}", response_model=VideoProject)
async def get_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get specific project details"""
    try:
        user_context = get_user_context(current_user)
        user_id = current_user["id"]
        
        logger.info(f"Project {project_id} requested by user {user_id}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{VIDEO_SERVICE_URL}/api/projects/{project_id}",
                headers=get_service_headers(user_context)
            )
            
            if response.status_code == 200:
                project_data = response.json()
                
                # Add video URL if project has video
                if project_data.get("hasVideo"):
                    project_data["videoUrl"] = f"/api/video/video/{project_id}"
                
                return VideoProject(**project_data)
            
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Project not found")
            
            elif response.status_code == 403:
                raise HTTPException(status_code=403, detail="Access denied to this project")
            
            else:
                logger.error(f"Video service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Failed to fetch project"
                )
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    
    except Exception as e:
        logger.error(f"Error fetching project: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch project")

@router.get("/video/{project_id}")
async def stream_video(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Stream video file for authenticated user"""
    try:
        user_context = get_user_context(current_user)
        user_id = current_user["id"]
        
        logger.info(f"Video stream requested for project {project_id} by user {user_id}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{VIDEO_SERVICE_URL}/api/video/{project_id}",
                headers=get_service_headers(user_context)
            )
            
            if response.status_code == 200:
                # Stream the video content
                def video_stream():
                    for chunk in response.iter_bytes(chunk_size=8192):
                        yield chunk
                
                # Determine content type from response headers
                content_type = response.headers.get("content-type", "video/mp4")
                content_length = response.headers.get("content-length")
                
                headers = {
                    "Content-Disposition": f"inline; filename=video_{project_id}.mp4",
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "private, max-age=3600"  # Cache for 1 hour
                }
                
                if content_length:
                    headers["Content-Length"] = content_length
                
                return StreamingResponse(
                    video_stream(),
                    media_type=content_type,
                    headers=headers
                )
            
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Video not found")
            
            elif response.status_code == 403:
                raise HTTPException(status_code=403, detail="Access denied to this video")
            
            else:
                logger.error(f"Video service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Video not available")
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Video service timeout")
    
    except Exception as e:
        logger.error(f"Error streaming video: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to stream video")

@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a user's project"""
    try:
        user_context = get_user_context(current_user)
        user_id = current_user["id"]
        
        logger.info(f"Project deletion requested for {project_id} by user {user_id}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{VIDEO_SERVICE_URL}/api/projects/{project_id}",
                headers=get_service_headers(user_context)
            )
            
            if response.status_code == 200:
                # Log activity in background
                background_tasks.add_task(
                    log_video_activity,
                    db,
                    user_id,
                    "project_deleted",
                    project_id,
                    {"deleted_at": datetime.utcnow().isoformat()}
                )
                
                return JSONResponse(
                    content={"success": True, "message": "Project deleted successfully"}
                )
            
            elif response.status_code == 404:
                raise HTTPException(status_code=404, detail="Project not found")
            
            elif response.status_code == 403:
                raise HTTPException(status_code=403, detail="Access denied")
            
            else:
                logger.error(f"Video service error: {response.status_code} - {response.text}")
                raise HTTPException(status_code=response.status_code, detail="Failed to delete project")
                
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete project")

@router.get("/generation-status/{generation_id}")
async def get_generation_status(
    generation_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get status of ongoing generation process"""
    try:
        user_id = current_user["id"]
        
        if generation_id not in generation_status:
            raise HTTPException(status_code=404, detail="Generation not found")
        
        status_data = generation_status[generation_id]
        
        # Check if user owns this generation
        if status_data.get("user_id") != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Calculate elapsed time
        elapsed = datetime.utcnow() - status_data["started_at"]
        status_data["elapsed_seconds"] = int(elapsed.total_seconds())
        
        return JSONResponse(content=status_data)
        
    except Exception as e:
        logger.error(f"Error fetching generation status: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch status")

# Cleanup old generation statuses (run periodically)
async def cleanup_old_statuses():
    """Remove generation statuses older than 24 hours"""
    try:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        to_remove = []
        
        for gen_id, status_data in generation_status.items():
            if status_data["started_at"] < cutoff:
                to_remove.append(gen_id)
        
        for gen_id in to_remove:
            del generation_status[gen_id]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} old generation statuses")
            
    except Exception as e:
        logger.error(f"Error cleaning up statuses: {str(e)}")

# # Health check endpoint
# @router.get("/health")
# async def health_check():
#     """Health check for video generation service"""
#     try:
#         # Check video service connectivity
#         async with httpx.AsyncClient(timeout=5.0) as client:
#             response = await client.get(f"{VIDEO_SERVICE_URL}/health")
#             video_service_healthy = response.status_code == 200
#     except:
#         video_service_healthy = False
    
#     return JSONResponse(content={
#         "status": "healthy" if video_service_healthy else "degraded",
#         "video_service": "up" if video_service_healthy else "down",
#         "active_generations": len(generation_status),
#         "timestamp": datetime.utcnow().isoformat()
#     })[generation_id]["status"] = "completed"
#                 generation_status[generation_id]["completed_at"] = datetime.utcnow()
                
#                 # Log activity in background
#                 background_tasks.add_task(
#                     log_video_activity,
#                     db,
#                     user_id,
#                     "script_generated",
#                     result_data.get("data", {}).get("projectId"),
#                     {
#                         "content_length": len(request.content),
#                         "lesson_steps": result_data.get("data", {}).get("lessonStepsCount", 0),
#                         "generation_id": generation_id
#                     }
#                 )
                
#                 return ApiResponse(**result_data)
            
#             elif response.status_code == 400:
#                 error_detail = response.json().get("detail", "Invalid request")
#                 raise HTTPException(status_code=400, detail=error_detail)
            
#             elif response.status_code == 429:
#                 raise HTTPException(
#                     status_code=429, 
#                     detail="Rate limit exceeded. Please try again later."
#                 )
            
#             else:
#                 logger.error(f"Video service error: {response.status_code} - {response.text}")
#                 raise HTTPException(
#                     status_code=response.status_code,
#                     detail=f"Video service error: {response.text}"
#                 )
                
#     except httpx.TimeoutException:
#         generation_status[generation_id]["status"] = "timeout"
#         raise HTTPException(
#             status_code=504, 
#             detail="Script generation timeout. Please try with shorter content."
#         )
    
#     except httpx.RequestError as e:
#         generation_status[generation_id]["status"] = "error"
#         logger.error(f"Video service connection error: {str(e)}")
#         raise HTTPException(
#             status_code=503, 
#             detail="Video service temporarily unavailable"
#         )
    
#     except Exception as e:
#         generation_status[generation_id]["status"] = "error"
#         logger.error(f"Script generation error: {str(e)}")
#         raise HTTPException(
#             status_code=500, 
#             detail="Script generation failed. Please try again."
#         )

@router.post("/generate-video", response_model=ApiResponse)
async def generate_video(
    request: GenerateVideoRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate video from project slides"""
    try:
        user_context = get_user_context(current_user)
        user_id = current_user["id"]
        
        logger.info(f"Video generation requested by user {user_id} for project: {request.projectId}")
        
        # Validate slides data
        if not request.slides or len(request.slides) == 0:
            raise HTTPException(
                status_code=400, 
                detail="Slides data is required for video generation"
            )
        
        if len(request.slides) > 50:  # Reasonable limit
            raise HTTPException(
                status_code=400, 
                detail="Too many slides. Maximum 50 slides allowed."
            )
        
        # Track generation status
        generation_id = f"video_{user_id}_{request.projectId}_{int(datetime.utcnow().timestamp())}"
        generation_status[generation_id] = {
            "status": "processing",
            "user_id": user_id,
            "project_id": request.projectId,
            "started_at": datetime.utcnow(),
            "type": "video",
            "slides_count": len(request.slides)
        }
        
        async with httpx.AsyncClient(timeout=VIDEO_TIMEOUT) as client:
            response = await client.post(
                f"{VIDEO_SERVICE_URL}/api/generate-video",
                json=request.dict(),
                headers=get_service_headers(user_context)
            )
            
            if response.status_code == 200:
                result_data = response.json()
                
                # Update generation status
                generation_status
    except Exception as e:
        logger.error(f"Error in video generation: {str(e)}")
        raise HTTPException(status_code=500, detail="Video generation failed.")