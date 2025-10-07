# --- START OF FILE Dockerfile ---

# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Install system-level dependencies required for the mariadb Python package.
RUN apt-get update && apt-get install -y libmariadb-dev gcc && \
    rm -rf /var/lib/apt/lists/*


# Copy ONLY the requirements file first.
# This is a Docker best practice for layer caching. If requirements.txt doesn't change,
# this layer (and the next one) will be cached, speeding up builds.
COPY requirements.txt ./

# Install the Python dependencies.
# This will now reliably find the requirements.txt we just copied.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container.
# This copies everything from your repo root into the /app directory.
COPY . .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variable (optional, good practice)
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# This default is overridden by the 'command' in docker-compose.yaml for each service
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

# --- END OF FILE Dockerfile ---
