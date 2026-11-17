#!/usr/bin/env python3
"""
Entry point to run the Examination Management Portal (EMP) web application.
"""
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from app.database import init_db

app = create_app(os.environ.get('FLASK_CONFIG', 'default'))

if __name__ == '__main__':
    # Initialize DB automatically if running for the first time
    init_db(app)
    
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    print(f"\n* Starting EMP on http://{host}:{port}")
    app.run(host=host, port=port, debug=True)
