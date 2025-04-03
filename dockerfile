FROM python:3.12-slim
# Install LaTeX packages
RUN apt-get update && apt-get install -y \
    texlive-latex-base \
    texlive-latex-extra \
    texlive-fonts-recommended \
    && apt-get clean
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV PORT=8000
EXPOSE $PORT
# Use exec form for CMD
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]
