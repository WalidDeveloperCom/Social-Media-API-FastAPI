#!/usr/bin/env python3
"""
Test runner script for Social Media API
"""
import sys
import os
import subprocess
from pathlib import Path

def run_tests():
    """Run tests with proper environment setup"""
    
    # Set environment variables for testing
    env = os.environ.copy()
    env['ENVIRONMENT'] = 'testing'
    env['TESTING'] = 'true'
    env['PYTHONPATH'] = str(Path(__file__).parent)
    
    # Run pytest with coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "-v",  # Verbose output
        "--cov=app",  # Coverage for app directory
        "--cov-report=html",  # HTML coverage report
        "--cov-report=term",  # Terminal coverage report
        "--asyncio-mode=auto",  # Auto detect async tests
        "-W", "ignore::DeprecationWarning",  # Ignore deprecation warnings
        "tests/"  # Test directory
    ]
    
    # Add custom arguments if provided
    if len(sys.argv) > 1:
        cmd.extend(sys.argv[1:])
    
    print(f"Running tests with command: {' '.join(cmd)}")
    print(f"Environment: {env.get('ENVIRONMENT')}")
    
    result = subprocess.run(cmd, env=env)
    
    if result.returncode == 0:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Tests failed!")
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())