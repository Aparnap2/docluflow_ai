"""Deployment script for Modal vLLM endpoints."""

import subprocess
import sys
import os
import argparse
import structlog

logger = structlog.get_logger(__name__)

def deploy_granite_cpu():
    """Deploy Granite-Docling CPU endpoint."""
    logger.info("Deploying Granite-Docling CPU endpoint...")
    
    try:
        result = subprocess.run([
            "modal", "deploy", "granite_docling_cpu.py"
        ], cwd="modal_backend", capture_output=True, text=True, check=True)
        
        logger.info("Granite-Docling CPU deployment completed", 
                   stdout=result.stdout,
                   stderr=result.stderr)
        
        # Extract URL from output
        for line in result.stdout.split('\n'):
            if 'modal.run' in line:
                url = line.strip()
                logger.info(f"Granite-Docling CPU endpoint: {url}")
                return url
                
    except subprocess.CalledProcessError as e:
        logger.error("Granite-Docling CPU deployment failed", 
                    error=e.stderr,
                    returncode=e.returncode)
        raise

def deploy_deepseek_gpu():
    """Deploy DeepSeek-OCR GPU endpoint."""
    logger.info("Deploying DeepSeek-OCR GPU endpoint...")
    
    try:
        result = subprocess.run([
            "modal", "deploy", "deepseek_ocr_gpu.py"
        ], cwd="modal_backend", capture_output=True, text=True, check=True)
        
        logger.info("DeepSeek-OCR GPU deployment completed",
                   stdout=result.stdout,
                   stderr=result.stderr)
        
        # Extract URL from output
        for line in result.stdout.split('\n'):
            if 'modal.run' in line:
                url = line.strip()
                logger.info(f"DeepSeek-OCR GPU endpoint: {url}")
                return url
                
    except subprocess.CalledProcessError as e:
        logger.error("DeepSeek-OCR GPU deployment failed",
                    error=e.stderr,
                    returncode=e.returncode)
        raise

def update_env_file(granite_url: str, deepseek_url: str):
    """Update .env file with deployed URLs."""
    env_path = "src/.env"
    
    try:
        # Read current env file
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Update URLs
        updated_lines = []
        for line in lines:
            if line.startswith('MODAL_GRANITE_URL='):
                updated_lines.append(f'MODAL_GRANITE_URL={granite_url}\n')
            elif line.startswith('MODAL_DEEPSEEK_URL='):
                updated_lines.append(f'MODAL_DEEPSEEK_URL={deepseek_url}\n')
            else:
                updated_lines.append(line)
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(updated_lines)
            
        logger.info("Updated .env file with Modal endpoints",
                   granite_url=granite_url,
                   deepseek_url=deepseek_url)
        
    except Exception as e:
        logger.error("Failed to update .env file", error=str(e))
        raise

def check_modal_auth():
    """Check if Modal authentication is configured."""
    try:
        result = subprocess.run([
            "modal", "token", "info"
        ], capture_output=True, text=True, check=True)
        
        logger.info("Modal authentication verified", 
                   stdout=result.stdout.strip())
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error("Modal authentication failed", 
                    error=e.stderr,
                    returncode=e.returncode)
        return False

def main():
    """Main deployment function."""
    parser = argparse.ArgumentParser(description="Deploy Modal vLLM endpoints")
    parser.add_argument("--cpu-only", action="store_true", help="Deploy only CPU endpoint")
    parser.add_argument("--gpu-only", action="store_true", help="Deploy only GPU endpoint")
    parser.add_argument("--check-auth", action="store_true", help="Check Modal authentication only")
    
    args = parser.parse_args()
    
    # Setup logging
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    logger.info("Starting Modal deployment process")
    
    # Check authentication first
    if not check_modal_auth():
        logger.error("Please run 'modal token set' to authenticate with Modal")
        sys.exit(1)
    
    if args.check_auth:
        logger.info("Modal authentication check completed")
        return
    
    try:
        granite_url = None
        deepseek_url = None
        
        # Deploy CPU endpoint
        if not args.gpu_only:
            granite_url = deploy_granite_cpu()
            logger.info(f"Granite-Docling CPU endpoint deployed: {granite_url}")
        
        # Deploy GPU endpoint
        if not args.cpu_only:
            deepseek_url = deploy_deepseek_gpu()
            logger.info(f"DeepSeek-OCR GPU endpoint deployed: {deepseek_url}")
        
        # Update environment file
        if granite_url or deepseek_url:
            update_env_file(
                granite_url or os.getenv('MODAL_GRANITE_URL', 'https://placeholder-granite.modal.run'),
                deepseek_url or os.getenv('MODAL_DEEPSEEK_URL', 'https://placeholder-deepseek.modal.run')
            )
        
        logger.info("Modal deployment completed successfully!")
        
        # Test endpoints
        if granite_url:
            logger.info(f"Test Granite endpoint: {granite_url}/docs")
        if deepseek_url:
            logger.info(f"Test DeepSeek endpoint: {deepseek_url}/docs")
            
    except Exception as e:
        logger.error("Deployment failed", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()