# Dockerfile
# Docker image for python 3.11
FROM python:3.11-slim

# Set the working directory to /app
WORKDIR /app

# copy only the requirements file used to install dependencies
COPY requirements.txt .

# install dependencies 
RUN pip install --no-cache-dir -r requirements.txt

# copy the rest of the files
COPY . .

# Inform Docker that the container is listening on port 8000
EXPOSE 8000

# command to run on container start
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

