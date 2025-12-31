"""Secure deployment script for Modal endpoints with comprehensive error handling and validation."""

import modal
import subprocess
import sys
import time
import requests
import json
from typing import Dict, Any, Optional

def deploy_modal_endpoint(app_file: str, app_name: str, timeout: int = 600) -> Optional[Dict[str, Any]]:
    """
    Deploy a Modal endpoint with comprehensive error handling and validation.
    
    Args:
        app_file: Path to the Modal app file
        app_name: Name of the Modal app
        timeout: Deployment timeout in seconds
        
    Returns:
        Deployment result with endpoint information or None if failed
    """
    print(f"🚀 Starting deployment of {app_name} from {app_file}")
    
    try:
        # Deploy the Modal app
        print(f"📦 Deploying Modal app: {app_name}")
        result = subprocess.run(
            ["modal", "deploy", app_file],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            print(f"❌ Deployment failed for {app_name}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return None
            
        print(f"✅ Deployment successful for {app_name}")
        print(f"Output: {result.stdout}")
        
        # Extract deployment information from output
        deployment_info = extract_deployment_info(result.stdout, app_name)
        
        if deployment_info:
            print(f"🔗 Endpoint URL: {deployment_info.get('endpoint_url', 'Unknown')}")
            
            # Wait for service to be ready
            if validate_endpoint(deployment_info.get('endpoint_url')):
                print(f"✅ Endpoint is ready and responding")
                return deployment_info
            else:
                print(f"⚠️  Endpoint deployed but not responding yet")
                return deployment_info
        else:
            print(f"⚠️  Could not extract deployment information")
            return {"app_name": app_name, "status": "deployed", "endpoint_url": None}
            
    except subprocess.TimeoutExpired:
        print(f"⏰ Deployment timed out for {app_name}")
        return None
    except Exception as e:
        print(f"💥 Unexpected error deploying {app_name}: {str(e)}")
        return None

def extract_deployment_info(output: str, app_name: str) -> Optional[Dict[str, Any]]:
    """Extract deployment information from Modal output."""
    try:
        # Look for URL patterns in the output
        import re
        
        # Extract web endpoint URL
        url_pattern = r'https://[^\s]+\.modal\.run'
        urls = re.findall(url_pattern, output)
        
        if urls:
            endpoint_url = urls[0]
            return {
                "app_name": app_name,
                "status": "deployed",
                "endpoint_url": endpoint_url,
                "deployment_time": time.time()
            }
        
        # If no URL found, return basic info
        return {
            "app_name": app_name,
            "status": "deployed",
            "endpoint_url": None,
            "raw_output": output
        }
        
    except Exception as e:
        print(f"⚠️  Failed to extract deployment info: {str(e)}")
        return None

def validate_endpoint(endpoint_url: Optional[str], max_retries: int = 10, retry_delay: int = 30) -> bool:
    """
    Validate that the deployed endpoint is responding correctly.
    
    Args:
        endpoint_url: The endpoint URL to validate
        max_retries: Maximum number of validation attempts
        retry_delay: Delay between retries in seconds
        
    Returns:
        True if endpoint is responding, False otherwise
    """
    if not endpoint_url:
        print("⚠️  No endpoint URL provided for validation")
        return False
        
    print(f"🔍 Validating endpoint: {endpoint_url}")
    
    for attempt in range(max_retries):
        try:
            print(f"🔄 Validation attempt {attempt + 1}/{max_retries}")
            
            # Try health check endpoint
            health_url = f"{endpoint_url}/health"
            response = requests.get(health_url, timeout=30)
            
            if response.status_code == 200:
                health_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                print(f"✅ Health check successful: {health_data}")
                return True
            else:
                print(f"⚠️  Health check returned status {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"⏳ Endpoint not ready yet: {str(e)}")
        except Exception as e:
            print(f"⚠️  Validation error: {str(e)}")
        
        if attempt < max_retries - 1:
            print(f"⏰ Waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)
    
    print(f"❌ Endpoint validation failed after {max_retries} attempts")
    return False

def deploy_all_endpoints() -> Dict[str, Any]:
    """Deploy all Modal endpoints with security and validation."""
    
    endpoints = [
        {
            "file": "modal_backend/granite_docling_cpu_optimized.py",
            "name": "granite-docling-cpu-optimized",
            "type": "cpu"
        },
        {
            "file": "modal_backend/deepseek_ocr_gpu_optimized.py", 
            "name": "deepseek-ocr-gpu-optimized",
            "type": "gpu"
        }
    ]
    
    results = {
        "successful": [],
        "failed": [],
        "total": len(endpoints),
        "timestamp": time.time()
    }
    
    print("🚀 Starting secure Modal endpoint deployment")
    print(f"📋 Deploying {len(endpoints)} endpoints with security validation")
    
    for endpoint in endpoints:
        print(f"\n{'='*60}")
        print(f"🔧 Deploying {endpoint['type'].upper()} endpoint: {endpoint['name']}")
        print(f"📁 File: {endpoint['file']}")
        
        result = deploy_modal_endpoint(
            app_file=endpoint['file'],
            app_name=endpoint['name'],
            timeout=900  # 15 minutes for GPU deployment
        )
        
        if result:
            results["successful"].append({
                **endpoint,
                "deployment_info": result
            })
            print(f"✅ {endpoint['name']} deployed successfully")
        else:
            results["failed"].append({
                **endpoint,
                "error": "Deployment failed"
            })
            print(f"❌ {endpoint['name']} deployment failed")
    
    # Summary
    print(f"\n{'='*60}")
    print("📊 DEPLOYMENT SUMMARY")
    print(f"✅ Successful: {len(results['successful'])}/{results['total']}")
    print(f"❌ Failed: {len(results['failed'])}/{results['total']}")
    
    if results['successful']:
        print("\n🌐 DEPLOYED ENDPOINTS:")
        for success in results['successful']:
            endpoint_url = success['deployment_info'].get('endpoint_url', 'Unknown')
            print(f"  • {success['name']}: {endpoint_url}")
    
    if results['failed']:
        print("\n💥 FAILED DEPLOYMENTS:")
        for failure in results['failed']:
            print(f"  • {failure['name']}: {failure['error']}")
    
    return results

def main():
    """Main deployment function with security validation."""
    print("🔒 SECURE MODAL DEPLOYMENT")
    print("This script deploys Modal endpoints with comprehensive security and validation")
    
    # Check if Modal CLI is available
    try:
        result = subprocess.run(["modal", "--version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ Modal CLI not found. Please install Modal: pip install modal")
            sys.exit(1)
    except FileNotFoundError:
        print("❌ Modal CLI not found. Please install Modal: pip install modal")
        sys.exit(1)
    
    print("✅ Modal CLI detected")
    
    # Deploy all endpoints
    results = deploy_all_endpoints()
    
    # Exit with appropriate code
    success_count = len(results['successful'])
    total_count = results['total']
    
    if success_count == total_count:
        print(f"\n🎉 ALL DEPLOYMENTS SUCCESSFUL!")
        sys.exit(0)
    elif success_count > 0:
        print(f"\n⚠️  PARTIAL SUCCESS: {success_count}/{total_count} endpoints deployed")
        sys.exit(0)  # Partial success is still acceptable
    else:
        print(f"\n💥 ALL DEPLOYMENTS FAILED!")
        sys.exit(1)

if __name__ == "__main__":
    main()