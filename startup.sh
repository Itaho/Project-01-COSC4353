#!/bin/bash
# Install LaTeX + make
apt-get update && apt-get install -y make texlive-latex-base texlive-latex-extra

# Optionally install more packages

# Then start your app
gunicorn app:app --bind=0.0.0.0:8000
