# Connectivity probe for Hugging Face Spaces (Day 13): can a Space reach the course endpoints?
FROM python:3.12-slim
RUN useradd --create-home --uid 1000 app
USER app
WORKDIR /home/app
COPY --chown=app app.py .
EXPOSE 7860
CMD ["python", "app.py"]
