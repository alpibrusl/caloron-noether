"""Run the orchestrator: python3 -m orchestrator 'goal' or python3 orchestrator/orchestrator.py 'goal'"""
import sys
import os

# Ensure the orchestrator directory is in the path for sibling imports
sys.path.insert(0, os.path.dirname(__file__))

from orchestrator import main

main()
