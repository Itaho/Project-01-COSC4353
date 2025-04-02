FROM python:3.12-slim

# Install LaTeX for pdflatex
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy your dependencies file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . /app

EXPOSE 8000

# Run your Flask app
CMD ["python", "app.py"]

