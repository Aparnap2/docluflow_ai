"""
Production-Grade Modal Client with Exponential Backoff & Retry
Handles serverless cold starts, transient errors, and network flakes
"""

import time
import requests
import logging
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

def create_robust_session():
    """Create a requests session with retry logic for serverless cold starts."""
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def call_modal_with_retry(url: str, payload: Dict[str, Any], max_retries: int = 3, 
                          initial_timeout: int = 60) -> Optional[Dict[str, Any]]:
    """
    Robustly calls a Modal endpoint with retries and exponential backoff.
    Handles cold starts (long timeouts) and transient failures (503s).
    
    Args:
        url: Modal endpoint URL
        payload: Request payload
        max_retries: Maximum number of retry attempts
        initial_timeout: Initial timeout in seconds (increases with retries)
    
    Returns:
        Response JSON or None if all retries failed
    """
    session = create_robust_session()
    
    for attempt in range(max_retries):
        try:
            # Increase timeout on subsequent retries (give it more time if it failed once)
            current_timeout = initial_timeout + (attempt * 30)
            
            logger.info(f"Calling Modal (Attempt {attempt+1}/{max_retries})... timeout={current_timeout}s")
            logger.debug(f"URL: {url}, Payload size: {len(str(payload))} chars")
            
            response = session.post(url, json=payload, timeout=current_timeout)
            
            # Case 1: Success
            if response.status_code == 200:
                logger.info(f"Modal request successful on attempt {attempt+1}")
                return response.json()
                
            # Case 2: Container Starting / Overloaded (503, 502, 504)
            elif response.status_code in [502, 503, 504]:
                wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s...
                logger.warning(f"Modal busy/starting ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
                
            # Case 3: Application Error (400, 500) - Don't retry
            else:
                logger.error(f"Modal Error {response.status_code}: {response.text}")
                return None

        except requests.exceptions.ReadTimeout:
            # Case 4: Timeout (Cold start took too long) - Retry
            logger.warning(f"Request timed out (>{current_timeout}s). Retrying...")
            continue
            
        except requests.exceptions.ConnectionError:
            # Case 5: Connection failed - Retry
            logger.warning("Connection error. Retrying...")
            time.sleep(1)
            continue
            
    logger.error("Max retries exceeded for Modal endpoint.")
    return None

def call_modal_health_check(url: str, max_retries: int = 3, timeout: int = 90) -> bool:
    """
    Robust health check for Modal endpoints with retry logic.
    
    Args:
        url: Health endpoint URL
        max_retries: Maximum number of retry attempts
        timeout: Timeout per attempt
    
    Returns:
        True if healthy, False otherwise
    """
    session = create_robust_session()
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Health check (Attempt {attempt+1}/{max_retries})... timeout={timeout}s")
            
            response = session.get(url, timeout=timeout)
            
            if response.status_code == 200:
                logger.info(f"Health check successful on attempt {attempt+1}")
                return True
            elif response.status_code in [502, 503, 504]:
                wait_time = 2 ** attempt
                logger.warning(f"Service unavailable ({response.status_code}). Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                logger.error(f"Health check failed with status {response.status_code}")
                return False
                
        except requests.exceptions.ReadTimeout:
            logger.warning(f"Health check timed out (>{timeout}s). Retrying...")
            continue
        except requests.exceptions.ConnectionError:
            logger.warning("Connection error during health check. Retrying...")
            time.sleep(1)
            continue
            
    logger.error("Health check failed after all retries.")
    return False

# Convenience functions for specific endpoints
def call_modal_cpu(endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call Modal CPU endpoint with robust retry logic."""
    return call_modal_with_retry(f"{endpoint}/process", payload)

def call_modal_gpu(endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call Modal GPU endpoint with robust retry logic."""
    return call_modal_with_retry(f"{endpoint}/process", payload)

def call_modal_extract(endpoint: str, file_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Call Modal extract endpoint with file upload."""
    return call_modal_with_retry(f"{endpoint}/extract", file_data)

# Example usage for testing
if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Test health check
    cpu_health = call_modal_health_check("https://ap3617180--docuflow-cpu-granite-gguf-serve.modal.run/health")
    gpu_health = call_modal_health_check("https://ap3617180--docuflow-gpu-deepseek-serve.modal.run/health")
    
    print(f"CPU Health: {'✅' if cpu_health else '❌'}")
    print(f"GPU Health: {'✅' if gpu_health else '❌'}")
    
    # Test processing
    test_payload = {
        "text": "Invoice #INV-2024-001\nDate: 2024-01-15\nVendor: TechCorp Solutions\nTotal: $1,250.00"
    }
    
    result = call_modal_cpu("https://ap3617180--docuflow-cpu-granite-gguf-serve.modal.run", test_payload)
    if result:
        print("CPU Processing Result:", result.get("status"))
    else:
        print("CPU Processing Failed")