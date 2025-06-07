FROM python:3.12-slim

# Install system dependencies (including distutils)
RUN apt-get update && apt-get install -y python3-distutils

# Set working directory
WORKDIR /app

# Copy your code
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Expose port and set entrypoint
EXPOSE 8000
CMD ["gunicorn", "videoshorts.wsgi:application", "--bind", "0.0.0.0:8000"]
