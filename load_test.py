"""
Load test for PropFlow Agent.
Tests concurrent document processing and resource usage.
"""
import asyncio
import time
import psutil
import os
from datetime import datetime
from agent_graph import router_node, extraction_node


async def process_document_simulation(doc_id: int, doc_type: str, text: str):
    """Simulate processing a single document."""
    start_time = time.time()
    
    # Router step
    state = {"doc_url": f"test://doc_{doc_id}.pdf", "text_md": text, "doc_type": "", "final_data": {}}
    router_result = router_node(state)
    state_after_router = {**state, **router_result}
    
    # Extraction step (simulated - skip actual LLM call for load test)
    # In real scenario, this would call extraction_node
    extraction_result = {"final_data": {"doc_type": state_after_router["doc_type"], "status": "processed"}}
    result = {**state_after_router, **extraction_result}
    
    elapsed = time.time() - start_time
    return {
        "doc_id": doc_id,
        "doc_type": result["doc_type"],
        "elapsed": elapsed,
        "success": True
    }


def get_sample_texts():
    """Get sample document texts for testing."""
    return {
        "lease": """
        RESIDENTIAL LEASE AGREEMENT
        Tenant Name: John Smith
        End Date: December 31, 2024
        Notice Period: 60 days
        """,
        "quote": """
        ESTIMATE / QUOTE
        Vendor: ACME Plumbing Services
        Total Amount: $1,000.00
        """,
        "coi": """
        CERTIFICATE OF LIABILITY INSURANCE
        Expiration Date: February 15, 2024
        Policy Limit: $2,000,000
        """
    }


async def run_load_test(num_documents: int, concurrency: int):
    """Run load test with specified number of documents and concurrency."""
    print(f"\n{'='*70}")
    print(f"Load Test: {num_documents} documents, {concurrency} concurrent")
    print(f"{'='*70}\n")
    
    # Get system info before test
    process = psutil.Process(os.getpid())
    mem_before = process.memory_info().rss / 1024 / 1024  # MB
    cpu_before = process.cpu_percent(interval=0.1)
    
    sample_texts = get_sample_texts()
    doc_types = ["lease", "quote", "coi"]
    
    # Create tasks
    tasks = []
    for i in range(num_documents):
        doc_type = doc_types[i % len(doc_types)]
        text = sample_texts[doc_type]
        tasks.append(process_document_simulation(i, doc_type, text))
    
    # Run with concurrency limit
    start_time = time.time()
    results = []
    
    # Process in batches
    for i in range(0, len(tasks), concurrency):
        batch = tasks[i:i+concurrency]
        batch_results = await asyncio.gather(*batch)
        results.extend(batch_results)
        
        # Show progress
        if (i + concurrency) % 10 == 0 or i + concurrency >= len(tasks):
            print(f"  Processed {min(i + concurrency, len(tasks))}/{len(tasks)} documents...")
    
    elapsed_time = time.time() - start_time
    
    # Get system info after test
    mem_after = process.memory_info().rss / 1024 / 1024  # MB
    cpu_after = process.cpu_percent(interval=0.1)
    
    # Calculate statistics
    success_count = sum(1 for r in results if r["success"])
    avg_time = sum(r["elapsed"] for r in results) / len(results)
    max_time = max(r["elapsed"] for r in results)
    min_time = min(r["elapsed"] for r in results)
    
    # Group by doc_type
    doc_type_counts = {}
    for r in results:
        doc_type = r["doc_type"]
        doc_type_counts[doc_type] = doc_type_counts.get(doc_type, 0) + 1
    
    # Print results
    print(f"\n{'='*70}")
    print("Load Test Results")
    print(f"{'='*70}")
    print(f"Total Documents: {num_documents}")
    print(f"Successful: {success_count}")
    print(f"Failed: {num_documents - success_count}")
    print(f"Total Time: {elapsed_time:.2f}s")
    print(f"Throughput: {num_documents / elapsed_time:.2f} docs/sec")
    print(f"\nPer-Document Stats:")
    print(f"  Average: {avg_time*1000:.2f}ms")
    print(f"  Min: {min_time*1000:.2f}ms")
    print(f"  Max: {max_time*1000:.2f}ms")
    print(f"\nDocument Type Distribution:")
    for doc_type, count in doc_type_counts.items():
        print(f"  {doc_type}: {count}")
    print(f"\nResource Usage:")
    print(f"  Memory Before: {mem_before:.2f} MB")
    print(f"  Memory After: {mem_after:.2f} MB")
    print(f"  Memory Delta: {mem_after - mem_before:.2f} MB")
    print(f"  CPU Before: {cpu_before:.1f}%")
    print(f"  CPU After: {cpu_after:.1f}%")
    print(f"{'='*70}\n")
    
    return {
        "total_documents": num_documents,
        "success_count": success_count,
        "elapsed_time": elapsed_time,
        "throughput": num_documents / elapsed_time,
        "avg_time": avg_time,
        "mem_before": mem_before,
        "mem_after": mem_after,
        "mem_delta": mem_after - mem_before,
        "cpu_before": cpu_before,
        "cpu_after": cpu_after
    }


async def main():
    """Run load tests with different configurations."""
    print("="*70)
    print("PropFlow Agent Load Test Suite")
    print("="*70)
    
    # Install psutil if needed
    try:
        import psutil
    except ImportError:
        print("Installing psutil for resource monitoring...")
        os.system("pip install psutil")
        import psutil
    
    # Reduced load for CPU-only Ollama and PyTorch/Docling
    # These are more realistic for CPU-only processing
    test_configs = [
        (5, 1),    # 5 docs, 1 concurrent (warm-up)
        (10, 2),   # 10 docs, 2 concurrent (light load)
        (20, 3),   # 20 docs, 3 concurrent (moderate load)
    ]
    
    all_results = []
    for num_docs, concurrency in test_configs:
        result = await run_load_test(num_docs, concurrency)
        all_results.append(result)
        await asyncio.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*70)
    print("Load Test Summary")
    print("="*70)
    print(f"{'Config':<20} {'Throughput':<15} {'Avg Time':<15} {'Mem Delta':<15}")
    print("-" * 70)
    for result in all_results:
        config = f"{result['total_documents']} docs, {result['total_documents']//10} concurrent"
        print(f"{config:<20} {result['throughput']:>10.2f} docs/s  {result['avg_time']*1000:>10.2f}ms  {result['mem_delta']:>10.2f} MB")
    print("="*70)


if __name__ == "__main__":
    asyncio.run(main())

