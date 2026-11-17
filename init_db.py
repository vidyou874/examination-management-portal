#!/usr/bin/env python3
"""
Database Initialization Script for Examination Management Portal (EMP).
Creates SQLite tables and the initial administrator account programmatically.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.database import init_db
from app.config import Config

def main():
    print("=" * 60)
    print("  Examination Management Portal (EMP) - Database Setup")
    print("=" * 60)
    print(f"Target Database: {Config.DATABASE_PATH}")
    
    init_db()
    
    print("\nDatabase initialization complete.")
    print(f"Default Administrator Account initialized:")
    print(f"  Username: {Config.ADMIN_USERNAME}")
    print(f"  Email:    {Config.ADMIN_EMAIL}")
    print(f"  Password: {Config.ADMIN_PASSWORD}")
    print("=" * 60)

if __name__ == '__main__':
    main()
