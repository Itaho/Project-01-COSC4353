FROM python:3.12-slim

# Install LaTeX packages
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && apt-get clean

# Create directories with proper permissions
RUN mkdir -p /app/SavedPdf /app/static/pdfs /app/static/signatures
RUN chmod -R 777 /app/SavedPdf /app/static/pdfs /app/static/signatures

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
