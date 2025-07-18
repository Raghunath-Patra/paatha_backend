from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from config.database import get_db
from config.security import get_current_user
import httpx
import os
from typing import Dict, Any
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/video-generator", tags=["video-generation"])

VIDEO_SERVICE_URL = os.getenv("VIDEO_SERVICE_URL", "http://localhost:8001")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "your-service-key-here")

# Debug endpoint to check configuration
@router.get("/debug/config")
async def debug_config(
    current_user: dict = Depends(get_current_user)
):
    """Debug endpoint to check video service configuration"""
    return {
        "user_id": str(current_user["id"]),  # Convert UUID to string
        "user_role": current_user.get("role"),
        "video_service_url": VIDEO_SERVICE_URL,
        "service_key_configured": bool(SERVICE_API_KEY and SERVICE_API_KEY != "your-service-key-here"),
        "service_key_length": len(SERVICE_API_KEY) if SERVICE_API_KEY else 0,
        "environment_vars": {
            "VIDEO_SERVICE_URL": bool(os.getenv("VIDEO_SERVICE_URL")),
            "SERVICE_API_KEY": bool(os.getenv("SERVICE_API_KEY"))
        }
    }

def get_service_headers(user_context: Dict = None):
    """Get headers for video service requests"""
    headers = {
        "Content-Type": "application/json",
        "X-Service-Key": SERVICE_API_KEY
    }
    
    if user_context:
        headers["X-User-Context"] = json.dumps(user_context)
    
    return headers

