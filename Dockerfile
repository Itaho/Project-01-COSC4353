# Use an official slim Python image as base
FROM python:3.12-slim

# Install system dependencies including a minimal LaTeX distribution.
# Note: texlive-full is large; you may opt for texlive-latex-base and a few extras.
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    texlive-latex-extra \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your application code
COPY . /app

# Expose the port (ensure it matches what your app listens on, e.g., 8000)
EXPOSE 8000

# Start the application using Gunicorn (adjust the module name if needed)
CMD ["gunicorn", "-b", "0.0.0.0:8000", "app:app"]
