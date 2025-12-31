"""Optimized deployment script for Modal vLLM endpoints with persistent caching."""

import subprocess
import sys
import os
import argparse
import structlog

# Configure logging
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

logger = structlog.get_logger(__name__)

def deploy_granite_cpu_optimized():
    """Deploy optimized Granite-Docling CPU endpoint with persistent caching."""
    logger.info("Deploying optimized Granite-Docling CPU endpoint with persistent caching...")
    
    try:
        result = subprocess.run([
            "modal", "deploy", "granite_docling_cpu_optimized.py"
        ], cwd="modal_backend", capture_output=True, text=True, check=True)
        
        logger.info("Optimized Granite-Docling CPU deployment completed", 
                   stdout=result.stdout,
                   stderr=result.stderr)
        
        # Extract URL from output
        for line in result.stdout.split('\n'):
            if 'modal.run' in line and 'Serving at:' in line:
                url = line.split('Serving at:')[1].strip()
                logger.info(f"Optimized Granite-Docling CPU endpoint: {url}")
                return url
                
    except subprocess.CalledProcessError as e:
        logger.error("Optimized Granite-Docling CPU deployment failed", 
                    error=e.stderr,
                    returncode=e.returncode)
        raise

def deploy_deepseek_gpu_optimized():
    """Deploy optimized DeepSeek-OCR GPU endpoint with persistent caching."""
    logger.info("Deploying optimized DeepSeek-OCR GPU endpoint with persistent caching...")
    
    try:
        result = subprocess.run([
            "modal", "deploy", "deepseek_ocr_gpu_optimized.py"
        ], cwd="modal_backend", capture_output=True, text=True, check=True)
        
        logger.info("Optimized DeepSeek-OCR GPU deployment completed",
                   stdout=result.stdout,
                   stderr=result.stderr)
        
        # Extract URL from output
        for line in result.stdout.split('\n'):
            if 'modal.run' in line and 'Serving at:' in line:
                url = line.split('Serving at:')[1].strip()
                logger.info(f"Optimized DeepSeek-OCR GPU endpoint: {url}")
                return url
                
    except subprocess.CalledProcessError as e:
        logger.error("Optimized DeepSeek-OCR GPU deployment failed",
                    error=e.stderr,
                    returncode=e.returncode)
        raise

def setup_persistent_volumes():
    """Set up persistent volumes for model caching."""
    logger.info("Setting up persistent volumes for model caching...")
    
    try:
        # Create volumes for both models
        volumes = ["granite-docling-cache", "deepseek-ocr-cache"]
        
        for volume_name in volumes:
            logger.info(f"Creating volume: {volume_name}")
            result = subprocess.run([
                "modal", "volume", "create", volume_name, "--yes"
            ], capture_output=True, text=True, check=True)
            logger.info(f"Volume {volume_name} created/verified")
            
    except subprocess.CalledProcessError as e:
        logger.warning("Volume creation may have failed (might already exist)", 
                      error=e.stderr,
                      returncode=e.returncode)
        # Continue anyway - volumes might already exist

def update_env_file_optimized(granite_url: str, deepseek_url: str):
    """Update .env file with optimized deployment URLs."""
    env_path = "src/.env"
    
    try:
        # Read current env file
        with open(env_path, 'r') as f:
            lines = f.readlines()
        
        # Update URLs and add caching configuration
        updated_lines = []
        for line in lines:
            if line.startswith('MODAL_GRANITE_URL='):
                updated_lines.append(f'MODAL_GRANITE_URL={granite_url}\n')
            elif line.startswith('MODAL_DEEPSEEK_URL='):
                updated_lines.append(f'MODAL_DEEPSEEK_URL={deepseek_url}\n')
            elif line.startswith('# Modal Deployment Configuration'):
                updated_lines.append(line)
                updated_lines.append('MODAL_VOLUME_GRANITE=granite-docling-cache\n')
                updated_lines.append('MODAL_VOLUME_DEEPSEEK=deepseek-ocr-cache\n')
                updated_lines.append('MODAL_CACHING_ENABLED=true\n')
            else:
                updated_lines.append(line)
        
        # Write back
        with open(env_path, 'w') as f:
            f.writelines(updated_lines)
            
        logger.info("Updated .env file with optimized Modal endpoints and caching config",
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
    """Main deployment function with optimized caching."""
    parser = argparse.ArgumentParser(description="Deploy optimized Modal vLLM endpoints with persistent caching")
    parser.add_argument("--cpu-only", action="store_true", help="Deploy only CPU endpoint")
    parser.add_argument("--gpu-only", action="store_true", help="Deploy only GPU endpoint")
    parser.add_argument("--check-auth", action="store_true", help="Check Modal authentication only")
    parser.add_argument("--setup-volumes-only", action="store_true", help="Set up volumes only")
    
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
    
    logger.info("Starting optimized Modal deployment with persistent caching")
    
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
        
        # Set up persistent volumes first
        if not args.gpu_only:
            setup_persistent_volumes()
        
        if args.setup_volumes_only:
            logger.info("Volume setup completed")
            return
        
        # Deploy CPU endpoint
        if not args.gpu_only:
            granite_url = deploy_granite_cpu_optimized()
            logger.info(f"Optimized Granite-Docling CPU endpoint deployed: {granite_url}")
        
        # Deploy GPU endpoint
        if not args.cpu_only:
            deepseek_url = deploy_deepseek_gpu_optimized()
            logger.info(f"Optimized DeepSeek-OCR GPU endpoint deployed: {deepseek_url}")
        
        # Update environment file
        if granite_url or deepseek_url:
            update_env_file_optimized(
                granite_url or os.getenv('MODAL_GRANITE_URL', 'https://placeholder-granite.modal.run'),
                deepseek_url or os.getenv('MODAL_DEEPSEEK_URL', 'https://placeholder-deepseek.modal.run')
            )
        
        logger.info("Optimized Modal deployment completed successfully!")
        
        # Provide usage instructions
        if granite_url:
            logger.info(f"Test CPU endpoint: {granite_url}/docs")
        if deepseek_url:
            logger.info(f"Test GPU endpoint: {deepseek_url}/docs")
            
        logger.info("Benefits of optimized deployment:")
        logger.info("- Persistent model caching prevents re-downloads")
        logger.info("- Faster cold starts (seconds vs minutes)")
        logger.info("- Cost savings on GPU time")
        logger.info("- Improved reliability during HF downtime")
            
    except Exception as e:
        logger.error("Optimized deployment failed", error=str(e))
        sys.exit(1)

if __name__ == "__main__":
    main()