@router.post("/generate-script")
async def generate_script(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Proxy endpoint for script generation"""
    try:
        # Check if user has permission (optional role check)
        if current_user.get('role') not in ['student', 'teacher']:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only students and teachers can generate scripts."
            )
        
        body = await request.body()
        
        # Add user context to the request - CONVERT UUID TO STRING
        user_id = str(current_user["id"])
        user_email = current_user.get("email", "")
        user_role = current_user.get("role", "student")
        
        user_context = {
            "user_id": user_id,
            "user_email": user_email,
            "user_role": user_role
        }
        
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                # Send both formats for compatibility - ALL VALUES MUST BE STRINGS
                headers = {
                    "Content-Type": "application/json",
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,  # Now a string
                    "X-User-Email": user_email,
                    "X-User-Role": user_role,
                    "X-User-Context": json.dumps(user_context)
                }
                
                response = await client.post(
                    f"{VIDEO_SERVICE_URL}/api/generate-script",
                    content=body,
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Video service error: {response.text}"
                    )
                
                # Log the project creation in your database if needed
                project_data = response.json()
                await log_video_project(db, user_id, project_data)
                
                return project_data
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except httpx.TimeoutException:
        logger.error("Video service timeout")
        raise HTTPException(status_code=504, detail="Video service timeout")
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Video generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")

@router.post("/generate-video")
async def generate_video(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Proxy endpoint for video generation"""
    try:
        # Check if user has permission
        if current_user.get('role') not in ['student', 'teacher']:
            raise HTTPException(
                status_code=403,
                detail="Access denied. Only students and teachers can generate videos."
            )
        
        body = await request.body()
        
        # CONVERT UUID TO STRING
        user_id = str(current_user["id"])
        user_email = current_user.get("email", "")
        user_role = current_user.get("role", "student")
        
        user_context = {
            "user_id": user_id,
            "user_email": user_email,
            "user_role": user_role
        }
        
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient(timeout=600.0) as client:  # Longer timeout for video
            try:
                # Send both formats for compatibility - ALL VALUES MUST BE STRINGS
                headers = {
                    "Content-Type": "application/json",
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,  # Now a string
                    "X-User-Email": user_email,
                    "X-User-Role": user_role,
                    "X-User-Context": json.dumps(user_context)
                }
                
                response = await client.post(
                    f"{VIDEO_SERVICE_URL}/api/generate-video",
                    content=body,
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Video service error: {response.text}"
                    )
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except httpx.TimeoutException:
        logger.error("Video generation timeout")
        raise HTTPException(status_code=504, detail="Video generation timeout")
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Video generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Video generation failed: {str(e)}")

@router.get("/projects")
async def get_user_projects(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's video projects"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                # CONVERT UUID TO STRING - THIS IS THE FIX
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,  # Now a string instead of UUID
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                logger.info(f"Making request to: {VIDEO_SERVICE_URL}/api/projects")
                logger.info(f"Request headers: {dict(headers)}")
                
                response = await client.get(
                    f"{VIDEO_SERVICE_URL}/api/projects",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error(f"403 Forbidden from video service")
                    logger.error(f"Response text: {response.text}")
                    # Return empty projects instead of error
                    return {
                        "success": True,
                        "projects": [],
                        "total": 0,
                        "page": 1,
                        "limit": 20,
                        "message": "Access denied by video service"
                    }
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    # Return empty projects instead of error
                    return {
                        "success": True,
                        "projects": [],
                        "total": 0,
                        "page": 1,
                        "limit": 20,
                        "message": f"Video service unavailable (Status: {response.status_code})"
                    }
                
                return response.json()
                
            except httpx.ConnectError as e:
                logger.error(f"Connection error to video service: {str(e)}")
                return {
                    "success": True,
                    "projects": [],
                    "total": 0,
                    "page": 1,
                    "limit": 20,
                    "message": "Video service offline"
                }
            except httpx.TimeoutException as e:
                logger.error(f"Timeout connecting to video service: {str(e)}")
                return {
                    "success": True,
                    "projects": [],
                    "total": 0,
                    "page": 1,
                    "limit": 20,
                    "message": "Video service timeout"
                }
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    return {
                        "success": True,
                        "projects": [],
                        "total": 0,
                        "page": 1,
                        "limit": 20,
                        "message": "Access denied by video service"
                    }
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching projects: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch projects: {str(e)}")

@router.get("/stream/{project_id}")
async def stream_video(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get signed URL for video streaming"""
    try:
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            user_id = str(current_user["id"])
            user_email = current_user.get("email", "")
            user_role = current_user.get("role", "student")
            
            headers = {
                "X-Service-Key": SERVICE_API_KEY,
                "X-User-Id": user_id,
                "X-User-Email": user_email,
                "X-User-Role": user_role
            }
            
            # Use the /stream endpoint instead of /video
            response = await client.get(
                f"{VIDEO_SERVICE_URL}/api/stream/{project_id}",
                headers=headers
            )
            
            logger.info(f"Video service response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Video service error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Video not found or access denied"
                )
            
            # Return the JSON response with signed URL
            return response.json()
                
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Video service error: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Error getting video stream URL: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get video stream URL: {str(e)}")
    
@router.get("/download/{project_id}")
async def download_video(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download video file"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,  # Now a string
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.get(
                    f"{VIDEO_SERVICE_URL}/api/download/{project_id}",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="Video not found or access denied"
                    )
                
                return StreamingResponse(
                    response.iter_bytes(),
                    media_type="video/mp4",
                    headers={
                        "Content-Disposition": f"attachment; filename=video_{project_id}.mp4"
                    }
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: {str  (e)}")

@router.put("/project/{project_id}/step/{step_number}")
async def update_project_step(
    project_id: str,
    step_number: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a specific step in a video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        body = await request.body()
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "Content-Type": "application/json",
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.put(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}/step/{step_number}",
                    content=body,
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Video service error: {response.text}"
                    )
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except httpx.TimeoutException:
        logger.error("Video service timeout")
        raise HTTPException(status_code=504, detail="Video service timeout")
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating project step: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update project step: {str(e)}")

@router.post("/project/{project_id}/step/{step_number}/ai-modify")
async def ai_modify_project_step(
    project_id: str,
    step_number: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """AI modify a specific step in a video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        body = await request.body()
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "Content-Type": "application/json",
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.post(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}/step/{step_number}/ai-modify",
                    content=body,
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Video service error: {response.text}"
                    )
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except httpx.TimeoutException:
        logger.error("Video service timeout")
        raise HTTPException(status_code=504, detail="Video service timeout")
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error AI modifying project step: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to AI modify project step: {str(e)}")

@router.get("/project/{project_id}/export-pdf")
async def export_project_pdf(
    project_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Export video project as PDF"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.get(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}/export-pdf",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail="PDF export failed or access denied"
                    )
                
                return StreamingResponse(
                    response.iter_bytes(),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename=project_{project_id}.pdf"
                    }
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error exporting PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export PDF: {str(e)}")

@router.get("/project/{project_id}/visual-functions")
async def get_project_visual_functions(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get visual functions for a video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.get(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}/visual-functions",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Visual functions not found or access denied"
                    )
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching visual functions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch visual functions: {str(e)}")

@router.put("/project/{project_id}/visual-function/{function_name}")
async def update_visual_function(
    project_id: str,
    function_name: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a visual function in a video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        body = await request.body()
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "Content-Type": "application/json",
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.put(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}/visual-function/{function_name}",
                    content=body,
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Video service error: {response.text}"
                    )
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except httpx.TimeoutException:
        logger.error("Video service timeout")
        raise HTTPException(status_code=504, detail="Video service timeout")
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error updating visual function: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update visual function: {str(e)}")

@router.delete("/project/{project_id}/visual-function/{function_name}")
async def delete_visual_function(
    project_id: str,
    function_name: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a visual function from a video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.delete(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}/visual-function/{function_name}",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to delete visual function: {response.text}"
                    )
                
                return {"success": True, "message": "Visual function deleted successfully"}
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting visual function: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete visual function: {str(e)}")

# Helper function to log video projects
async def log_video_project(db: Session, user_id: str, project_data: Dict[Any, Any]):
    """Log video project creation in database"""
    try:
        # You can create a video_projects table or log in existing tables
        # This is optional based on your tracking needs
        from models import VideoProject
        
        if 'project_id' in project_data:
            video_project = VideoProject(
                user_id=user_id,  # user_id is now a string
                project_id=project_data['project_id'],
                title=project_data.get('title', 'Untitled'),
                description=project_data.get('description', ''),
                status=project_data.get('status', 'created')
            )
            db.add(video_project)
            db.commit()
            logger.info(f"Video project logged: {project_data['project_id']}")
        
    except Exception as e:
        logger.error(f"Error logging video project: {str(e)}")
        db.rollback()

@router.get("/project/{project_id}")
async def get_project_details(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,  # Now a string
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.get(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Video project not found or access denied"
                    )
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching project details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch project details: {str(e)}")

@router.delete("/project/{project_id}")
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a specific video project"""
    try:
        # Check if SERVICE_API_KEY is set
        if not SERVICE_API_KEY or SERVICE_API_KEY == "your-service-key-here":
            logger.error("SERVICE_API_KEY not properly configured")
            raise HTTPException(
                status_code=500,
                detail="Video service not properly configured"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                # CONVERT UUID TO STRING
                user_id = str(current_user["id"])
                user_email = current_user.get("email", "")
                user_role = current_user.get("role", "student")
                
                headers = {
                    "X-Service-Key": SERVICE_API_KEY,
                    "X-User-Id": user_id,  # Now a string
                    "X-User-Email": user_email,
                    "X-User-Role": user_role
                }
                
                response = await client.delete(
                    f"{VIDEO_SERVICE_URL}/api/project/{project_id}",
                    headers=headers
                )
                
                logger.info(f"Video service response status: {response.status_code}")
                
                if response.status_code == 403:
                    logger.error("403 Forbidden from video service - check SERVICE_API_KEY")
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                
                if response.status_code != 200:
                    logger.error(f"Video service error: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to delete video project: {response.text}"
                    )
                
                return {"success": True, "message": "Project deleted successfully"}
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error from video service: {e.response.status_code} - {e.response.text}")
                if e.response.status_code == 403:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied by video service. Check service configuration."
                    )
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"Video service error: {e.response.text}"
                )
            
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error deleting project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")

