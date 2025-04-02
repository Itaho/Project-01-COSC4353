FROM python:3.12-slim

# Install LaTeX packages
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && apt-get clean

WORKDIR /app

RUN mkdir -p static/signatures static/pdfs
RUN chmod 777 static/signatures static/pdfs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENV PORT=8000
EXPOSE 8000

CMD gunicorn --bind 0.0.0.0:$PORT app:app
